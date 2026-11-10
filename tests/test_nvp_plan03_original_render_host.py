"""PLAN-03 source-bound real PNG rendering across protected native worker.

The approved selection is a separate, nonexecuting native OS review.
Unit tests never count synthetic approval as a witnessed human action.
On Windows, the positive test uses an actual Job Object process and an
independently reopened original USD/SQLite scene. Linux strict cgroup-v2
execution requires the separately delegated systemd native witness.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from test_nvp_plan02d_derived_raster import ActualSourceRasterTests
from backend.nvp_plan02d_render_queue import DurableRenderIntentionQueue
from backend.nvp_plan03_original_render_host import NativeOriginalSceneRender
from tools.nvp_plan03_original_render_worker import render as render_worker
from backend.nvp_plan02d_source_selection import ExactSourceWindowSelector
from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex


class NativeSourceRenderTests(unittest.TestCase):
    def setUp(self):
        ActualSourceRasterTests.setUp(self)
        tmp=tempfile.TemporaryDirectory(prefix="nvp-plan03-render-work-")
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.queue=DurableRenderIntentionQueue(self.index,ask_native=lambda scope:True)
        self.queue.enqueue(self.pid,"OriginalSceneDeriveOne",self.request)
        self.review=self.queue.review(self.pid,"OriginalSceneDeriveOne",1)
        self.approvals=[]
        self.approve=True

    def host(self):
        return NativeOriginalSceneRender(
            self.index,self.queue,workspace=self.root,ask_native=self._ask,
            memory_mb=1024)

    def _ask(self,scope):
        self.approvals.append(scope)
        return self.approve

    def test_refused_second_native_authorization_never_starts_renderer(self):
        self.approve=False
        host=self.host()
        with patch("backend.nvp_plan03_original_render_host.launch_contained") as launch:
            with self.assertRaisesRegex(PermissionError,"refused"):
                host.render_once(self.pid,"OriginalSceneDeriveOne",2,
                    self.review["selection_sha256"],T//3)
            launch.assert_not_called()
        self.assertFalse(list(self.root.iterdir()))
        self.assertEqual(self.index.read_revision(self.pid,"RasterTake",1)[
            "document_sha256"],self.take_sha)
        with self.assertRaises(PermissionError):
            host.render_once(self.pid,"OriginalSceneDeriveOne",2,
                self.review["selection_sha256"],T//3)

    def test_stale_and_unreviewed_job_denied_before_native_dialog(self):
        host=self.host()
        with self.assertRaises(PermissionError):
            host.render_once(self.pid,"OriginalSceneDeriveOne",2,
                "0"*64,T//3)
        self.assertEqual(self.approvals,[])
        restarted=DurableRenderIntentionQueue(self.index,ask_native=lambda scope:True)
        after=NativeOriginalSceneRender(
            self.index,restarted,workspace=self.root,ask_native=self._ask)
        with self.assertRaises(PermissionError):
            after.render_once(self.pid,"OriginalSceneDeriveOne",2,
                self.review["selection_sha256"],T//3)
        self.assertEqual(self.approvals,[])

    def test_genuine_original_usd_native_worker_output_no_source_mutation(self):
        # This is a separate actual original USD raster computation, not an
        # injected PNG return or mock fake renderer.
        scope=ExactSourceWindowSelector(self.index).preview(self.pid,self.request)
        manifest={
            "format":"nvp.plan03.native_original_source_render_worker.v1",
            "project_id":self.pid,
            "request":self.request,
            "selection_sha256":scope["selection_sha256"],
            "source_tick":T//3,
            "db_path":str(self.studio.db_path.resolve()),
            "take_document_sha256":self.take_sha,
        }
        work=self.root/"real_derived"
        work.mkdir()
        source=work/"source_manifest.json"
        source.write_text(json.dumps(manifest))
        receipt=render_worker(source)
        self.assertEqual(receipt["status"],"DERIVED_OPENUSD_IMAGE_ONLY")
        self.assertFalse(receipt["ffmpeg_used"])
        with Image.open(work/"derived_source.png") as image:
            self.assertEqual(image.size,(640,360))
            self.assertEqual(image.format,"PNG")
            self.assertIsNotNone(image.getbbox())
        self.assertEqual(self.index.read_revision(self.pid,"RasterTake",1)[
            "document_sha256"],self.take_sha)
        with self.assertRaises(FileExistsError):
            render_worker(source)

    @unittest.skipUnless(os.name=="nt","Windows actual Job Object; Linux needs real delegated cgroup witness")
    def test_windows_real_os_worker_derived_image_and_one_use(self):
        result=self.host().render_once(
            self.pid,"OriginalSceneDeriveOne",2,self.review["selection_sha256"],T//3)
        self.assertEqual(result["status"],"DERIVED_OPENUSD_IMAGE_ONLY")
        self.assertEqual(result["custody_mode"],"windows_job_object")
        self.assertTrue(result["worker_process_tree_custody_verified"])
        self.assertFalse(result["cinema_master_published"])
        with Image.open(result["derived_image_path"]) as image:
            self.assertEqual(image.size,(640,360))
        self.assertEqual(self.index.read_revision(self.pid,"RasterTake",1)[
            "document_sha256"],self.take_sha)
        self.assertEqual(len(self.approvals),1)
        with self.assertRaises(PermissionError):
            self.host().render_once(
                self.pid,"OriginalSceneDeriveOne",2,
                self.review["selection_sha256"],T//3)


T=7056000000


if __name__=="__main__":
    unittest.main()
