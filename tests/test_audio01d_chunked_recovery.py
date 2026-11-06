"""AUDIO-01D: real PCM chunks, pause/resume, cancellation and tampering."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
import wave

from backend.nvp_audio01d_chunked_recovery import (
    RATE, CHUNK_SAMPLES, run_chunked_preview, verify_chunked_preview
)


def clip(start,stop,source=0,gain=1000):
    return {"out_start":start,"out_end":stop,"source_start":source,
            "fade_in":0,"fade_out":0,"gain_milli":gain}


class ChunkedRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.sources={}
        for sid,value in (("voice",1000),("room",200)):
            p=self.root/(sid+".wav")
            with wave.open(str(p),"wb") as w:
                w.setnchannels(2)
                w.setsampwidth(2)
                w.setframerate(RATE)
                # 30 seconds of genuinely written media, exceeding B13 20s fixture.
                w.writeframes(struct.pack("<hh",value,-value)*(RATE*30))
            self.sources[sid]=p
        self.length=RATE*25
        self.plan={"stems":[
            {"stem_id":"voice","kind":"dialogue","clips":[clip(0,self.length)]},
            {"stem_id":"room","kind":"ambience","clips":[clip(0,self.length,gain=500)]},
        ]}

    def tearDown(self):
        self.temp.cleanup()

    def test_25_second_multi_chunk_resume_and_replay(self):
        output=self.root/"out"
        first=run_chunked_preview(self.plan,self.sources,self.length,output,max_new_chunks=3)
        self.assertEqual(first["status"],"PAUSED_RESUMABLE")
        self.assertEqual(first["next_sample"],3*CHUNK_SAMPLES)
        before=(output/"mix_chunk_0000000.pcm").read_bytes()
        done=run_chunked_preview(self.plan,self.sources,self.length,output)
        self.assertEqual(done["chunks"],25)
        self.assertEqual((output/"mix_chunk_0000000.pcm").read_bytes(),before)
        proof=verify_chunked_preview(self.plan,self.sources,self.length,output)
        self.assertEqual(proof["chunks"],25)
        self.assertTrue(proof["full_replay"])
        raw=(output/"mix_chunk_0000000.pcm").read_bytes()
        self.assertEqual(struct.unpack_from("<hh",raw,0),(1100,-1100))
        # Idempotent completed job does not create new bytes.
        self.assertEqual(run_chunked_preview(self.plan,self.sources,self.length,output)["chunks"],25)

    def test_cancel_and_resume_without_chunk_loss(self):
        out=self.root/"cancel"
        got=run_chunked_preview(self.plan,self.sources,self.length,out,cancel=lambda: True)
        self.assertEqual(got["status"],"CANCELLED_RESUMABLE")
        self.assertEqual(got["chunks"],0)
        self.assertEqual(run_chunked_preview(self.plan,self.sources,self.length,out,
                                             max_new_chunks=2)["chunks"],2)
        self.assertEqual(run_chunked_preview(self.plan,self.sources,self.length,out)["chunks"],25)
        verify_chunked_preview(self.plan,self.sources,self.length,out)

    def test_corruption_and_changed_input_fail_closed(self):
        out=self.root/"tamper"
        run_chunked_preview(self.plan,self.sources,self.length,out,max_new_chunks=2)
        with (out/"stem_voice_chunk_0000000.pcm").open("r+b") as stream:
            stream.seek(6)
            stream.write(b"FAIL")
        with self.assertRaisesRegex(RuntimeError,"modified"):
            run_chunked_preview(self.plan,self.sources,self.length,out)
        out2=self.root/"source_change"
        run_chunked_preview(self.plan,self.sources,self.length,out2,max_new_chunks=1)
        modified=self.plan["stems"][0]["clips"][0]
        modified["gain_milli"]=900
        with self.assertRaisesRegex(RuntimeError,"changed"):
            run_chunked_preview(self.plan,self.sources,self.length,out2)

    def test_clip_validation_rejects_invalid_address_and_gain(self):
        plan=json.loads(json.dumps(self.plan))
        plan["stems"][0]["clips"][0]["source_start"]=RATE*10
        with self.assertRaises(ValueError):
            run_chunked_preview(plan,self.sources,self.length,self.root/"bad")
        plan=json.loads(json.dumps(self.plan))
        plan["stems"][0]["clips"][0]["gain_milli"]=1001
        with self.assertRaises(ValueError):
            run_chunked_preview(plan,self.sources,self.length,self.root/"bad2")

    def test_clipping_fails_before_checkpoint_completion(self):
        p=self.root/"hot.wav"
        with wave.open(str(p),"wb") as w:
            w.setnchannels(2);w.setsampwidth(2);w.setframerate(RATE)
            w.writeframes(struct.pack("<hh",30000,-30000)*(RATE*2))
        sources={"a":p,"b":p}
        plan={"stems":[
            {"stem_id":sid,"kind":kind,"clips":[clip(0,RATE)]}
            for sid,kind in (("a","dialogue"),("b","sfx"))
        ]}
        with self.assertRaisesRegex(RuntimeError,"clip"):
            run_chunked_preview(plan,sources,RATE,self.root/"hot_out")
        with self.assertRaises(RuntimeError):
            verify_chunked_preview(plan,sources,RATE,self.root/"hot_out")


if __name__=="__main__":
    unittest.main()
