"""AUDIO-01E.6 fault injection for atomic checkpoint replacement boundaries."""
import copy
import json
import hashlib
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from backend.nvp_audio01d_chunked_recovery import (
    RATE, _json_bytes, _render_chunk, _read_state, _validate, run_chunked_preview,
    verify_chunked_preview,
)
from backend.nvp_audio_checkpoint_stage_recovery import reconcile_checkpoint_stage


class StagedCheckpointRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.wav=self.root/"input.wav"
        self.n=RATE*3
        with wave.open(str(self.wav),"wb") as output:
            output.setnchannels(2);output.setsampwidth(2);output.setframerate(RATE)
            output.writeframes(struct.pack("<hh",750,-750)*self.n)
        self.sources={"voice":self.wav}
        self.plan={"stems":[{"stem_id":"voice","kind":"dialogue","clips":[{
            "out_start":0,"out_end":self.n,"source_start":0,
            "fade_in":0,"fade_out":0,"gain_milli":1000
        }]}]}
        self.work=self.root/"render"
        run_chunked_preview(self.plan,self.sources,self.n,self.work,max_new_chunks=1)

    def tearDown(self):
        self.temp.cleanup()

    def stage(self):
        state=_read_state(self.work)
        pieces=_render_chunk(_validate(self.plan,self.sources,self.n),
                             self.sources,RATE,RATE*2)
        names=["stem_voice_chunk_0000001.pcm","mix_chunk_0000001.pcm"]
        for path,raw in zip(names,pieces):
            (self.work/path).write_bytes(raw)
        updated=copy.deepcopy(state)
        updated["chunks"].append({
            "index":1,"start_sample":RATE,"samples":RATE,
            "files":names,
            "sha256":[hashlib.sha256(x).hexdigest() for x in pieces],
        })
        updated["next_sample"]=RATE*2
        (self.work/"checkpoint.json.new").write_bytes(_json_bytes(updated))
        return names,updated

    def test_adopt_valid_stage_and_resume(self):
        original=(self.work/"mix_chunk_0000000.pcm").read_bytes()
        self.stage()
        found=reconcile_checkpoint_stage(self.plan,self.sources,self.n,self.work)
        self.assertEqual(found["status"],"RECOVERED_STAGED_CHECKPOINT")
        self.assertFalse((self.work/"checkpoint.json.new").exists())
        self.assertEqual(_read_state(self.work)["next_sample"],RATE*2)
        self.assertEqual(run_chunked_preview(self.plan,self.sources,self.n,self.work)["chunks"],3)
        verify_chunked_preview(self.plan,self.sources,self.n,self.work)
        self.assertEqual(original,(self.work/"mix_chunk_0000000.pcm").read_bytes())

    def test_reject_corrupt_stage(self):
        names,_=self.stage()
        (self.work/names[0]).write_bytes(b"altered")
        with self.assertRaisesRegex(RuntimeError,"missing or corrupted"):
            reconcile_checkpoint_stage(self.plan,self.sources,self.n,self.work)
        self.assertEqual(_read_state(self.work)["next_sample"],RATE)
        self.assertTrue((self.work/"checkpoint.json.new").exists())

    def test_reject_forged_stage_history(self):
        _,updated=self.stage()
        updated["chunks"][0]["sha256"][0]="0"*64
        (self.work/"checkpoint.json.new").write_bytes(_json_bytes(updated))
        with self.assertRaisesRegex(RuntimeError,"rewrite history"):
            reconcile_checkpoint_stage(self.plan,self.sources,self.n,self.work)
        self.assertEqual(_read_state(self.work)["next_sample"],RATE)

    def test_no_stage_no_mutation(self):
        old=(self.work/"checkpoint.json").read_bytes()
        self.assertEqual(reconcile_checkpoint_stage(self.plan,self.sources,self.n,self.work)["status"],
                         "NO_PENDING_CHECKPOINT")
        self.assertEqual((self.work/"checkpoint.json").read_bytes(),old)

    def test_recover_final_complete_marker(self):
        run_chunked_preview(self.plan,self.sources,self.n,self.work)
        state=_read_state(self.work)
        self.assertEqual(state["status"],"complete")
        # A completed marker exists already; replacing it must not be treated
        # as fresh uncommitted work. No regression is permitted.
        (self.work/"checkpoint.json.new").write_bytes(_json_bytes(state))
        with self.assertRaisesRegex(RuntimeError,"terminal"):
            reconcile_checkpoint_stage(self.plan,self.sources,self.n,self.work)


if __name__=="__main__":
    unittest.main()
