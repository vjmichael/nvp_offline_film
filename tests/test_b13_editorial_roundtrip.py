"""B13 OTIO edit round-trip: official NLE schema and native authorization tests.

Synthetic FilmIndex sources below are UNIT fixtures, not claims of real
Blender/ProRes. The real native CI fixture reopens B12's genuine frozen take,
full 120-frame PNG package and independently audited ProRes movie.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from backend.nvp_b12_editorial_delivery import _otio,build_otio
from backend.nvp_b13_editorial_roundtrip import (
    parse_edited_otio,import_edited_otio,verify_imported_edit)
from backend.nvp_b13_native_reimport import NativeB13ImportHost,EDITED
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_studio import Studio


CUTS=[
    {"shot_id":"first_shot","start_frame":1,"stop_frame_exclusive":49},
    {"shot_id":"second_shot","start_frame":49,"stop_frame_exclusive":121},
]


def invented_delivery(project_id="a"*32):
    from string import ascii_lowercase
    media=[]
    for i in range(1,121):
        media.append({
            "frame":i,
            "shot_id":"first_shot" if i<49 else "second_shot",
            "source_exr_sha256":("%064x"%(i*3)),
            "png16_sha256":("%064x"%(i*3+1)),
            "rgb48_sha256":("%064x"%(i*3+2)),
        })
    return {
        "format":"nvp.presentation.b12.editorial_delivery.v1",
        "project_id":project_id,"source_review_id":"review_unit",
        "source_review_sha256":"a"*64,
        "source_take_id":"take_unit",
        "source_take_sha256":"b"*64,
        "source_float32_presentation_id":"exr_unit",
        "source_float32_presentation_sha256":"c"*64,
        "frame_count":120,"fps":24,"camera_cutlist":CUTS,
        "media_frames":media,
    }


def editable_otio():
    otio=_otio()
    initial=build_otio(CUTS,project_id="a"*32,
                       source_take_id="take_unit",review_id="review_unit",
                       frame_count=120)
    first=initial.tracks[0][0].deepcopy()
    second=initial.tracks[0][1].deepcopy()
    repeat=initial.tracks[0][1].deepcopy()
    # Reorder and trim the second shot (9 frames), first shot (16 frames),
    # repeat the second shot for another 8 frames.
    choices=[(second,3,9),(first,5,16),(repeat,0,8)]
    edited=otio.schema.Track(name="Director cut v2",kind=otio.schema.TrackKind.Video)
    for clip,offset,duration in choices:
        clip.source_range=otio.opentime.TimeRange(
            otio.opentime.RationalTime(offset,24),
            otio.opentime.RationalTime(duration,24))
        edited.append(clip)
    timeline=otio.schema.Timeline(name="Edited NVP camera shots",
                                 tracks=[edited],
                                 metadata={"nvp":{"project_id":"a"*32,
                                                  "source_take_id":"take_unit",
                                                  "review_id":"review_unit",
                                                  "fps":24,"frames":120,
                                                  "soundtrack_present":False}})
    return otio.adapters.write_to_string(timeline,adapter_name="otio_json").encode("utf8")


class StrictOTIORoundTrip(unittest.TestCase):
    def test_edit_trim_reorder_repeat_and_source_map(self):
        original=invented_delivery()
        result=parse_edited_otio(editable_otio(),original)
        self.assertEqual(result["fps"],24)
        self.assertEqual(result["frame_count"],33)
        self.assertEqual(result["clip_count"],3)
        self.assertEqual(result["duration_seconds"],33/24)
        self.assertEqual(
            [row["source_frame"] for row in result["frame_map"]],
            list(range(52,61))+list(range(6,22))+list(range(49,57)))
        self.assertEqual(
            [row["edit_frame"] for row in result["frame_map"]],
            list(range(1,34)))
        self.assertEqual(result["segments"][0]["shot_id"],"second_shot")

    def test_rejects_foreign_media_relative_escape_and_invented_camera_shot(self):
        otio=_otio()
        initial=build_otio(CUTS,project_id="a"*32,
                           source_take_id="take_unit",review_id="review_unit",
                           frame_count=120)
        clip=initial.tracks[0][0]
        clip.media_reference.target_url_base="../../other_project/"
        raw=otio.adapters.write_to_string(initial,adapter_name="otio_json").encode()
        with self.assertRaisesRegex(RuntimeError,"media reference"):
            parse_edited_otio(raw,invented_delivery())
        clip.media_reference.target_url_base="media/"
        clip.name="invented_new_shot"
        raw=otio.adapters.write_to_string(initial,adapter_name="otio_json").encode()
        with self.assertRaisesRegex(RuntimeError,"outside"):
            parse_edited_otio(raw,invented_delivery())

    def test_rejects_audio_gap_speed_and_outside_original_shot(self):
        otio=_otio()
        for kind in ("audio","gap","speed","out_of_range"):
            with self.subTest(kind=kind):
                timeline=build_otio(CUTS,project_id="a"*32,
                           source_take_id="take_unit",review_id="review_unit",
                           frame_count=120)
                if kind=="audio":
                    timeline.tracks.append(otio.schema.Track(kind=otio.schema.TrackKind.Audio))
                if kind=="gap":
                    timeline.tracks[0].append(otio.schema.Gap(
                        source_range=otio.opentime.TimeRange(
                           otio.opentime.RationalTime(0,24),
                           otio.opentime.RationalTime(3,24))))
                if kind=="speed":
                    timeline.tracks[0][0].effects.append(
                        otio.schema.LinearTimeWarp(time_scalar=2.0))
                if kind=="out_of_range":
                    timeline.tracks[0][0].source_range=otio.opentime.TimeRange(
                        otio.opentime.RationalTime(40,24),
                        otio.opentime.RationalTime(16,24))
                raw=otio.adapters.write_to_string(timeline,adapter_name="otio_json").encode()
                with self.assertRaises(RuntimeError):
                    parse_edited_otio(raw,invented_delivery())

    def test_disabled_clips_and_parent_picture_trim_are_denied(self):
        otio=_otio()
        for modification in ("disabled_clip","disabled_track","trimmed_track"):
            with self.subTest(modification=modification):
                timeline=build_otio(CUTS,project_id="a"*32,
                     source_take_id="take_unit",review_id="review_unit",
                     frame_count=120)
                if modification=="disabled_clip":
                    timeline.tracks[0][0].enabled=False
                elif modification=="disabled_track":
                    timeline.tracks[0].enabled=False
                else:
                    timeline.tracks[0].source_range=otio.opentime.TimeRange(
                        otio.opentime.RationalTime(0,24),
                        otio.opentime.RationalTime(50,24))
                raw=otio.adapters.write_to_string(
                    timeline,adapter_name="otio_json").encode("utf8")
                with self.assertRaises(RuntimeError):
                    parse_edited_otio(raw,invented_delivery())

    def test_native_otio_anydictionary_origin_is_required_and_complete(self):
        otio=_otio()
        for changed in ("project_id","source_take_id","review_id",
                        "fps","frames","soundtrack_present"):
            with self.subTest(changed=changed):
                timeline=build_otio(CUTS,project_id="a"*32,
                       source_take_id="take_unit",review_id="review_unit",
                       frame_count=120)
                edits={"project_id":"b"*32,"source_take_id":"other_take",
                       "review_id":"foreign_review","fps":25,"frames":121,
                       "soundtrack_present":True}
                timeline.metadata["nvp"][changed]=edits[changed]
                wire=otio.adapters.write_to_string(
                    timeline,adapter_name="otio_json").encode("utf8")
                with self.assertRaisesRegex(RuntimeError,"origin"):
                    parse_edited_otio(wire,invented_delivery())
        timeline=build_otio(CUTS,project_id="a"*32,
              source_take_id="take_unit",review_id="review_unit",frame_count=120)
        timeline.metadata["nvp"]={}
        with self.assertRaisesRegex(RuntimeError,"origin"):
            parse_edited_otio(otio.adapters.write_to_string(
                timeline,adapter_name="otio_json").encode("utf8"),invented_delivery())

    def test_rejects_oversize_non_timelines_and_invalid_origin(self):
        with self.assertRaises(ValueError):
            parse_edited_otio(b"X"*(4*1024*1024+1),invented_delivery())
        otio=_otio()
        fake=otio.adapters.write_to_string(otio.schema.Clip(name="nothing"),
                                           adapter_name="otio_json").encode()
        with self.assertRaises(RuntimeError):
            parse_edited_otio(fake,invented_delivery())
        timeline=build_otio(CUTS,project_id="a"*32,
                           source_take_id="take_unit",review_id="review_unit",
                           frame_count=120)
        timeline.metadata["nvp"]["source_take_id"]="another_take"
        forged=otio.adapters.write_to_string(timeline,adapter_name="otio_json").encode()
        with self.assertRaisesRegex(RuntimeError,"origin"):
            parse_edited_otio(forged,invented_delivery())


class NativeB13RevisionContract(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        root=Path(self.temp.name)
        self.studio=Studio(root/"film.sqlite3")
        self.pid=self.studio.create_project("B13 policy-only fixture","")["id"]
        self.capture=DigitalCapture(self.studio)
        take=self.capture.index.register_revision(
            self.pid,"take_unit","take",{"format":"unit.mock.take"})
        source=self.capture.index.register_revision(
            self.pid,"exr_unit","presentation",
            {"format":"unit.mock.float32"})
        review=self.capture.index.register_revision(
            self.pid,"review_unit","presentation",
            {"format":"unit.mock.sdr"})
        doc=invented_delivery(self.pid)
        doc["source_take_sha256"]=take["document_sha256"]
        doc["source_float32_presentation_sha256"]=source["document_sha256"]
        doc["source_review_sha256"]=review["document_sha256"]
        delivery=self.capture.index.register_revision(
            self.pid,"delivery_unit","presentation",doc,
            dependencies=[{"object_id":"take_unit","revision":1,"role":"source_take"},
                          {"object_id":"review_unit","revision":1,"role":"presentation"},
                          {"object_id":"exr_unit","revision":1,"role":"presentation"}])
        self.delivery_sha=delivery["document_sha256"]
        self.signal=object()
        self.scopes=[]
        self.package=root/"original_package"
        self.package.mkdir()
        self.otiofile=root/"editor_altered.otio"
        # Initial OTIO project metadata must match actual project ID.
        edited=editable_otio()
        edited=edited.replace(("a"*32).encode(),self.pid.encode())
        self.otiofile.write_bytes(edited)
        self.mock_one=patch("backend.nvp_b13_editorial_roundtrip.verify_editorial_handoff",
                            return_value={"status":"VERIFIED_PORTABLE_EDITORIAL_HANDOFF"})
        self.mock_two=patch("backend.nvp_b13_native_reimport.verify_editorial_handoff",
                            return_value={"status":"VERIFIED_PORTABLE_EDITORIAL_HANDOFF"})
        self.mock_one.start()
        self.mock_two.start()
        self.ledger=TaskLedger(root/"resources",
                               sampler=lambda:ResourceSnapshot(1,32768,25000,0,()))
        def creator(event,scope):
            self.scopes.append(scope)
            return event is self.signal
        self.host=NativeB13ImportHost(
            self.capture,self.ledger,root/"native",verify_creator_action=creator)

    def tearDown(self):
        self.mock_one.stop()
        self.mock_two.stop()
        self.temp.cleanup()

    def stage(self,**kw):
        return self.host.stage_and_approve(
            self.pid,"delivery_unit",self.package,self.otiofile,self.signal,
            **kw)

    def test_native_creator_scope_captures_actual_edited_input_and_declares_no_audio(self):
        with self.assertRaises(PermissionError):
            self.host.stage_and_approve(
                self.pid,"delivery_unit",self.package,self.otiofile,{"web":True})
        ticket=self.stage()
        self.assertEqual(ticket["state"],"QUEUED")
        self.assertFalse(ticket["native_worker_started"])
        scope=self.scopes[-1]
        self.assertEqual(scope["edited_otio_sha256"],ticket["otio_sha256"])
        self.assertEqual(scope["source_delivery_sha256"],self.delivery_sha)
        self.assertEqual(scope["maximum_output_frames"],480)
        self.assertFalse(scope["audio_import_allowed"])

    def test_low_ram_refuses_parser_and_reservation(self):
        ticket=self.stage()
        self.ledger.sampler=lambda:ResourceSnapshot(1,16384,400,0,())
        with patch("backend.nvp_b13_native_reimport.launch_contained",
                   side_effect=AssertionError("OTIO must not start on RAM pressure")) as launched:
            denied=self.host.run_next()
            launched.assert_not_called()
        self.assertEqual(denied["state"],"QUEUED")
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_tampered_input_and_expired_consent_refuse_spawn(self):
        token=self.stage()
        inp=self.host.root/token["job_id"]/EDITED
        inp.write_bytes(inp.read_bytes()+b"altered")
        with patch("backend.nvp_b13_native_reimport.launch_contained") as proc:
            with self.assertRaises(PermissionError):
                self.host.run_next()
            proc.assert_not_called()
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)
        self.ledger.cancel_queued(token["job_id"],owner_key=self.host.owner_key)
        token2=self.stage()
        with self.ledger._db() as db:
            db.execute("UPDATE native_b13_import_grants SET expires_at=0 WHERE job_id=?",
                       (token2["job_id"],))
        with patch("backend.nvp_b13_native_reimport.launch_contained") as proc:
            with self.assertRaises(PermissionError):
                self.host.run_next()
            proc.assert_not_called()

    def test_unknown_os_launcher_state_keeps_ram_reservation(self):
        token=self.stage()
        with patch("backend.nvp_b13_native_reimport.launch_contained",
                   side_effect=RuntimeError("unverified worker handle")):
            with self.assertRaisesRegex(RuntimeError,"worker handle"):
                self.host.run_next()
        self.assertEqual(self.ledger.get_task(token["job_id"])["state"],"ACTIVE")
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],1024)

    def test_revision_cas_original_take_history_and_restart(self):
        edited=self.otiofile.read_bytes()
        imported=import_edited_otio(
            self.capture,self.pid,"delivery_unit",self.package,
            "edited_picture",edited)
        self.assertEqual(imported["revision"],1)
        self.assertEqual(imported["frames"],33)
        # Second edit is a new revision of ONE persistent edit object.
        revised=import_edited_otio(
            self.capture,self.pid,"delivery_unit",self.package,
            "edited_picture",edited,expected_edit_revision=1)
        self.assertEqual(revised["revision"],2)
        self.assertEqual(len(self.capture.index.history(self.pid,"edited_picture")),2)
        with self.assertRaises(RuntimeError):
            import_edited_otio(
                self.capture,self.pid,"delivery_unit",self.package,
                "edited_picture",edited,expected_edit_revision=1)
        restarted=DigitalCapture(Studio(self.studio.db_path))
        accepted=verify_imported_edit(
            restarted,self.pid,"edited_picture",self.package,revision=1)
        self.assertEqual(accepted["frames"],33)
        self.assertFalse(accepted["picture_approved"])
        self.assertEqual(
            restarted.index.read_revision(self.pid,"take_unit")["revision"],1)

    def test_cancel_unstarted_native_import_does_not_claim_process_killed(self):
        ticket=self.stage()
        with self.assertRaises(PermissionError):
            self.host.revoke_from_trusted_native_action(ticket["job_id"],{"fake":True})
        result=self.host.revoke_from_trusted_native_action(ticket["job_id"],self.signal)
        self.assertTrue(result["queued_cancelled"])
        self.assertFalse(result["live_worker_terminated_claimed"])
        self.assertEqual(self.ledger.get_task(ticket["job_id"])["state"],"CANCELLED")


if __name__=="__main__":
    unittest.main()
