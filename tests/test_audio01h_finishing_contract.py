"""AUDIO-01H.2/.3 isolated contract tests: no implicit approval or source edit."""
from __future__ import annotations
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import wave

from backend.nvp_audio01e_wav_publication import FORMAT as WAV_FORMAT
from backend.nvp_audio01h_stem_revision import automate_stem
from backend.nvp_audio01h_mix_decision import record_mix_decision


class FakeIndex:
    def __init__(self, root):
        self.root = Path(root)
        self.rows = {}
        self.saved = {}
        self.rows["original"] = {
            "kind": "audio", "document_sha256": "a" * 64,
            "data": {"format": WAV_FORMAT, "final_mix": False,
                     "total_samples_per_channel": 4,
                     "wav_outputs": [{"stem_id": None, "filename": "stem_dialogue.wav",
                                      "sha256": ""}]}
        }

    def read_revision(self, project, obj, revision=None):
        if obj not in self.rows:
            raise KeyError(obj)
        return self.rows[obj]

    def verify_media_file(self, project, sha, media_type):
        if sha in self.saved:
            return {"path": str(self.saved[sha])}
        if sha == self.rows["original"]["data"]["wav_outputs"][0]["sha256"]:
            return {"path": str(self.root / "stem_dialogue.wav")}
        raise RuntimeError("Missing media")

    def put_media_file(self, project, path, media_type):
        data = Path(path).read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        self.saved[sha] = Path(path)
        return {"sha256": sha}

    def register_revision(self, project, obj, kind, doc, *,
                          expected_revision=0, dependencies=None):
        prior = self.rows.get(obj)
        current = prior["revision"] if prior else 0
        if current != expected_revision:
            raise RuntimeError("Concurrent decision revision")
        sha = hashlib.sha256(repr(doc).encode()).hexdigest()
        self.rows[obj] = {
            "kind": kind, "revision": current + 1,
            "document_sha256": sha, "data": doc}
        return {"revision": current + 1, "document_sha256": sha}


class AudioFinishingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.wav = self.root / "stem_dialogue.wav"
        with wave.open(str(self.wav), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(48000)
            w.writeframes((1024).to_bytes(2, "little", signed=True) * 8)
        self.index = FakeIndex(self.root)
        self.index.rows["original"]["data"]["wav_outputs"][0]["sha256"] = (
            hashlib.sha256(self.wav.read_bytes()).hexdigest())
        self.capture = Mock(index=self.index)
        self.dest = self.root / "processed.wav"

    def make_stem(self):
        return automate_stem(self.capture, "project", "original", None,
                             [[0, 0], [3, 0]], self.root, self.dest,
                             "automated", authorize=lambda _: True)

    def test_stem_requires_authorization_and_never_mutates_input(self):
        before = self.wav.read_bytes()
        with self.assertRaises(PermissionError):
            automate_stem(self.capture, "project", "original", None,
                          [[0, 0], [3, 0]], self.root, self.dest, "automated",
                          authorize=lambda _: False)
        self.assertFalse(self.dest.exists())
        answer = self.make_stem()
        self.assertEqual(answer["status"], "UNAPPROVED_AUTOMATED_STEM")
        self.assertEqual(self.wav.read_bytes(), before)
        self.assertFalse(self.index.rows["automated"]["data"]["director_approved"])
        with self.assertRaises(RuntimeError):
            self.make_stem()

    def test_decision_denies_forged_evidence_and_unauthorized_accept(self):
        self.make_stem()
        evidence = {
            "format": "nvp.audio01h.loudness_evidence.v1",
            "wav_sha256": self.index.rows["automated"]["data"]["automated_wav_sha256"],
            "normalized": False, "final_mix": False, "director_approved": False,
            "integrated_lufs": -22.0, "true_peak_dbtp": -12.0,
            "loudness_range_lu": 0.0
        }
        with patch("backend.nvp_audio01h_mix_decision.analyze_wav",
                   return_value=dict(evidence)):
            with self.assertRaises(PermissionError):
                record_mix_decision(self.capture, "project", "automated", "decision",
                                    evidence, decision="ACCEPT", creator_event="event",
                                    authorize=lambda *_: False)
            accepted = record_mix_decision(
                self.capture, "project", "automated", "decision",
                evidence, decision="ACCEPT", creator_event="human_accept",
                authorize=lambda event, scope: event == "human_accept")
            self.assertTrue(accepted["final_mix"])
            self.assertFalse(accepted["final_master"])
            revoked = record_mix_decision(
                self.capture, "project", "automated", "decision",
                evidence, decision="REVOKE", creator_event="human_revoke",
                authorize=lambda event, scope: event == "human_revoke")
            self.assertFalse(revoked["final_mix"])
            self.assertEqual(revoked["revision"], 2)

    def test_forged_loudness_never_reaches_creator_authorization(self):
        self.make_stem()
        wrong = {
            "format": "nvp.audio01h.loudness_evidence.v1",
            "wav_sha256": "0" * 64, "normalized": False,
            "final_mix": False, "director_approved": False,
            "integrated_lufs": -23.0, "true_peak_dbtp": -2.0,
            "loudness_range_lu": 1.0,
        }
        callback = Mock(return_value=True)
        with self.assertRaises(RuntimeError):
            record_mix_decision(self.capture, "project", "automated", "decision",
                                wrong, decision="ACCEPT", creator_event="human",
                                authorize=callback)
        callback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
