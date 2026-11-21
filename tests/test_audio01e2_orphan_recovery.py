"""Failure injection for AUDIO-01E.2 incomplete chunk reconciliation."""
import json
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from backend.nvp_audio01d_chunked_recovery import (
    RATE, CHUNK_SAMPLES, _render_chunk, _validate, run_chunked_preview,
    verify_chunked_preview,
)
from backend.nvp_audio01e2_orphan_recovery import reconcile_next_chunk


def clip(samples):
    return {"out_start": 0, "out_end": samples, "source_start": 0,
            "fade_in": 0, "fade_out": 0, "gain_milli": 1000}


class RecoveryFaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.total = RATE*3
        self.sources = {}
        for sid, value in (("voice", 500), ("room", 100)):
            path = self.root/(sid+".wav")
            with wave.open(str(path), "wb") as w:
                w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE)
                w.writeframes(struct.pack("<hh", value, -value)*self.total)
            self.sources[sid] = path
        self.plan = {"stems": [
            {"stem_id": "voice", "kind": "dialogue", "clips": [clip(self.total)]},
            {"stem_id": "room", "kind": "ambience", "clips": [clip(self.total)]},
        ]}
        self.work = self.root/"out"
        run_chunked_preview(self.plan,self.sources,self.total,self.work,max_new_chunks=1)

    def tearDown(self):
        self.temp.cleanup()

    def orphan(self, count):
        stems = _validate(self.plan,self.sources,self.total)
        blocks = _render_chunk(stems,self.sources,RATE,RATE*2)
        names = ("stem_voice_chunk_0000001.pcm",
                 "stem_room_chunk_0000001.pcm",
                 "mix_chunk_0000001.pcm")
        for i in range(count):
            (self.work/names[i]).write_bytes(blocks[i])
        return names

    def test_missing_output_filled_and_then_resume(self):
        names = self.orphan(1)
        result = reconcile_next_chunk(self.plan,self.sources,self.total,self.work)
        self.assertEqual(result["status"], "RECOVERED_SOURCE_VERIFIED_CHUNK")
        self.assertEqual(result["next_sample"], 2*CHUNK_SAMPLES)
        self.assertTrue(all((self.work/name).exists() for name in names))
        self.assertEqual(run_chunked_preview(self.plan,self.sources,self.total,self.work)["chunks"],3)
        verify_chunked_preview(self.plan,self.sources,self.total,self.work)

    def test_all_outputs_written_but_receipt_missing(self):
        self.orphan(3)
        self.assertEqual(reconcile_next_chunk(self.plan,self.sources,self.total,self.work)["reconciled_chunks"],1)
        self.assertEqual(run_chunked_preview(self.plan,self.sources,self.total,self.work)["chunks"],3)

    def test_no_orphans_does_not_advance_checkpoint(self):
        before=(self.work/"checkpoint.json").read_bytes()
        result=reconcile_next_chunk(self.plan,self.sources,self.total,self.work)
        self.assertEqual(result["status"],"NO_ORPHAN_CHUNK")
        self.assertEqual((self.work/"checkpoint.json").read_bytes(),before)

    def test_modified_orphan_rejected_without_receipt(self):
        names=self.orphan(2)
        with (self.work/names[0]).open("r+b") as f:
            f.seek(20);f.write(b"FAIL")
        with self.assertRaisesRegex(RuntimeError,"differs"):
            reconcile_next_chunk(self.plan,self.sources,self.total,self.work)
        checkpoint=json.loads((self.work/"checkpoint.json").read_text())
        self.assertEqual(checkpoint["next_sample"],RATE)

    def test_changed_plan_is_rejected(self):
        self.orphan(1)
        self.plan["stems"][0]["clips"][0]["gain_milli"]=999
        with self.assertRaisesRegex(RuntimeError,"changed"):
            reconcile_next_chunk(self.plan,self.sources,self.total,self.work)

    def test_unexpected_artifacts_and_checkpoint_stage_rejected(self):
        self.orphan(1)
        (self.work/"future_chunk_0000009.pcm").write_bytes(b"unexpected")
        with self.assertRaisesRegex(RuntimeError,"Unexpected"):
            reconcile_next_chunk(self.plan,self.sources,self.total,self.work)
        (self.work/"future_chunk_0000009.pcm").unlink()
        (self.work/"checkpoint.json.new").write_bytes(b"partial")
        with self.assertRaisesRegex(RuntimeError,"Pending checkpoint"):
            reconcile_next_chunk(self.plan,self.sources,self.total,self.work)

    def test_cannot_reconcile_completed_checkpoint(self):
        run_chunked_preview(self.plan,self.sources,self.total,self.work)
        with self.assertRaisesRegex(RuntimeError,"incomplete"):
            reconcile_next_chunk(self.plan,self.sources,self.total,self.work)


if __name__ == "__main__":
    unittest.main()
