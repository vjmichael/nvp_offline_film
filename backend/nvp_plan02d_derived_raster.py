"""PLAN-02-D4: independently reopened, SHA-bound native USD still derivative.

Produces a single real 640x360 source-selected OpenUSD primitive picture on
demand; optional previously human-approved camera rail is a *virtual view*
over unchanged ActorIDs, geometry, PCM and integer Film Time. No FFmpeg,
frame-authoritative editing, imported proxy, general Hydra/Cycles renderer,
or cinema export claim. Publication requires a distinct native OS dialog.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO

from PIL import Image

from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_native_cpu_raster import NativeSourceRaster
from backend.nvp_plan02d_source_selection import ExactSourceWindowSelector

FORMAT="nvp.plan02d.native_source_selected_png.v1"
MAX_PNG_BYTES=24*1024*1024


class SourceSelectedNativeRaster:
    def __init__(self,index:FilmIndex,*,ask_native):
        if not isinstance(index,FilmIndex) or not callable(ask_native):
            raise TypeError("FilmIndex and trusted OS approval callback required")
        self.index=index
        self.ask_native=ask_native
        self.selector=ExactSourceWindowSelector(index)

    @staticmethod
    def _reopen(png):
        if type(png) is not bytes or not 64<=len(png)<=MAX_PNG_BYTES:
            raise RuntimeError("Renderer output exceeds bounded PNG contract")
        with Image.open(BytesIO(png)) as image:
            image.verify()
        with Image.open(BytesIO(png)) as inspected:
            if inspected.format!="PNG" or inspected.mode!="RGB" or (
                    inspected.width,inspected.height)!=(640,360):
                raise RuntimeError("Independently reopened derived USD raster differs")
            inspected.load()
        return sha256(png).hexdigest()

    def preview(self,project_id,request,selection_sha256,tick):
        pid=_require_pid(project_id)
        sample=self.selector.sample_at(pid,request,selection_sha256,tick)
        scope=self.selector.preview(pid,request)
        if sample["selection_sha256"]!=scope["selection_sha256"]:
            raise RuntimeError("Rendered source changed after original selection")
        raster=NativeSourceRaster(self.index,pid)
        png=raster.render_png(
            scope={"scene_document_sha256":scope["original_scene_sha256"]},
            tick=tick,camera_path=scope["source_camera_path"],
            source_snapshot=sample["source_snapshot"],
            approved_camera_pose=sample["approved_director_camera_pose"])
        digest=self._reopen(png)
        # One more complete source/rail check after native image generation.
        after=self.selector.preview(pid,request)
        if after!=scope:
            raise RuntimeError("Source/rail changed while deriving picture")
        return {
            "format":FORMAT, "status":"DERIVED_MEMORY_PREVIEW_NOT_PUBLISHED",
            "source_selection_sha256":selection_sha256,
            "take_document_sha256":scope["take_document_sha256"],
            "camera_timeline_sha256":scope["camera_timeline_sha256"],
            "rail_document_sha256":(
                scope["approved_rail"]["rail_document_sha256"]
                if scope["approved_rail"] else None),
            "film_tick":tick,
            "png_sha256":digest,
            "png_bytes":png,
            "width":640,"height":360,
            "source_modified":False,"worker_authorized":False,
            "ffmpeg_used":False,
        }

    def publish(self,project_id,presentation_id,request,
                selection_sha256,tick,expected_png_sha256):
        """Only the trusted NVP native host can request derivative publication."""
        pid=_require_pid(project_id)
        _id(presentation_id,"new derivative picture identity")
        if type(expected_png_sha256) is not str or len(expected_png_sha256)!=64:
            raise ValueError("A pinned native PNG preview SHA is mandatory")
        first=self.preview(pid,request,selection_sha256,tick)
        if first["png_sha256"]!=expected_png_sha256:
            raise PermissionError("Stale native image or source-selection preview")
        scope={
            "operation":"nvp.plan02d.publish_verified_derivative_png.v1",
            "project_id":pid,
            "presentation_id":presentation_id,
            "source_selection_sha256":selection_sha256,
            "take_sha256":first["take_document_sha256"],
            "camera_timeline_sha256":first["camera_timeline_sha256"],
            "approved_rail_sha256":first["rail_document_sha256"],
            "film_tick":tick,
            "png_sha256":first["png_sha256"],
            "no_worker_master_or_original_mutation":True,
        }
        if self.ask_native(dict(scope)) is not True:
            raise PermissionError("Creator refused a distinct derivative picture publication")
        second=self.preview(pid,request,selection_sha256,tick)
        if second["png_sha256"]!=first["png_sha256"]:
            raise PermissionError("Image changed during native OS permission")
        png=second["png_bytes"]
        stored=self.index.put_blob(pid,png,media_type="image/png")
        if stored!=first["png_sha256"] or self.index.get_blob(pid,stored)!=png:
            raise RuntimeError("Independent persisted derived image SHA differs")
        deps=[
            {"object_id":request["take_id"],"revision":1,"role":"source_take"},
            {"object_id":request["camera_timeline_id"],
             "revision":request["camera_timeline_revision"],"role":"timeline"},
        ]
        if request["camera_mode"]=="approved_rail":
            deps.append({"object_id":request["rail_id"],
                         "revision":request["rail_revision"],"role":"presentation"})
        doc={
            "format":FORMAT,"source_selection_sha256":selection_sha256,
            "original_take_sha256":first["take_document_sha256"],
            "camera_timeline_sha256":first["camera_timeline_sha256"],
            "approved_rail_sha256":first["rail_document_sha256"],
            "source_film_tick":str(tick),
            "png_sha256":stored,
            "width":first["width"],"height":first["height"],
            "source_modified":False,"actual_native_geometry_raster":True,
            "conventional_movie_master":False,"ffmpeg_used":False,
        }
        result=self.index.register_revision(
            pid,presentation_id,"presentation",doc,
            expected_revision=0,dependencies=deps)
        reopened=self.index.read_revision(pid,presentation_id,1)
        if (reopened["data"]!=doc or
                self._reopen(self.index.get_blob(pid,stored))!=stored):
            raise RuntimeError("New derivative presentation could not independently reopen")
        return {
            "status":"VERIFIED_DERIVED_OPENUSD_PNG",
            "presentation_id":presentation_id,
            "revision":1,
            "presentation_document_sha256":result["document_sha256"],
            "source_take_sha256":first["take_document_sha256"],
            "png_sha256":stored,
            "film_tick":tick,
            "source_modified":False,"ffmpeg_used":False,
            "cinema_master_accepted":False,
        }
