"""P1-F: fail-closed original-camera, genuine actor-mesh/face-rig admission.

This is a source-integrity preflight, not a Blender/Cycles render worker.
No procedural actor stand-ins, camera substitutions, fake facial movement,
generated pixels, or render-success receipts are emitted.

The NVP DATA-AV source layer currently supports only primitive asset
bindings; production characters MUST be imported and verified separately.
"""
from __future__ import annotations

import hashlib
import json

from backend.nvp_film_index import FilmIndex, _require_pid, _id, _sha
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_p1f_p2_reel_plan import P1FReelPlan
from backend.nvp_temporal_ledger import _int

CONTRACT = "nvp.p1f.original_cycles_frame_admission.v1"
MAX_ACTORS = 32
MAX_MESHES_PER_ACTOR = 128
MAX_ACTOR_POINTS = 2_000_000
# A face-rig capability is more than a jaw energy envelope.
REQUIRED_FACE_DOMAINS = frozenset(("jaw", "lips", "eyes", "expression"))


class RenderSourceNotReady(RuntimeError):
    """The authentic 3D source cannot yet be faithfully rendered."""


def _source_sha(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False
    ).encode("ascii")).hexdigest()


def _actor_geometry(stage, actor_path):
    from pxr import Usd, UsdGeom, UsdSkel
    actor = stage.GetPrimAtPath(actor_path)
    if not actor or not actor.IsDefined():
        raise RenderSourceNotReady("Original ActorID source prim is missing")
    mesh_count = 0
    points = 0
    blendshapes = set()
    skel_count = 0
    for prim in Usd.PrimRange(actor):
        if prim.IsA(UsdGeom.Mesh):
            mesh_count += 1
            if mesh_count > MAX_MESHES_PER_ACTOR:
                raise RenderSourceNotReady("Actor source mesh exceeds native scene limits")
            mesh = UsdGeom.Mesh(prim)
            val = mesh.GetPointsAttr().Get()
            if val is None or not val:
                raise RenderSourceNotReady("Actor source mesh has no authentic vertices")
            points += len(val)
            if points > MAX_ACTOR_POINTS:
                raise RenderSourceNotReady("Actor source geometry exceeds native mesh budget")
            if len(mesh.GetFaceVertexCountsAttr().Get() or []) < 1:
                raise RenderSourceNotReady("Actor mesh has no authored faces")
            api = UsdSkel.BindingAPI(prim)
            # Name-authored blendshape targets are a prerequisite, not
            # a claim of calibrated expression transfer.
            tokens = api.GetBlendShapesAttr().Get()
            if tokens:
                blendshapes.update(str(t).lower() for t in tokens)
        elif prim.IsA(UsdSkel.Skeleton):
            skel_count += 1
    if mesh_count == 0 or skel_count == 0:
        raise RenderSourceNotReady(
            "P1-F requires an imported actor mesh with original source skeleton; "
            "NVP procedural cubes/spheres are not a character render")
    if not blendshapes:
        raise RenderSourceNotReady(
            "P1-F requires an authored facial blendshape/viseme rig; "
            "a simple jaw-volume animation is insufficient")
    aliases = {
        "jaw": ("jaw", "mouthopen"),
        "lips": ("lip", "mouth", "viseme"),
        "eyes": ("eye", "blink", "lid"),
        "expression": ("cheek", "brow", "smile", "frown", "expression"),
    }
    covered = {domain for domain, names in aliases.items()
               if any(any(n in shape for n in names) for shape in blendshapes)}
    if covered != REQUIRED_FACE_DOMAINS:
        raise RenderSourceNotReady(
            "Original actor facial rig is missing explicit jaw/lips/eyes/expression controls")
    return {"mesh_count": mesh_count, "vertex_count": points,
            "skeleton_count": skel_count,
            "face_domains": sorted(covered)}


def admit_original_frame(index: FilmIndex, project_id, plan_id,
                         reel_index, frame_offset):
    """Verify exact original Take and genuine actor/camera at output frame.

    Returns only SOURCE_ADMITTED evidence. Worker authorization, kernel custody,
    actual Cycles rendering and independent image/audio verification MUST
    remain separate. Missing imported assets always refuse the render.
    """
    if not isinstance(index, FilmIndex):
        raise TypeError("Native NVP FilmIndex required")
    _require_pid(project_id)
    _id(plan_id, "existing source reel plan")
    _int(reel_index, "reel index")
    _int(frame_offset, "frame offset")
    plan = P1FReelPlan(index)
    original = plan.picture_instant(
        project_id, plan_id, reel_index, frame_offset)
    source_id = original["source_take_id"]
    source_sha = _sha(original["source_take_sha256"])
    frozen = index.read_revision(project_id, source_id, 1)
    if frozen["document_sha256"] != source_sha:
        raise RenderSourceNotReady("Original source Take revision SHA changed")
    proof = OpenUSDTakeCapture(
        index, verify_creator_action=lambda *_: False
    ).verify_take(project_id, source_id)
    if proof["take_document_sha256"] != source_sha:
        raise RenderSourceNotReady("Original Take is not independently verified")
    src = frozen["data"]
    scene, stage = OpenUSDSceneBridge(index).open(
        project_id, src["scene_id"], src["scene_revision"])
    if scene["document_sha256"] != src["scene_document_sha256"]:
        raise RenderSourceNotReady("Original composed OpenUSD scene SHA changed")
    camera = original["source_camera"]
    roles = scene["data"]["prim_roles"]
    if roles.get(camera) != "camera":
        raise RenderSourceNotReady("Shot requires original USD camera, not an anchor")
    from pxr import UsdGeom
    cam_prim = stage.GetPrimAtPath(camera)
    if not cam_prim or not cam_prim.IsA(UsdGeom.Camera):
        raise RenderSourceNotReady("Shot lacks genuine authored USD camera optics")
    actors = [path for path, role in roles.items() if role == "actor"]
    if not actors or len(actors) > MAX_ACTORS:
        raise RenderSourceNotReady("P1-F needs bounded, real 3D cast")
    geometry = {}
    for path in sorted(actors):
        geometry[path] = _actor_geometry(stage, path)
    receipt = {
        "format": CONTRACT, "status": "SOURCE_ADMITTED_NOT_RENDERED",
        "project_id": project_id, "plan_id": plan_id,
        "plan_document_sha256": plan.read(
            project_id, plan_id)["document_sha256"],
        "take_id": source_id, "take_document_sha256": source_sha,
        "scene_document_sha256": scene["document_sha256"],
        "source_tick": original["source_tick"],
        "output_tick": original["output_tick"],
        "camera_path": camera,
        "actor_geometry": geometry,
        "genuine_cycles_output": False,
        "original_pcm_replaced": False,
        "filmmaker_approval_granted": False,
    }
    return {**receipt, "receipt_sha256": _source_sha(receipt)}
