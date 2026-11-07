"""Native WO4 disk-streamed audio: byte parity, no-clobber, source custody."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from io import BytesIO
import unittest
import wave

from backend.nvp_wo4_pcm_stream import stream_master_pcm24_candidate
from backend.nvp_wo4_pcm_master import master_pcm24_candidate


class StreamedPCM24Acceptance(unittest.TestCase):
    def setUp(self):
        self.temporary=TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name).resolve()
        self.source=self.root/"original_source.pcm"
        self.export=self.root/"approved_export"
        self.export.mkdir()
        samples=[-200001,1,123456,-1,0,200000]
        self.raw=b"".join(n.to_bytes(3,"little",signed=True)
                          for n in samples)*2000
        self.source.write_bytes(self.raw)
        self.original_sha=sha256(self.raw).hexdigest()
        self.take_sha="a"*64

    def stream(self,**changes):
        args=dict(source_path=self.source,
                  source_sha256=self.original_sha,
                  original_take_sha256=self.take_sha,
                  cinema_frames=3,channel_layout="stereo",
                  output_root=self.export,approve=lambda _:True)
        args.update(changes)
        return stream_master_pcm24_candidate(**args)

    def test_streamed_identity_is_exact_legacy_master_and_source_unchanged(self):
        result=self.stream()
        wav=Path(result["destination"])
        with wave.open(str(wav),"rb") as stream:
            data=stream.readframes(stream.getnframes())
            self.assertEqual(stream.getnframes(),6000)
            self.assertEqual(stream.getframerate(),48000)
        self.assertEqual(data,self.raw)
        self.assertEqual(result["master_pcm_sha256"],self.original_sha)
        self.assertEqual(result["wav_file_sha256"],
                         sha256(wav.read_bytes()).hexdigest())
        self.assertEqual(self.source.read_bytes(),self.raw)
        self.assertTrue(result["whole_reel_loaded_into_ram"] is False)
        self.assertFalse(result["production_audio_accepted"])
        self.assertFalse(any(p.name.startswith(".nvp-wo4-")
                             for p in self.export.iterdir()))

    def test_streamed_gain_matches_in_memory_integer_transform(self):
        result=self.stream(gain_numerator=1,gain_denominator=2)
        expected=master_pcm24_candidate(
            self.raw,source_sha256=self.original_sha,
            original_take_sha256=self.take_sha,cinema_frames=3,
            channel_layout="stereo",gain_numerator=1,
            gain_denominator=2,creator_approved=True)
        self.assertEqual(Path(result["destination"]).read_bytes(),
                         expected["wav_bytes"])
        self.assertEqual(result["master_pcm_sha256"],
                         expected["master_pcm_sha256"])
        self.assertEqual(self.source.read_bytes(),self.raw)

    def test_denial_and_invalid_digest_have_no_export(self):
        denied=self.stream(approve=lambda _:False)
        self.assertEqual(denied["status"],"DENIED")
        with self.assertRaises(PermissionError):
            self.stream(source_sha256="f"*64)
        self.assertEqual(list(self.export.iterdir()),[])

    def test_clipping_refuses_and_cleans_stage(self):
        loud=(8388607).to_bytes(3,"little",signed=True)
        self.raw=loud*12000
        self.source.write_bytes(self.raw)
        self.original_sha=sha256(self.raw).hexdigest()
        with self.assertRaisesRegex(ValueError,"clips"):
            self.stream(gain_numerator=2)
        self.assertEqual(list(self.export.iterdir()),[])
        self.assertEqual(self.source.read_bytes(),self.raw)

    def test_existing_creator_files_survive_multiple_exports(self):
        protected=self.export/"PCM24_creator.wav"
        protected.write_bytes(b"creator-original")
        one=self.stream()
        two=self.stream()
        self.assertNotEqual(one["destination"],two["destination"])
        self.assertEqual(protected.read_bytes(),b"creator-original")
        self.assertTrue(Path(one["destination"]).is_file())
        self.assertTrue(Path(two["destination"]).is_file())

    def test_rejects_linked_source_or_export_root(self):
        link=self.root/"linked_source.pcm"
        try:
            link.symlink_to(self.source)
        except (OSError,NotImplementedError):
            self.skipTest("Symlink not permitted on test host")
        with self.assertRaises(PermissionError):
            self.stream(source_path=link)


if __name__=="__main__":
    unittest.main()
