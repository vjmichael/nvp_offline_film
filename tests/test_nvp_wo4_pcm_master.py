"""WO4-01 deterministic cinema PCM candidate and hostile source rejection."""
import hashlib
import io
import unittest
import wave
from backend.nvp_wo4_pcm_master import master_pcm24_candidate

TAKE="b"*64


def encode_sample(v):
    return int(v).to_bytes(3,"little",signed=True)


def build_pcm(frames,channels,sequence):
    pattern=b"".join(encode_sample(x) for x in sequence)
    repeat=(frames*2000*channels+len(sequence)-1)//len(sequence)
    return (pattern*repeat)[:frames*2000*channels*3]


class WO4PCM(unittest.TestCase):
    def master(self,src,**kwargs):
        opts=dict(source_pcm=src,source_sha256=hashlib.sha256(src).hexdigest(),
                  original_take_sha256=TAKE,cinema_frames=3,
                  channel_layout="stereo",creator_approved=True)
        opts.update(kwargs)
        return master_pcm24_candidate(**opts)

    def test_identity_stereo_is_bit_exact_and_source_immutable(self):
        original=build_pcm(3,2,[-90000,0,50000,838860])
        baseline=bytes(original)
        out=self.master(original)
        self.assertEqual(original,baseline)
        self.assertEqual(out["master_pcm_sha256"],out["source_pcm_sha256"])
        self.assertEqual(out["channel_order"],["L","R"])
        with wave.open(io.BytesIO(out["wav_bytes"]),"rb") as reader:
            self.assertEqual(reader.getnframes(),6000)
            self.assertEqual(reader.getframerate(),48000)
            self.assertEqual(reader.getsampwidth(),3)
            self.assertEqual(reader.getnchannels(),2)
            self.assertEqual(reader.readframes(6000),original)
        self.assertFalse(out["production_audio_accepted"])

    def test_rational_gain_and_negative_rounding_are_deterministic(self):
        original=build_pcm(3,2,[1,-1,3,-3])
        out=self.master(original,gain_numerator=1,gain_denominator=2)
        with wave.open(io.BytesIO(out["wav_bytes"]),"rb") as reader:
            data=reader.readframes(reader.getnframes())
        self.assertEqual([int.from_bytes(data[i:i+3],"little",signed=True)
                          for i in range(0,12,3)],[1,-1,2,-2])

    def test_clipping_rejected_not_automatically_normalized(self):
        source=build_pcm(3,2,[8388607,-8388608])
        with self.assertRaisesRegex(ValueError,"clip"):
            self.master(source,gain_numerator=2)

    def test_wrong_pcm_length_and_unapproved_source_rejected(self):
        source=build_pcm(3,2,[100])
        with self.assertRaises(ValueError):
            self.master(source[:-3])
        with self.assertRaises(PermissionError):
            self.master(source,creator_approved=False)
        with self.assertRaises(PermissionError):
            self.master(source,source_sha256="0"*64)

    def test_six_and_eight_channel_order_are_explicit(self):
        for layout,channels in (("5.1",6),("7.1",8)):
            with self.subTest(layout=layout):
                source=build_pcm(3,channels,[1000,-2000])
                out=self.master(source,channel_layout=layout)
                self.assertEqual(len(out["channel_order"]),channels)
                self.assertEqual(out["master_pcm_sha256"],
                                 out["source_pcm_sha256"])


if __name__=="__main__":
    unittest.main()
