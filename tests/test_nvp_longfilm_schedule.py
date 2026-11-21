"""Portable exact-clock and streaming regressions; no renderer acceptance."""
import hashlib
import json
from pathlib import Path
import tempfile
import struct
import wave
import unittest
from unittest.mock import patch

from backend.nvp_longfilm_schedule import ChunkSchedule, MAX_CHUNKS, MAX_TOTAL_FRAMES, MAX_PAGE
from backend.nvp_p2_longform_source_plan import NativeLongformFilmPlan
from backend.nvp_p1f_sustained_delivery import FRAME_TICKS, MAX_CHUNK_FRAMES, _bounded_file_digest, _bounded_manifest, MAX_MANIFEST_BYTES
from backend.nvp_p1f_sustained_delivery import NativeSustainedPictureSound, FORMAT as CHUNK_FORMAT, _digest


def segment(start, frames, source=0, ident="Cut"):
    return {"timeline_start_tick": start*FRAME_TICKS,
            "timeline_end_tick": (start+frames)*FRAME_TICKS,
            "source_in_tick": source*FRAME_TICKS,
            "source_out_tick": (source+frames)*FRAME_TICKS,
            "segment_id": ident, "source_take_id": "Take"+ident,
            "source_take_document_sha256": "a"*64,
            "source_shot_id": None, "source_shot_document_sha256": None}


def legacy_rows(segments):
    index=0
    for s in segments:
        start=s["timeline_start_tick"]//FRAME_TICKS
        end=s["timeline_end_tick"]//FRAME_TICKS
        for first in range(start,end,MAX_CHUNK_FRAMES):
            yield {"index":index,"chunk_id":"P2FilmChunk"+str(index).zfill(6),
                "first_frame":first,"frame_count":min(MAX_CHUNK_FRAMES,end-first),
                "segment_id":s["segment_id"],"source_take_id":s["source_take_id"],
                "source_take_sha256":s["source_take_document_sha256"],
                "source_shot_id":s["source_shot_id"],"source_shot_sha256":s["source_shot_document_sha256"],
                "source_start_tick":str(s["source_in_tick"]+(first-start)*FRAME_TICKS)}
            index+=1


def digest(rows):
    h=hashlib.sha256()
    for row in rows:
        h.update(json.dumps(row,sort_keys=True,separators=(",",":"),ensure_ascii=True,
                            allow_nan=False).encode("ascii")+b"\n")
    return h.hexdigest()


