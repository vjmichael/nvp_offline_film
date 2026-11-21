"""AUDIO-01E: materialized real WAV sources, stems and FilmIndex durability."""
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
import wave

from backend.nvp_audio01d_chunked_recovery import run_chunked_preview, RATE
from backend.nvp_audio01e_wav_publication import (
    publish_chunked_wavs, verify_published_wavs,
)
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_studio import Studio


def clip(end, gain=1000):
    return {"out_start":0,"out_end":end,"source_start":0,
            "fade_in":0,"fade_out":0,"gain_milli":gain}


class AudioPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.cap=DigitalCapture(Studio(self.root/"studio.sqlite3"))
        self.pid=self.cap.studio.create_project("Audio publication","Real stems")["id"]
        self.length=RATE*2
        self.sources={}
        for sid,value in (("voice",1000),("air",200)):
            path=self.root/(sid+".wav")
            with wave.open(str(path),"wb") as out:
                out.setnchannels(2);out.setsampwidth(2);out.setframerate(RATE)
                out.writeframes(struct.pack("<hh",value,-value)*self.length)
            self.sources[sid]=path
        self.plan={"stems":[
            {"stem_id":"voice","kind":"dialogue","clips":[clip(self.length)]},
            {"stem_id":"air","kind":"ambience","clips":[clip(self.length,gain=500)]},
        ]}
        self.chunkdir=self.root/"chunks"
        self.output=self.root/"exports"

    def tearDown(self):
        self.temp.cleanup()

    def build(self):
        run_chunked_preview(self.plan,self.sources,self.length,self.chunkdir)

    def test_publishes_three_independent_wavs_and_reopens(self):
        self.build()
        sourcehash={sid:hashlib.sha256(path.read_bytes()).hexdigest()
                    for sid,path in self.sources.items()}
        result=publish_chunked_wavs(self.cap,self.pid,"mix",self.plan,self.sources,
                                    self.length,self.chunkdir,self.output)
        self.assertEqual(result["wav_count"],3)
        self.assertFalse(result["picture_bound"])
        for sid,path in self.sources.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),sourcehash[sid])
        with wave.open(str(self.output/"mix_preview.wav"),"rb") as r:
            self.assertEqual(r.getnframes(),self.length)
            self.assertEqual(struct.unpack("<hh",r.readframes(1)),(1100,-1100))
        with wave.open(str(self.output/"stem_air.wav"),"rb") as r:
            self.assertEqual(struct.unpack("<hh",r.readframes(1)),(100,-100))
        reopened=DigitalCapture(Studio(self.root/"studio.sqlite3"))
        verified=verify_published_wavs(reopened,self.pid,"mix",self.plan,self.sources,
                                       self.length,self.chunkdir,self.output)
        self.assertEqual(verified["status"],"VERIFIED_UNAPPROVED_INDEXED_WAV_PREVIEW")
        with self.assertRaises(RuntimeError):
            publish_chunked_wavs(reopened,self.pid,"mix",self.plan,self.sources,
                                 self.length,self.chunkdir,self.root/"another")

    def test_rejects_partial_render_without_publishing(self):
        run_chunked_preview(self.plan,self.sources,self.length,self.chunkdir,
                            max_new_chunks=1)
        with self.assertRaisesRegex(RuntimeError,"completed"):
            publish_chunked_wavs(self.cap,self.pid,"partial",self.plan,self.sources,
                                 self.length,self.chunkdir,self.output)
        with self.assertRaises(KeyError):
            self.cap.index.read_revision(self.pid,"partial")

    def test_tamper_output_rejected(self):
        self.build()
        publish_chunked_wavs(self.cap,self.pid,"mix",self.plan,self.sources,
                             self.length,self.chunkdir,self.output)
        path=self.output/"stem_voice.wav"
        with path.open("r+b") as raw:
            raw.seek(100)
            raw.write(b"BAD!")
        with self.assertRaisesRegex(RuntimeError,"changed"):
            verify_published_wavs(DigitalCapture(Studio(self.root/"studio.sqlite3")),
                                  self.pid,"mix",self.plan,self.sources,
                                  self.length,self.chunkdir,self.output)

    def test_source_mutation_rejected(self):
        self.build()
        with (self.sources["voice"]).open("r+b") as raw:
            raw.seek(200)
            raw.write(b"CHNG")
        with self.assertRaisesRegex(RuntimeError,"changed"):
            publish_chunked_wavs(self.cap,self.pid,"mix",self.plan,self.sources,
                                 self.length,self.chunkdir,self.output)


if __name__=="__main__":
    unittest.main()
