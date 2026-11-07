"""Batch 3 real OpenEXR FLOAT32 ACEScg source/movie interchange acceptance.

Must use official OpenEXR native bindings and real pinned OCIO+OpenUSD.
A DERIVED image sequence and sound are not original frame authority.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import wave

import numpy as np
import OpenEXR
import test_nvp_source_linear_aces_scene as fixture
from backend.nvp_final_2d_native import (
    Approved2DPackage,FORMAT_EXR)
from backend.nvp_native_scene_linear_exr import (
    NativeSceneLinearEXR,FORMAT)
from backend.nvp_native_cpu_raster import NativeSourceRaster
from backend.nvp_native_avi_delivery import deliver_avi


class SceneLinearEXRTests(unittest.TestCase):
    def setUp(self):
        fixture.NativeSourceLinearACESAcceptance.setUp(self)
        tmp=tempfile.TemporaryDirectory(prefix="nvp-acescg-exr-test-")
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.grants=[]
        self.inputs={
            "grade_id":"SourceColor001",
            "revision":1,"document_sha256":self.grade["document_sha256"],
            "config_sha256":self.policy["configuration_sha256"],
        }

    def source(self,destination,*,take_sha=None,config_sha=None):
        return NativeSceneLinearEXR(self.index).write(
            self.pid,"SourceColorTake",
            take_sha or self.take["document_sha256"],
            "SourceColor001",1,self.grade["document_sha256"],
            tick=0,camera_path="/World/Camera",
            expected_config_sha256=config_sha or
                self.policy["configuration_sha256"],
            output_file=destination)

    def test_real_float32_scene_linear_exr_has_exact_sha_and_ocio(self):
        path=self.root/"source0000001.exr"
        source_take=self.take["document_sha256"]
        receipt=self.source(path)
        self.assertEqual(receipt["format"],FORMAT)
        self.assertEqual(receipt["status"],
                         "UNMASTERED_SOURCE_LINEAR_ACESCG_EXR")
        self.assertEqual(receipt["working_space"],"ACEScg")
        self.assertEqual(receipt["float_bits_per_component"],32)
        self.assertEqual(receipt["output_exr_sha256"],
                         hashlib.sha256(path.read_bytes()).hexdigest())
        with OpenEXR.File(str(path)) as exr:
            values=exr.channels()["RGB"].pixels
            self.assertEqual(values.dtype,np.float32)
            self.assertEqual(values.shape,(360,640,3))
            self.assertGreater(float(values.max()),0)
            self.assertEqual(exr.header()["nvpOriginalTakeSha"],source_take)
            self.assertEqual(exr.header()["nvpOCIOConfigSha"],
                             self.policy["configuration_sha256"])
            self.assertEqual(exr.header()["nvpColorSpace"],"ACEScg")
        self.assertEqual(self.index.read_revision(
            self.pid,"SourceColorTake",1)["document_sha256"],source_take)
        self.assertFalse(receipt["professional_master_approved"])
        self.assertFalse(receipt["ffmpeg_used"])

    def test_interrupted_acescg_original_source_export_resumes_without_rerender(self):
        from unittest.mock import patch
        from backend.nvp_native_scene_linear_exr import NativeSceneLinearEXR
        engine=Approved2DPackage(
            self.index,native_creator_approval=lambda _:True,
            render_png=NativeSourceRaster(self.index,self.pid).render_png)
        take_sha=self.take["document_sha256"]
        kwargs=dict(
            listener_path="/World/Camera",fps_num=24,fps_den=1,
            linear_exr_grade=self.inputs,resumable=True)
        old=NativeSceneLinearEXR.write
        first=[0]
        def interrupt(obj,*args,**kw):
            first[0]+=1
            if first[0]==4:
                raise RuntimeError("Simulated host crash before derived frame receipt")
            return old(obj,*args,**kw)
        with patch.object(NativeSceneLinearEXR,"write",interrupt):
            with self.assertRaisesRegex(RuntimeError,"Simulated host crash"):
                engine.export(self.pid,"SourceColorTake",take_sha,
                    "RecoveredACEScgFilm",self.root,**kwargs)
        incomplete=self.root/".nvp-color-work-RecoveredACEScgFilm"
        self.assertTrue(incomplete.is_dir())
        self.assertEqual(len(list((incomplete/"pictures").glob("*.exr"))),3)
        old_sha=hashlib.sha256(
            (incomplete/"pictures"/"0000001.exr").read_bytes()).hexdigest()
        resumed=[0]
        def count(obj,*args,**kw):
            resumed[0]+=1
            return old(obj,*args,**kw)
        with patch.object(NativeSceneLinearEXR,"write",count):
            result=engine.export(self.pid,"SourceColorTake",take_sha,
                "RecoveredACEScgFilm",self.root,**kwargs)
        self.assertEqual(resumed,[21])
        self.assertEqual(result["status"],"DERIVED_2D_PACKAGE")
        target=Path(result["directory"])
        self.assertFalse(incomplete.exists())
        self.assertEqual(hashlib.sha256(
            (target/"pictures"/"0000001.exr").read_bytes()).hexdigest(),
            old_sha)
        self.assertFalse((target/"owner.lock").exists())
        self.assertEqual(self.index.read_revision(
            self.pid,"SourceColorTake",1)["document_sha256"],take_sha)

    def test_explicit_native_cancel_preserves_unapproved_derived_progress(self):
        engine=Approved2DPackage(
            self.index,native_creator_approval=lambda _:True,
            render_png=NativeSourceRaster(self.index,self.pid).render_png)
        calls=[0]
        def stop_after_first_two():
            calls[0]+=1
            return calls[0]>=3
        with self.assertRaises(InterruptedError):
            engine.export(self.pid,"SourceColorTake",
                self.take["document_sha256"],"CancelUnmastered",self.root,
                listener_path="/World/Camera",
                linear_exr_grade=self.inputs,resumable=True,
                cancel_check=stop_after_first_two)
        workspace=self.root/".nvp-color-work-CancelUnmastered"
        self.assertTrue(workspace.is_dir())
        self.assertFalse((self.root/"NVP2D_CancelUnmastered").exists())
        self.assertEqual(len(list((workspace/"pictures").glob("*.exr"))),2)
        self.assertFalse(self.index.read_revision(
            self.pid,"SourceColorTake",1)["data"].get("master_approved",False))

    def test_published_source_package_registers_native_receipt_and_reopens_for_readiness(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import patch
        from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge
        from backend.nvp_native_cinema_master_gate import FORMAT as READY_FORMAT
        package=Approved2DPackage(
            self.index,native_creator_approval=lambda _:True,
            render_png=NativeSourceRaster(self.index,self.pid).render_png)
        name="AuthenticNativeSource"
        receipt=package.export(
            self.pid,"SourceColorTake",self.take["document_sha256"],
            name,self.root,
            listener_path="/World/Camera",
            fps_num=24,fps_den=1,
            linear_exr_grade=self.inputs,resumable=True)
        record=self.index.read_revision(
            self.pid,"NativePackage_"+name,1)
        self.assertEqual(record["kind"],"presentation")
        self.assertEqual(record["document_sha256"],
                         receipt["native_presentation_receipt_sha256"])
        self.assertEqual(record["data"]["manifest_sha256"],
                         receipt["manifest_sha256"])
        self.assertFalse(record["data"]["dcp_delivered"])
        self.assertEqual(len(record["dependencies"]),2)
        class Window:
            def get_current_url(self):return "http://127.0.0.1:7777/"
            def create_confirmation_dialog(self,title,message):return True
            def create_file_dialog(self,dialog):
                return [receipt["directory"]]
        bridge=TrustedDesktopCameraBridge(
            self.index,origin="http://127.0.0.1:7777")
        bridge._attach_window(Window())
        self.addCleanup(bridge._close)
        with patch.dict(sys.modules,{"webview":SimpleNamespace(
                FileDialog=SimpleNamespace(FOLDER=123))}):
            check=bridge.data_av_cinema_readiness({
                "project_id":self.pid,
                "take_id":"SourceColorTake",
                "take_document_sha256":self.take["document_sha256"],
                "target":"SMPTE_2K_FLAT_24"})
        self.assertEqual(check["format"],READY_FORMAT)
        self.assertTrue(check["authenticated_approved_source_derivative"])
        self.assertEqual(check["authenticated_native_presentation_sha256"],
                         record["document_sha256"])
        self.assertTrue(check["source_integrity_verified"])
        self.assertFalse(check["dcp_delivered"])
        self.assertIn("native_SMPTE_2K_XYZ_12bit_JPEG2000_encoder",
                      check["required_master_color_and_delivery_capabilities"])

    def test_invalid_source_or_config_and_existing_destination_refused(self):
        path=self.root/"refuse.exr"
        with self.assertRaises(RuntimeError):
            self.source(path,take_sha="f"*64)
        self.assertFalse(path.exists())
        with self.assertRaises(RuntimeError):
            self.source(path,config_sha="f"*64)
        self.assertFalse(path.exists())
        self.source(path)
        with self.assertRaises(PermissionError):
            self.source(path)

    def test_approved_real_acescg_sequence_has_full_float_pcm_and_no_avi(self):
        take_sha=self.take["document_sha256"]
        output=Approved2DPackage(
            self.index,native_creator_approval=lambda scope:
                self.grants.append(scope) is None,
            render_png=NativeSourceRaster(self.index,self.pid).render_png
        ).export(
            self.pid,"SourceColorTake",take_sha,
            "ACEScgOriginalSource01",self.root,
            listener_path="/World/Camera",fps_num=24,fps_den=1,
            linear_exr_grade=self.inputs)
        self.assertEqual(output["status"],"DERIVED_2D_PACKAGE")
        self.assertEqual(output["color_pipeline"],
                         "ocio_scene_linear_acescg_exr32_unmastered")
        self.assertEqual(output["picture_format"],"exr")
        self.assertEqual(output["pixel_bit_depth"],32)
        dir=Path(output["directory"])
        manifest=json.loads((dir/"manifest.json").read_text("utf8"))
        self.assertEqual(manifest["format"],FORMAT_EXR)
        self.assertEqual(manifest["picture_format"],"exr")
        self.assertEqual(manifest["original_take_sha256"],take_sha)
        self.assertEqual(manifest["output_picture_count"],24)
        self.assertEqual(len(manifest["acescg_source_receipts"]),24)
        self.assertEqual(manifest["linear_exr_grade"]["config_sha256"],
                         self.policy["configuration_sha256"])
        self.assertTrue(all(
            row["exr_file"].endswith(".exr") and row["pixel_type"]=="FLOAT32"
            for row in manifest["pictures"]))
        self.assertEqual(self.grants[0]["aces_config_sha256"],
                         self.policy["configuration_sha256"])
        frame=dir/"pictures"/"0000001.exr"
        with OpenEXR.File(str(frame)) as exr:
            self.assertEqual(exr.channels()["RGB"].pixels.dtype,np.float32)
        with wave.open(str(dir/"soundtrack.wav"),"rb") as wav:
            self.assertEqual(wav.getframerate(),48000)
            self.assertEqual(wav.getnframes(),48000)
        with self.assertRaises(RuntimeError):
            deliver_avi(
                dir,self.root/"lossy8bit.avi",
                expected_take_sha256=take_sha,
                approve_delivery=lambda _:True)
        self.assertFalse((self.root/"lossy8bit.avi").exists())
        self.assertEqual(self.index.read_revision(
            self.pid,"SourceColorTake",1)["document_sha256"],take_sha)
        self.assertFalse(manifest["conventional_single_file_master"])


if __name__=="__main__":
    unittest.main()
