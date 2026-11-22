"""Portable SOURCE CONTRACT tests. Synthetic receipts are NEVER hardware evidence."""
import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from backend.nvp_post01f_ltx_native_handoff import (
    WIRE, RESULT, validate_intent, admit_picture, ProtectedLtxHandoff,
    MAX_PLAN, _canonical,
)

H = lambda x: hashlib.sha256(x).hexdigest()
P = "a"*32
S = "b"*64


def intent(**changes):
    doc = dict(project_id=P, take_sha256=S, layout_sha256=S,
        look_sha256=S, conditioning_sha256=S, model_stack_sha256=S,
        display_frames=120, model_frames=121, fps=24,
        width=768, height=448, seed=22, camera_id="cam_one")
    doc.update(changes)
    return doc


class NativeHandoffSourceContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.job = "ltx_"+"1"*24
        self.scope = dict(job_id=self.job, project_id=P,
            plan_sha256=S, model_stack_sha256=S)
        self.os = dict(scm_authenticated_receipt_verified=True,
            job_id=self.job,plan_sha256=S,picture_sha256=S,process_tree_custody_verified=True,
            appcontainer_zero_network_caps_verified=True,
            wfp_no_egress_verified=True, efs_verified=True,
            scm_receipt_sha256="6"*64)
        self.gpu = dict(model_loaded=True, inference_executed=True,
            gpu_execution_verified=True, model_stack_sha256=S)
        self.plan = {"format":WIRE, **intent(), "job_id":self.job}
        (self.root/"plan.json").write_bytes(_canonical(self.plan))
        self.scope["plan_sha256"] = H(_canonical(self.plan))
        self.os["plan_sha256"] = self.scope["plan_sha256"]
        (self.root/"picture.mp4").write_bytes(b"not-real-video: SOURCE-CONTRACT-ONLY")
        self.receipt = dict(format=RESULT, job_id=self.job, project_id=P,
            plan_sha256=self.scope["plan_sha256"], model_stack_sha256=S,
            picture_sha256=H((self.root/"picture.mp4").read_bytes()),
            picture_frames=120, fps=24, width=768, height=448,
            audio_generated=False)
        self.os["picture_sha256"] = self.receipt["picture_sha256"]
        self.decoder = lambda path, plan, sha: {
            "independently_decoded":True,"picture_sha256":sha,
            "presented_frames":120,"fps":24,"pts_verified":True,"audio_streams":0}
        for name in ("journal.json", "layout.mp4", "look.png", "conditioning.json", "stdout.log", "stderr.log"):
            (self.root/name).write_bytes(b"test")
        self.write_receipt()

    def write_receipt(self):
        (self.root/"result.json").write_text(json.dumps(self.receipt), encoding="utf8")

    def admit(self, **changes):
        args=dict(root=self.root, **self.scope, picture_verifier=self.decoder,
            os_witness=self.os, model_witness=self.gpu)
        args.update(changes)
        return admit_picture(**args)

    def test_exact_120_to_121_frame_mapping(self):
        self.assertEqual(validate_intent(intent())["model_frames"],121)

    def test_reject_malformed_grids_and_types(self):
        for changes in ({"model_frames":120},{"display_frames":121},
                        {"width":770},{"fps":23},{"seed":True},
                        {"camera_id":"../stranger"},{"project_id":"other"}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                validate_intent(intent(**changes))

    def test_reject_unreviewed_fields_and_injected_paths(self):
        with self.assertRaises(ValueError):
            validate_intent(intent(executable="C:/malicious.exe"))

    def test_quarantine_is_not_film_publication(self):
        row=self.admit()
        self.assertEqual(row["state"],"PICTURE_VERIFIED_UNAPPROVED")
        self.assertIs(row["creator_approved"],False)
        self.assertIs(row["publishable"],False)

    def test_missing_os_security_witness_refuses(self):
        for key in self.os:
            witness=dict(self.os)
            witness[key]=False
            with self.subTest(key=key),self.assertRaises(PermissionError):
                self.admit(os_witness=witness)

    def test_missing_native_model_gpu_witness_refuses(self):
        for key in ("model_loaded","inference_executed","gpu_execution_verified"):
            witness=dict(self.gpu)
            witness[key]=False
            with self.subTest(key=key),self.assertRaises(PermissionError):
                self.admit(model_witness=witness)

    def test_worker_receipt_drift_refuses(self):
        for key,bad in (("job_id","other"),("project_id","c"*32),
                        ("picture_frames",121),("audio_generated",True),
                        ("model_stack_sha256","e"*64)):
            old=self.receipt[key]
            self.receipt[key]=bad
            self.write_receipt()
            with self.subTest(key=key),self.assertRaises(PermissionError):
                self.admit()
            self.receipt[key]=old
        self.write_receipt()

    def test_unreviewed_audio_side_output_refuses(self):
        (self.root/"generated_audio.wav").write_bytes(b"wav")
        with self.assertRaises(PermissionError):
            self.admit()

    def test_picture_mutation_refuses(self):
        (self.root/"picture.mp4").write_bytes(b"tampered")
        with self.assertRaises(PermissionError):
            self.admit()

    def test_generated_audio_track_refuses(self):
        with self.assertRaises(PermissionError):
            self.admit(picture_verifier=lambda p,s,h: {
                "independently_decoded":True,"picture_sha256":h,
                "presented_frames":120,"fps":24,"pts_verified":True,"audio_streams":1})

    def test_missing_pts_verification_refuses(self):
        with self.assertRaises(PermissionError):
            self.admit(picture_verifier=lambda p,s,h: {
                "independently_decoded":True,"picture_sha256":h,
                "presented_frames":120,"fps":24,"pts_verified":False})

    def test_ltx_bootstrap_never_launches_on_linux(self):
        code=self.root/"installed"
        code.mkdir()
        exe=code/"reviewed.exe"
        exe.write_bytes(b"installed-exe")
        root=self.root/"runtime"
        root.mkdir()
        host=ProtectedLtxHandoff(runtime_root=root, installed_bootstrap=exe,
            bootstrap_sha256=H(exe.read_bytes()), model_stack_sha256=S,
            approved_code_roots=(code,), creator_approve=lambda scope:True,
            take_verify=lambda source:True, os_verify=lambda s,p: self.os, model_verify=lambda s,r: self.gpu,
            picture_verify=self.decoder)
        with patch("backend.nvp_post01f_ltx_native_handoff.os.name","posix"):
            with self.assertRaises(PermissionError):
                host.run(intent=intent(), layout=b"whatever", look=b"whatever",conditioning=b"{}")

    def test_interrupted_journal_never_promotes(self):
        code=self.root/"installed"
        code.mkdir()
        exe=code/"reviewed.exe"
        exe.write_bytes(b"installed-exe")
        root=self.root/"runtime"
        root.mkdir()
        host=ProtectedLtxHandoff(runtime_root=root, installed_bootstrap=exe,
            bootstrap_sha256=H(exe.read_bytes()), model_stack_sha256=S,
            approved_code_roots=(code,), creator_approve=lambda scope:True,
            take_verify=lambda source:True, os_verify=lambda s,p: self.os, model_verify=lambda s,r: self.gpu,
            picture_verify=self.decoder)
        jobdir=root/("ltx_"+"9"*24)
        jobdir.mkdir()
        (jobdir/"journal.json").write_text(json.dumps({"state":"RUNNING","publishable":False}),encoding="utf8")
        self.assertEqual(host.reconcile(),[jobdir.name])
        self.assertEqual(json.loads((jobdir/"journal.json").read_text())["state"],"INTERRUPTED_UNVERIFIED")


if __name__=="__main__":
    unittest.main()