class ScheduleTests(unittest.TestCase):
    def test_legacy_identity_digest_and_cut_boundary(self):
        seg=[segment(0,25,9,"A"),segment(25,49,71,"B"),segment(74,1,1,"C")]
        schedule=ChunkSchedule(seg)
        expected=list(legacy_rows(seg))
        self.assertEqual(list(schedule.entries()),expected)
        self.assertEqual(schedule.digest(),digest(expected))
        self.assertEqual(schedule.page(1,4),expected[1:5])
        self.assertEqual(schedule.page(len(expected)-1,64),expected[-1:])
        self.assertEqual([x["frame_count"] for x in expected],[24,1,24,24,1,1])

    def test_extended_durations_and_late_seek_no_prefix_scan(self):
        for hours in (0.5,1,3,6,8,12):
            frames=int(hours*3600*24)
            s=ChunkSchedule([segment(0,frames)])
            self.assertEqual(s.total_frames,frames)
            self.assertEqual(s.total_chunks,frames//24)
            with patch.object(s,"_entry",wraps=s._entry) as read:
                rows=s.page(s.total_chunks-2,64)
            self.assertEqual(read.call_count,2)
            self.assertEqual(rows[-1]["first_frame"]+rows[-1]["frame_count"],frames)
            self.assertEqual(rows[-1]["source_start_tick"],str((frames-24)*FRAME_TICKS))

    def test_full_eight_hour_digest_matches_legacy(self):
        seg=[segment(0,8*3600*24)]
        s=ChunkSchedule(seg)
        self.assertEqual(s.digest(),digest(legacy_rows(seg)))
        self.assertEqual(sum(len(s.page(i,MAX_PAGE)) for i in range(0,s.total_chunks,MAX_PAGE)),28800)

    def test_address_bounds_and_invalid_positions(self):
        s=ChunkSchedule([segment(0,MAX_TOTAL_FRAMES)])
        self.assertLessEqual(s.total_chunks,MAX_CHUNKS)
        self.assertEqual(s.page(s.total_chunks-1,1)[0]["index"],s.total_chunks-1)
        with self.assertRaises(ValueError): ChunkSchedule([segment(0,MAX_TOTAL_FRAMES+1)])
        # Splits consume additional chunk identities even without adding frames.
        if MAX_TOTAL_FRAMES == MAX_CHUNKS*MAX_CHUNK_FRAMES:
            with self.assertRaises(ValueError):
                ChunkSchedule([segment(0,1),segment(1,MAX_TOTAL_FRAMES-1)])
        for start,limit in ((-1,1),(s.total_chunks,1),(0,65),(0,0),(True,1),(0,True)):
            with self.assertRaises(ValueError): s.page(start,limit)

    def test_reject_gaps_zero_retime_and_misalignment(self):
        good=segment(0,24)
        for seg in ([segment(1,4)], [good,segment(25,1)], [segment(0,0)],
                    [{**good,"source_out_tick":good["source_out_tick"]+FRAME_TICKS}],
                    [{**good,"timeline_end_tick":good["timeline_end_tick"]+1}], []):
            with self.assertRaises((RuntimeError,ValueError)): ChunkSchedule(seg)

    def test_digest_cancellation_and_snapshot_not_mutable(self):
        original=segment(0,5000)
        s=ChunkSchedule([original]); first=s.page(0,1)
        original["source_take_id"]="Other"
        self.assertEqual(s.page(0,1),first)
        checks=iter((False,True))
        with self.assertRaises(InterruptedError): s.digest(cancelled=lambda:next(checks))

    def test_full_reconciliation_validates_once_before_and_after(self):
        # Synthetic receipts only: exercise orchestration, not media acceptance.
        schedule=ChunkSchedule([segment(0,24*130)])
        record={"document_sha256":"b"*64,"data":{"total_chunks":130,
            "total_frames":24*130,"is_thirty_minute_longform":False}}
        planner=object.__new__(NativeLongformFilmPlan)
        def verify(project,record,schedule,**kw):
            entries=schedule.page(kw["first_index"],kw["limit"])
            return {"missing_chunks":[],"verified_chunks":[{"first_frame":r["first_frame"],
                "frames":r["frame_count"],"audio_samples":r["frame_count"]*2000} for r in entries]}
        with patch.object(planner,"_open_schedule",return_value=(record,schedule)) as opened, \
                patch.object(planner,"_reconcile_verified_page",side_effect=verify) as verify_page:
            proof=planner.reconcile_all("pid","plan",1,output_parent="unused")
            self.assertEqual(opened.call_count,2)
            self.assertEqual(verify_page.call_count,3)
        self.assertEqual(proof["verified_frames"],3120)
        self.assertFalse(proof["master_approved"])
        altered={**record,"document_sha256":"c"*64}
        with patch.object(planner,"_open_schedule",side_effect=[(record,schedule),(altered,schedule)]), \
                patch.object(planner,"_reconcile_verified_page",side_effect=verify):
            with self.assertRaises(RuntimeError): planner.reconcile_all("pid","plan",1,output_parent="unused")


class StreamingTests(unittest.TestCase):
    def test_real_file_stream_digest_and_size_bound(self):
        data=b"a"*(3*1024*1024+13)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"file";p.write_bytes(data)
            sha,head=_bounded_file_digest(p,len(data),header_bytes=32)
            self.assertEqual(sha,hashlib.sha256(data).hexdigest());self.assertEqual(head,data[:32])
            with self.assertRaises(RuntimeError): _bounded_file_digest(p,len(data)-1)
            with self.assertRaises(RuntimeError): _bounded_manifest(p)
            p.write_bytes(b"{}")
            self.assertEqual(_bounded_manifest(p),b"{}")
            with self.assertRaises(RuntimeError): _bounded_file_digest(p,100,header_bytes=32)

    def test_chunk_verifier_reads_real_fixture_files_and_binds_manifest(self):
        # The payload is a structural PNG fixture, not a rendered image.
        # Only source preflight is replaced: all file/clock/hash checks are real.
        pid="1"*32
        plan={"project_id":pid,"first_frame":0,"frame_count":1,
            "source_start_tick":"0","source_take_id":"Take","source_take_sha256":"a"*64,
            "source_shot_id":None,"source_shot_sha256":None,
            "edit_document_sha256":"b"*64,"continuity_document_sha256":"c"*64,
            "camera_path":"/World/Camera","listener_path":"/World/Camera"}
        verifier=object.__new__(NativeSustainedPictureSound)
        verifier.require_protected_worker=False
        verifier.native_worker_verifier=None
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);pictures=root/"pictures";pictures.mkdir()
            payload=b"\x89PNG\r\n\x1a\n"+struct.pack(">I4sII",13,b"IHDR",1,1)+b"\x00"*8
            (pictures/"000001.png").write_bytes(payload)
            with wave.open(str(root/"soundtrack.wav"),"wb") as wav:
                wav.setnchannels(2);wav.setsampwidth(2);wav.setframerate(48000)
                wav.writeframes(b"\x00"*8000)
            manifest={"format":CHUNK_FORMAT,"status":"SOURCE_BOUNDED_PICTURE_PCM_CHUNK",
                "source_modified":False,"conventional_master_approved":False,"ffmpeg_used":False,
                "plan":plan,"plan_sha256":_digest(plan),"native_worker_receipts_embedded":False,
                "requires_protected_native_worker":False,"picture_dimensions":[1,1],
                "chunk_id":"P2FilmChunk000000","audio_samples":2000,
                "audio_sha256":hashlib.sha256((root/"soundtrack.wav").read_bytes()).hexdigest(),
                "frames":[{"filename":"000001.png","index":0,"output_frame":0,
                           "source_tick":"0","sha256":hashlib.sha256(payload).hexdigest()}]}
            raw=json.dumps(manifest).encode();(root/"manifest.json").write_bytes(raw)
            with patch.object(verifier,"_fresh"):
                proof=verifier.verify_chunk(pid,root)
                self.assertEqual(proof["manifest_sha256"],hashlib.sha256(raw).hexdigest())
                self.assertEqual(proof["continuity_document_sha256"],plan["continuity_document_sha256"])
                self.assertFalse(proof["protected_worker_independently_reopened"])
                verifier.require_protected_worker=True
                with self.assertRaises(RuntimeError): verifier.verify_chunk(pid,root)
                verifier.require_protected_worker=False
                (pictures/"000001.png").write_bytes(payload+b"tampered")
                with self.assertRaises(RuntimeError): verifier.verify_chunk(pid,root)
                (pictures/"000001.png").write_bytes(payload)
                with patch.object(verifier,"_fresh",side_effect=lambda _: (root/"manifest.json").write_bytes(raw+b" ")):
                    with self.assertRaisesRegex(RuntimeError,"manifest changed"):
                        verifier.verify_chunk(pid,root)

    def test_oversized_sparse_file_refused_before_streaming(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"sparse"
            with p.open("wb") as f: f.truncate(100*1024*1024)
            with self.assertRaises(RuntimeError): _bounded_file_digest(p,MAX_MANIFEST_BYTES)


if __name__=="__main__": unittest.main()
