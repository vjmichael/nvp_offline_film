"""INT-02C supervised Blender Cycles picture renderer for source-only OpenUSD.

Each approved sample is flattened at exact original Film Time into an
ephemeral *static* composed USD layer, then rendered by NVP's existing
SHA-pinned, OS-contained BlenderWorkerSupervisor. No CPU proxy fallback.
The renderer is an integration candidate: Cycles/UsdSkel/MaterialX quality,
color/lighting fidelity, kernel custody and feature scale need native proof.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
import os
from pathlib import Path
import shutil
import sys
import threading

from backend.nvp_blender_worker import BlenderOperation, BlenderWorkerSupervisor, sha_file
from backend.nvp_film_index import FilmIndex
from backend.nvp_final_2d_native import _png_header
from backend.nvp_openusd_scene import OpenUSDSceneBridge, _usd
from backend.nvp_openusd_shot_overrides import OpenUSDShotOverrides
from backend.nvp_temporal_ledger import _int
from backend.nvp_w1g_encrypted_source import require_efs_stage, verify_efs_inputs

FORMAT="nvp.int02.cycles.frame_plan.v1"
WIDTH=1920
HEIGHT=1080
SAMPLES=96


def static_composed_usd(index: FilmIndex, project_id, take_id, take_sha,
                        tick, *, camera_path, shot_id=None, shot_revision=None,
                        shot_sha=None):
    """Read actual authored USD + approved stronger shot, freeze sampled attrs."""
    if not isinstance(index, FilmIndex):
        raise TypeError("Native FilmIndex is required")
    _int(tick, "original Cycles sample time")
    take=index.read_revision(project_id,take_id,1)
    data=take["data"]
    if (take["kind"]!="take" or take["document_sha256"]!=take_sha or
        data.get("frozen") is not True or
        data.get("format")!="nvp.digital_take.openusd_temporal.v1" or
        tick>=data["duration_tick"]):
        raise RuntimeError("Cycles input is not an exact frozen original Take")
    if shot_id is None:
        if shot_revision is not None or shot_sha is not None:
            raise RuntimeError("Unbound director shot revision")
        scene,stage=OpenUSDSceneBridge(index).open(
            project_id,data["scene_id"],data["scene_revision"])
    else:
        if type(shot_revision) is not int or type(shot_sha) is not str:
            raise RuntimeError("Cycles shot must have an exact revision and SHA")
        record,scene,stage=OpenUSDShotOverrides(
            index,verify_director_action=lambda event,scope:False
        ).open_shot(project_id,shot_id,shot_revision,tick=tick)
        if (record["document_sha256"]!=shot_sha or
            record["data"]["take_id"]!=take_id or
            record["data"]["take_document_sha256"]!=take_sha):
            raise RuntimeError("Native shot composition no longer binds original performance")
    if scene["document_sha256"]!=data["scene_document_sha256"]:
        raise RuntimeError("Native production USD source changed after freezing")
    _,_,Usd,UsdGeom=_usd()
    prim=stage.GetPrimAtPath(camera_path)
    if not prim or not prim.IsA(UsdGeom.Camera):
        raise RuntimeError("Production Cycles requires a real UsdGeom.Camera schema")
    source_camera=UsdGeom.Camera(prim)
    sample_tick=Usd.TimeCode(float(tick))
    # USD camera focal and aperture attributes are authored in
    # one-tenth of a scene unit. Convert to real Blender millimeters
    # from the composed stage's original metersPerUnit metadata.
    mm_per_camera_unit=100.0*float(UsdGeom.GetStageMetersPerUnit(stage))
    params={}
    for key,attr in (
        ("camera_focal_length_mm",source_camera.GetFocalLengthAttr()),
        ("camera_sensor_width_mm",source_camera.GetHorizontalApertureAttr()),
        ("camera_sensor_height_mm",source_camera.GetVerticalApertureAttr()),
    ):
        raw=attr.Get(sample_tick)
        if raw is None:
            raise RuntimeError("Composed original USD camera lens/aperture is absent")
        value=float(raw)*mm_per_camera_unit
        if not math.isfinite(value) or not 1.0<=value<=300.0:
            raise RuntimeError("Original USD camera lens/aperture outside finite Blender bounds")
        params[key]=value
    from backend.nvp_int02_usd_materials import source_preview_materials
    material_bindings=source_preview_materials(stage,tick)
    # P1-B/C: render the REAL skinned character evaluated at authored Film
    # Time. The native Blender importer must never re-skin a source mesh
    # after it was baked for this one immutable picture sample.
    frozen_actor_skin=[]
    for original in scene["data"].get("imported_characters",[]):
        from backend.nvp_openusd_skinning import evaluate_skin
        actor=original["path"]
        mesh_path=actor+"/Rig/CharacterMesh"
        evaluated=evaluate_skin(
            stage,stage.GetPrimAtPath(mesh_path),actor,tick)
        if (evaluated["usd_skin_binding_verified"] is not True or
            evaluated["skinning_evaluated"] is not True):
            raise RuntimeError("Original imported character is not genuinely skin-deformed")
        frozen_actor_skin.append({
            "actor_id":original["actor_id"],
            "mesh_path":mesh_path,
            "points":evaluated["deformed_points"],
        })
    flat=stage.Flatten()
    baked=Usd.Stage.Open(flat)
    if baked is None:
        raise RuntimeError("USD composition could not flatten into a native worker source")
    sample=Usd.TimeCode(float(tick))
    # A static frame source contains the exact deformed world geometry,
    # no second animation layer or accidental Blender skin reapplication.
    if frozen_actor_skin:
        from pxr import Gf,UsdSkel,Vt
        for actor in frozen_actor_skin:
            source=baked.GetPrimAtPath(actor["mesh_path"])
            if not source or not source.IsA(UsdGeom.Mesh):
                raise RuntimeError("Frozen native actor source mesh is missing")
            mesh=UsdGeom.Mesh(source)
            if not mesh.GetPointsAttr().Set(Vt.Vec3fArray([
                Gf.Vec3f(*p) for p in actor["points"]])):
                raise RuntimeError("Evaluated imported actor skin could not bake to USD")
            for prop in ("skel:skeleton","skel:geomBindTransform",
                         "primvars:skel:jointIndices",
                         "primvars:skel:jointWeights"):
                if source.GetProperty(prop):
                    source.RemoveProperty(prop)
            if source.HasAPI(UsdSkel.BindingAPI):
                source.RemoveAPI(UsdSkel.BindingAPI)
            if source.GetProperty("skel:skeleton"):
                raise RuntimeError("Native frame retained an unwanted second skin binding")
    for prim in baked.Traverse():
        for attr in prim.GetAttributes():
            times=attr.GetTimeSamples()
            if times:
                value=attr.Get(sample)
                if value is None:
                    raise RuntimeError("Original USD timed attribute cannot be sampled")
                for t in times:
                    if not attr.ClearAtTime(Usd.TimeCode(float(t))):
                        raise RuntimeError("Could not clear original USD animation time sample")
                if attr.GetTimeSamples():
                    raise RuntimeError("Unbaked animation samples remain in native render source")
                if not attr.Set(value):
                    raise RuntimeError("Could not bake exact-time USD property")
    text=baked.GetRootLayer().ExportToString()
    if type(text) is not str or not 100<=len(text.encode("utf8"))<=24*1024*1024:
        raise RuntimeError("Composed native USD source exceeds worker bound")
    # No external textures/asset paths in this initial protected worker: a
    # flattened scene cannot cause Blender to load arbitrary drive files.
    if "@" in text:
        raise RuntimeError("Cycles stage contains unresolved external USD asset reference")
    return text.encode("utf8"), params, material_bindings


class NativeCyclesOriginalRenderer:
    def __init__(self,index:FilmIndex,project_id,supervisor:BlenderWorkerSupervisor,
                 *,trusted_script:Path,allow_plaintext_staging=False,
                 require_encrypted_scratch=True):
        if not isinstance(index,FilmIndex) or not isinstance(supervisor,BlenderWorkerSupervisor):
            raise TypeError("Trusted FilmIndex and bounded Blender worker required")
        if allow_plaintext_staging is not True:
            raise PermissionError("Explicit native consent for temporary plaintext USD staging required")
        self.index=index
        self.project_id=project_id
        self.supervisor=supervisor
        self.trusted_script=Path(trusted_script)
        if self.trusted_script.is_symlink() or not self.trusted_script.is_file():
            raise RuntimeError("Installed first-party Cycles worker script unavailable")
        self.script_sha=sha_file(self.trusted_script)
        if type(require_encrypted_scratch) is not bool:
            raise TypeError("Protected native Cycles scratch policy must be explicit")
        self.require_encrypted_scratch=require_encrypted_scratch
        self._lock=threading.RLock()
        self._active=None

    def cancel_active(self):
        with self._lock:
            job=self._active
        return self.supervisor.cancel(job) if job is not None else False

    def render_png(self, *, scope, tick, camera_path, source_snapshot):
        if (type(scope) is not dict or
            scope.get("project_id")!=self.project_id or
            scope.get("operation")!="nvp.int02.native_approved_edited_30s_derivative" or
            scope.get("no_ffmpeg") is not True or
            scope.get("original_sources_immutable") is not True or
            source_snapshot.get("time_tick")!=tick or
            source_snapshot.get("scene_document_sha256")!=scope.get("scene_document_sha256")):
            raise RuntimeError("Cycles source frame not bound to native editor authorization")
        if camera_path is None:
            # An authored camera gap legitimately has a black frame. No
            # invented camera or arbitrary background animation is added.
            from io import BytesIO
            from PIL import Image
            image=Image.new("RGB",(WIDTH,HEIGHT),(0,0,0))
            output=BytesIO()
            image.save(output,format="PNG")
            return output.getvalue()
        if type(camera_path) is not str or not camera_path.startswith("/World/"):
            raise RuntimeError("Only original authored USD cameras can be rendered")
        take_id=scope["source_take_id"]
        take_sha=scope["source_take_sha256"]
        shot_id=scope.get("source_shot_id")
        shot_rev=scope.get("source_shot_revision")
        shot_sha=scope.get("source_shot_sha256")
        usd,optics,material_bindings=static_composed_usd(
            self.index,self.project_id,take_id,take_sha,tick,
            camera_path=camera_path,
            shot_id=shot_id,shot_revision=shot_rev,shot_sha=shot_sha)
        for observed in source_snapshot.get("native_scene_schemas",[]):
            if (observed.get("prim_path")==camera_path and
                observed.get("schema")=="UsdGeom.Camera" and
                not math.isclose(float(observed["focal_length_mm"]),
                                 optics["camera_focal_length_mm"],
                                 rel_tol=2e-5,abs_tol=1e-4)):
                raise RuntimeError("Authoritative camera lens and scene snapshot conflict")
        dig=sha256(usd).hexdigest()
        spec=(self.project_id+"|"+scope["presentation_id"]+"|"+
              take_sha+"|"+str(tick)+"|"+str(shot_sha)).encode()
        job="int02_"+sha256(spec).hexdigest()[:40]
        jobdir=self.supervisor.root/job
        if jobdir.exists() or jobdir.is_symlink():
            raise RuntimeError("Previously submitted native Cycles sample cannot be replayed")
        jobdir.mkdir(mode=0o700)
        if self.require_encrypted_scratch:
            # Unlike a UI warning, this OS EFS preflight is enforced
            # BEFORE any original authored source reaches the disk.
            try:
                require_efs_stage(jobdir)
            except BaseException:
                # EFS refusal must not poison the deterministic job ID with
                # an empty directory. No source bytes have been written yet.
                if jobdir.is_dir() and not jobdir.is_symlink() and not any(jobdir.iterdir()):
                    jobdir.rmdir()
                raise
        plan={
            "format":FORMAT,"usd_file":"source.usda",
            "usd_sha256":dig,"camera_path":camera_path,
            "source_tick":tick,"width":WIDTH,"height":HEIGHT,
            "samples":SAMPLES,"renderer":"CYCLES",
            **optics,
            "material_bindings":material_bindings,
            "actor_paths":[o["path"] for o in source_snapshot.get("objects",[])
                           if o.get("semantic_role")=="actor"],
            "light_paths":[o["path"] for o in source_snapshot.get("objects",[])
                           if o.get("semantic_role")=="light"],
        }
        planbytes=json.dumps(plan,sort_keys=True,separators=(",",":")).encode("ascii")
        for name,contents in (
            ("source.usda",usd),("plan.json",planbytes),
            ("render.py",self.trusted_script.read_bytes())):
            with (jobdir/name).open("xb") as fd:
                fd.write(contents)
                fd.flush();os.fsync(fd.fileno())
        if self.require_encrypted_scratch:
            verify_efs_inputs(jobdir)
        op=BlenderOperation(
            job_id=job,script="render.py",script_sha256=self.script_sha,
            inputs={"source.usda":dig,"plan.json":sha256(planbytes).hexdigest()},
            outputs={"frame.png":"png","audit.json":"json_audit"},
            arguments={"--plan":"plan.json","--output":"frame.png","--audit":"audit.json"},
            timeout_seconds=600,memory_limit_mb=8192,
            require_linux_cgroup_v2=True)
        with self._lock:
            self._active=job
        try:
            result=self.supervisor.run(op)
            if self.require_encrypted_scratch:
                verify_efs_inputs(jobdir)
            if result.get("state")!="SUCCEEDED":
                raise RuntimeError("Protected native Cycles render has no verified success")
            self.supervisor.verify_completed(job)
            audit=json.loads((jobdir/"audit.json").read_text("utf8"))
            encoded=(jobdir/"frame.png").read_bytes()
            if (audit.get("passed") is not True or
                audit.get("format")!="nvp.int02.cycles.native_frame.v1" or
                audit.get("source_usd_sha256")!=dig or
                audit.get("source_tick")!=tick or
                audit.get("camera_path")!=camera_path or
                audit.get("render_engine")!="CYCLES" or
                audit.get("cycles_samples")!=SAMPLES or
                audit.get("resolution")!=[WIDTH,HEIGHT] or
                audit.get("native_frame_sha256")!=sha256(encoded).hexdigest() or
                audit.get("source_camera_unit_conversion_verified") is not True or
                audit.get("source_material_bindings_verified") is not True or
                audit.get("source_material_bindings_sha256")!=sha256(
                    json.dumps(material_bindings,sort_keys=True,
                               separators=(",",":")).encode("ascii")).hexdigest() or
                any(not math.isclose(float(audit.get(k,0.0)),float(v),
                                     rel_tol=1e-5,abs_tol=1e-4)
                    for k,v in optics.items()) or
                audit.get("original_actor_geometry_verified") is not True or
                audit.get("authored_lights_verified") is not True or
                _png_header(encoded)!=(WIDTH,HEIGHT)):
                raise RuntimeError("Independent Cycles source/output contract failed")
            return encoded
        finally:
            with self._lock:
                self._active=None


def build_native_cycles_renderer(index:FilmIndex,project_id,*,
                                 plaintext_consent=False,
                                 require_encrypted_scratch=True):
    """Native installed host only; no legacy still/proxy worker is re-enabled."""
    from backend.nvp_slate08b_native_camera_ipc import discover_blender
    from backend.nvp_resource_ledger import TaskLedger
    blender=discover_blender()
    if blender is None:
        raise RuntimeError("Trusted local Blender Cycles executable unavailable")
    root=Path(os.environ["NVP_HOME"]).resolve().parent/"Runtime"/"int02-cycles"
    if root.is_symlink():
        raise RuntimeError("Native Cycles runtime cannot follow a symlink")
    root.mkdir(parents=True,mode=0o700,exist_ok=True)
    ledger=TaskLedger(root/"tasks")
    supervisor=BlenderWorkerSupervisor(
        root/"workers",blender_executable=blender,
        blender_sha256=sha_file(blender),
        blender_version=_blender_version(blender),
        activity_ledger=ledger)
    unresolved=supervisor.recover_interrupted()
    if unresolved:
        raise RuntimeError(
            "Previous Cycles workers have unverified OS custody after restart; "+
            "do not admit new native frames until original kernel reconciliation")
    scriptroot=Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parents[1]))
    script=scriptroot/"tools"/"nvp_int02_cycles_frame_worker.py"
    return NativeCyclesOriginalRenderer(
        index,project_id,supervisor,trusted_script=script,
        allow_plaintext_staging=plaintext_consent,
        require_encrypted_scratch=require_encrypted_scratch)


def _blender_version(binary):
    import subprocess
    from backend.nvp_w1g_owned_subprocess import run_owned_subprocess
    result=run_owned_subprocess([str(binary),"-b","--version"],
                          capture_output=True,text=True,timeout=15,check=True)
    first=result.stdout.splitlines()[0].strip()
    if not first.startswith("Blender "):
        raise RuntimeError("Installed Cycles worker did not report real Blender version")
    return first
