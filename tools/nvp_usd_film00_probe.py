"""USD-FILM-00: execute REAL OpenUSD author/reopen capability probes.

This is a bounded native interoperability INVENTORY, not an alternative USD
renderer, arbitrary asset importer, physics engine, or film quality test.
Every feature has independent evidence and a capability LEVEL. An importable
schema is NEVER reported as a working simulation/rendered feature.

Run with pinned usd-core on Windows/Linux; optional modules are recorded
without fabricating support. An extra Blender process independently checks
selected real import/export features via its own Python interpreter.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import time

FORMAT = "nvp.usd_film00.native_capabilities.v1"
CORE = frozenset({
    "geometry_camera_light",
    "composition_layers",
    "references_and_payloads",
    "variants",
    "point_instancer",
    "skeletal_blendshapes",
    "usdpreview_material",
})
SCHEMAS = (
    ("physics_rigid_body", "pxr.UsdPhysics", "RigidBodyAPI"),
    ("volume_schema", "pxr.UsdVol", "Volume"),
    ("spatial_audio_schema", "pxr.UsdMedia", "SpatialAudio"),
    ("render_settings_schema", "pxr.UsdRender", "Settings"),
)
OPTIONAL_MODULES = (
    "pxr.UsdImagingGL",
    "pxr.Hd",
    "pxr.HdSt",
    "pxr.UsdRi",
    "MaterialX",
)


def sha(path):
    h = sha256()
    with Path(path).open("rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def _require(test, detail):
    if not test:
        raise RuntimeError(detail)


def geometry_camera_light(root):
    from pxr import Gf, Usd, UsdGeom, UsdLux, Vt
    target = root / "geometry_camera_light.usda"
    stage = Usd.Stage.CreateNew(str(target))
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    mesh = UsdGeom.Mesh.Define(stage, "/World/Mesh")
    mesh.GetPointsAttr().Set(Vt.Vec3fArray([
        Gf.Vec3f(-1, 0, 0), Gf.Vec3f(1, 0, 0),
        Gf.Vec3f(1, 0, 2), Gf.Vec3f(-1, 0, 2),
    ]))
    mesh.GetFaceVertexCountsAttr().Set(Vt.IntArray([3, 3]))
    mesh.GetFaceVertexIndicesAttr().Set(Vt.IntArray([0, 1, 2, 0, 2, 3]))
    camera = UsdGeom.Camera.Define(stage, "/World/Camera")
    camera.GetFocalLengthAttr().Set(0.5)
    light = UsdLux.SphereLight.Define(stage, "/World/Light")
    UsdLux.LightAPI(light.GetPrim()).GetIntensityAttr().Set(150.0)
    stage.GetRootLayer().Save()
    reopened = Usd.Stage.Open(str(target))
    m = UsdGeom.Mesh(reopened.GetPrimAtPath("/World/Mesh"))
    c = UsdGeom.Camera(reopened.GetPrimAtPath("/World/Camera"))
    l = UsdLux.SphereLight(reopened.GetPrimAtPath("/World/Light"))
    _require(bool(m) and len(m.GetPointsAttr().Get()) == 4, "Real USD mesh lost points")
    _require(bool(c) and abs(c.GetFocalLengthAttr().Get() - 0.5) < 0.0001,
             "Native camera optics lost")
    _require(bool(l) and abs(UsdLux.LightAPI(l.GetPrim()).GetIntensityAttr().Get() - 150) < .01,
             "Native light intensity lost")
    _require(abs(UsdGeom.GetStageMetersPerUnit(reopened) - 1) < 1e-9,
             "Native stage meter units lost")
    return {"level": "AUTHOR_SAVE_REOPEN", "mesh_points": 4,
            "camera_focal_native": 0.5, "light_intensity": 150,
            "stage_up_axis": str(UsdGeom.GetStageUpAxis(reopened)),
            "usd_sha256": sha(target),
            "limits": "No PBR pixel rendering, skinning or calibrated camera/light parity measured"}


def composition_layers(root):
    from pxr import Sdf, Usd, UsdGeom
    strong = Sdf.Layer.CreateAnonymous("nvp_test_strong.usda")
    weak = Sdf.Layer.CreateAnonymous("nvp_test_weak.usda")
    ws = Usd.Stage.Open(weak)
    cube = UsdGeom.Cube.Define(ws, "/World/Prop")
    cube.GetSizeAttr().Set(1.5)
    ss = Usd.Stage.Open(strong)
    UsdGeom.Cube.Define(ss, "/World/Prop").GetSizeAttr().Set(2.5)
    composed = Sdf.Layer.CreateAnonymous("nvp_test_composed.usda")
    composed.subLayerPaths = [strong.identifier, weak.identifier]
    stage = Usd.Stage.Open(composed)
    original = UsdGeom.Cube(stage.GetPrimAtPath("/World/Prop"))
    _require(original and abs(original.GetSizeAttr().Get() - 2.5) < 1e-5,
             "Native stronger USD layer did not win")
    # Original weaker layer remains separately readable.
    _require(abs(UsdGeom.Cube(ws.GetPrimAtPath("/World/Prop")).GetSizeAttr().Get()
                 - 1.5) < 1e-5, "Native source was destructively overwritten")
    return {"level": "AUTHOR_COMPOSE_EVALUATE", "source_size": 1.5,
            "composed_size": 2.5, "original_source_unchanged": True,
            "limits": "Anonymous sample only, not a project-local authorized resolver"}


def references_and_payloads(root):
    from pxr import Usd, UsdGeom
    asset = root / "shared_asset.usda"
    master = root / "scene_refs_payloads.usda"
    source = Usd.Stage.CreateNew(str(asset))
    geom = UsdGeom.Sphere.Define(source, "/Reusable")
    geom.GetRadiusAttr().Set(1.25)
    source.SetDefaultPrim(geom.GetPrim())
    source.GetRootLayer().Save()
    scene = Usd.Stage.CreateNew(str(master))
    scene.DefinePrim("/World", "Xform")
    r = scene.DefinePrim("/World/Reference")
    p = scene.DefinePrim("/World/Payload")
    _require(r.GetReferences().AddReference(str(asset), "/Reusable"),
             "Could not author a native USD reference")
    _require(p.GetPayloads().AddPayload(str(asset), "/Reusable"),
             "Could not author a native USD payload")
    scene.GetRootLayer().Save()
    reopened = Usd.Stage.Open(str(master), load=Usd.Stage.LoadNone)
    ref = reopened.GetPrimAtPath("/World/Reference")
    payload = reopened.GetPrimAtPath("/World/Payload")
    _require(ref and ref.IsA(UsdGeom.Sphere), "Actual referenced asset did not resolve")
    _require(payload and not payload.IsLoaded(), "Payload was not actually unloaded")
    reopened.Load("/World/Payload")
    loaded = reopened.GetPrimAtPath("/World/Payload")
    _require(loaded and loaded.IsA(UsdGeom.Sphere) and loaded.IsLoaded(),
             "Payload could not be loaded natively on demand")
    _require(abs(UsdGeom.Sphere(loaded).GetRadiusAttr().Get() - 1.25) < 1e-5,
             "Loaded payload differs from authored source")
    return {"level": "SAVE_REOPEN_LOAD_UNLOAD", "original_asset_sha256": sha(asset),
            "source_reused": True, "load_none_then_load_proven": True,
            "limits": "Temporary local asset paths: NOT NVP's source-authorized offline resolver"}


def variants(root):
    from pxr import Usd, UsdGeom
    target = root / "variants.usda"
    stage = Usd.Stage.CreateNew(str(target))
    cube = UsdGeom.Cube.Define(stage, "/World/Variant")
    v = cube.GetPrim().GetVariantSets().AddVariantSet("look")
    for name, size in (("wide", 2.0), ("narrow", 0.5)):
        v.AddVariant(name)
        _require(v.SetVariantSelection(name), "Could not select USD variant")
        with v.GetVariantEditContext():
            cube.GetSizeAttr().Set(size)
    stage.GetRootLayer().Save()
    reopened = Usd.Stage.Open(str(target))
    rv = reopened.GetPrimAtPath("/World/Variant").GetVariantSets().GetVariantSet("look")
    answers = {}
    for name in ("wide", "narrow"):
        _require(rv.SetVariantSelection(name), "Could not switch USD variant")
        answers[name] = UsdGeom.Cube(reopened.GetPrimAtPath("/World/Variant")).GetSizeAttr().Get()
    _require(abs(answers["wide"] - 2.0) < .001 and
             abs(answers["narrow"] - .5) < .001, "USD variants lost their unique data")
    return {"level": "AUTHOR_SAVE_REOPEN_SWITCH", "values": answers,
            "limits": "Asset/shot variant policy and controlled variant explosion not implemented"}


def point_instancer(root):
    from pxr import Gf, Usd, UsdGeom, Vt
    target = root / "instancing.usda"
    stage = Usd.Stage.CreateNew(str(target))
    proto = UsdGeom.Cube.Define(stage, "/World/PrototypeTree")
    proto.GetSizeAttr().Set(1)
    inst = UsdGeom.PointInstancer.Define(stage, "/World/Trees")
    _require(inst.GetPrototypesRel().SetTargets([proto.GetPath()]),
             "Could not set USD prototype")
    inst.GetProtoIndicesAttr().Set(Vt.IntArray([0, 0, 0]))
    inst.GetPositionsAttr().Set(Vt.Vec3fArray([
        Gf.Vec3f(0, 0, 0), Gf.Vec3f(10, 0, 0), Gf.Vec3f(20, 0, 0),
    ]))
    stage.GetRootLayer().Save()
    reopened = Usd.Stage.Open(str(target))
    reread = UsdGeom.PointInstancer(reopened.GetPrimAtPath("/World/Trees"))
    _require(reread and len(reread.GetProtoIndicesAttr().Get()) == 3 and
             len(reread.GetPrototypesRel().GetTargets()) == 1,
             "Native repeated point instances did not reopen")
    return {"level": "AUTHOR_SAVE_REOPEN", "instances": 3,
            "limits": "No viewport/crowd rendering, per-person unique animation or LOD measured"}


def skeletal_blendshapes(root):
    from pxr import Gf, Usd, UsdSkel, Vt
    target = root / "skeletal_shape.usda"
    stage = Usd.Stage.CreateNew(str(target))
    UsdSkel.Root.Define(stage, "/World/Actor/Rig")
    rig = UsdSkel.Skeleton.Define(stage, "/World/Actor/Rig/Skeleton")
    joints = Vt.TokenArray(["Root", "Root/Jaw"])
    rig.GetJointsAttr().Set(joints)
    poses = Vt.Matrix4dArray([Gf.Matrix4d(1.0), Gf.Matrix4d(1.0)])
    rig.GetBindTransformsAttr().Set(poses)
    rig.GetRestTransformsAttr().Set(poses)
    anim = UsdSkel.Animation.Define(stage, "/World/Actor/Rig/Animation")
    anim.GetJointsAttr().Set(joints)
    anim.GetBlendShapesAttr().Set(Vt.TokenArray(["MouthOpen"]))
    anim.GetBlendShapeWeightsAttr().Set(Vt.FloatArray([0.0]), Usd.TimeCode(0))
    anim.GetBlendShapeWeightsAttr().Set(Vt.FloatArray([1.0]), Usd.TimeCode(24))
    UsdSkel.BlendShape.Define(stage, "/World/Actor/Rig/MouthOpen")
    stage.GetRootLayer().Save()
    reopened = Usd.Stage.Open(str(target))
    native = UsdSkel.Animation(reopened.GetPrimAtPath("/World/Actor/Rig/Animation"))
    _require(native and abs(native.GetBlendShapeWeightsAttr().Get(
        Usd.TimeCode(24))[0] - 1) < 1e-5, "Timed USD BlendShape value failed")
    _require(len(UsdSkel.Skeleton(reopened.GetPrimAtPath(
        "/World/Actor/Rig/Skeleton")).GetJointsAttr().Get()) == 2,
        "Native skeleton joints missing")
    return {"level": "AUTHOR_SAVE_REOPEN", "joints": 2, "blendshape_count": 1,
            "limits": "Not bound to a real face mesh, not IK, eye solver, or believable speech; FILM03 verifies mesh separately"}


def usdpreview_material(root):
    from pxr import Gf, Sdf, Usd, UsdShade
    target = root / "materials.usda"
    stage = Usd.Stage.CreateNew(str(target))
    material = UsdShade.Material.Define(stage, "/Looks/A")
    shader = UsdShade.Shader.Define(stage, "/Looks/A/Preview")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(.8, .2, .1))
    _require(bool(material) and bool(shader), "Native material/schema missing")
    stage.GetRootLayer().Save()
    reopened = Usd.Stage.Open(str(target))
    s = UsdShade.Shader(reopened.GetPrimAtPath("/Looks/A/Preview"))
    value = s.GetInput("diffuseColor").Get()
    _require(str(s.GetIdAttr().Get()) == "UsdPreviewSurface" and
             abs(float(value[0]) - .8) < 1e-4,
             "USD Preview shader source did not survive reopen")
    return {"level": "AUTHOR_SAVE_REOPEN_UNBOUND_SHADER", "shader_id": "UsdPreviewSurface",
            "limits": "No MaterialX closure, material binding, texture response or renderer parity"}


def schema_only(root, feature, module_name, class_name):
    mod = importlib.import_module(module_name)
    cls = getattr(mod, class_name)
    from pxr import Usd, UsdGeom
    target = root / (feature + ".usda")
    stage = Usd.Stage.CreateNew(str(target))
    base = UsdGeom.Xform.Define(stage, "/World/Object")
    if feature == "physics_rigid_body":
        typed = cls.Apply(base.GetPrim())
        _require(bool(typed), "RigidBodyAPI cannot apply to native USD prim")
        typed.CreateRigidBodyEnabledAttr(True)
        expected = "UsdPhysics.RigidBodyAPI"
    else:
        typed = cls.Define(stage, "/World/Feature")
        _require(bool(typed), "Could not define the native USD schema")
        expected = module_name + "." + class_name
    stage.GetRootLayer().Save()
    stage2 = Usd.Stage.Open(str(target))
    if feature == "physics_rigid_body":
        check = cls(stage2.GetPrimAtPath("/World/Object"))
        _require(check and bool(check.GetRigidBodyEnabledAttr().Get()),
                 "RigidBody USD schema did not survive reopen")
    else:
        _require(stage2.GetPrimAtPath("/World/Feature").IsA(cls),
                 "Optional native USD schema lost during reopen")
    return {"level": "SCHEMA_AUTHOR_SAVE_REOPEN", "schema": expected,
            "limits": "Only representation verified; no physics, volume rendering, audio playback or render engine"}


def create_blender_fixture(path):
    """NVP-owned, source-generated Mesh+Camera+Light for actual Blender import."""
    from pxr import Gf, Usd, UsdGeom, UsdLux, Vt
    stage = Usd.Stage.CreateNew(str(path))
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    mesh = UsdGeom.Mesh.Define(stage, "/World/ProbeMesh")
    mesh.GetPointsAttr().Set(Vt.Vec3fArray([
        Gf.Vec3f(-1, -1, 0), Gf.Vec3f(1, -1, 0),
        Gf.Vec3f(1, 1, 0), Gf.Vec3f(-1, 1, 0),
    ]))
    mesh.GetFaceVertexCountsAttr().Set(Vt.IntArray([3, 3]))
    mesh.GetFaceVertexIndicesAttr().Set(Vt.IntArray([0, 1, 2, 0, 2, 3]))
    camera = UsdGeom.Camera.Define(stage, "/World/Camera")
    camera.GetFocalLengthAttr().Set(0.5)
    light = UsdLux.SphereLight.Define(stage, "/World/Light")
    UsdLux.LightAPI(light.GetPrim()).GetIntensityAttr().Set(100)
    stage.GetRootLayer().Save()
    return {"sha256": sha(path), "original_points": 4,
            "original_camera": True, "original_light": True}


def _try(name, work, func, *args):
    started = time.perf_counter()
    try:
        item = func(*args)
    except (ImportError, ModuleNotFoundError, AttributeError) as exc:
        result = {"status": "NOT_AVAILABLE", "level": "NONE",
                  "reason": type(exc).__name__ + ": " + str(exc)[:320]}
    except Exception as exc:
        result = {"status": "FAIL", "level": "NONE",
                  "reason": type(exc).__name__ + ": " + str(exc)[:320]}
    else:
        result = {"status": "PASS", **item}
    result["elapsed_seconds"] = round(time.perf_counter() - started, 4)
    work[name] = result


def run_audit(root, fixture=None):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError("Existing native audit working directory required")
    from pxr import Usd
    try:
        wheel = importlib.metadata.version("usd-core")
    except importlib.metadata.PackageNotFoundError:
        wheel = "UNSPECIFIED"
    out = {
        "format": FORMAT, "status": "NATIVE_PROBES_EXECUTED",
        "os": platform.platform(), "python": sys.version.split()[0],
        "usd_core_distribution": wheel,
        "usd_get_version": list(Usd.GetVersion()),
        "git_head_reported": os.environ.get("GITHUB_SHA", "NOT_IN_CI"),
        "probe_source_sha256": sha(__file__),
        "evidence_type": "real_usd_author_read_not_render",
        "features": {},
        "optional_module_imports": {},
        "renderer_verified": False,
        "blender_verified": False,
        "hydra_delegate_render_verified": False,
        "materialx_renderer_parity_verified": False,
        "photorealism_verified": False,
        "nvp_source_indexed_asset_resolver_verified": False,
    }
    for name, func in (
        ("geometry_camera_light", geometry_camera_light),
        ("composition_layers", composition_layers),
        ("references_and_payloads", references_and_payloads),
        ("variants", variants),
        ("point_instancer", point_instancer),
        ("skeletal_blendshapes", skeletal_blendshapes),
        ("usdpreview_material", usdpreview_material),
    ):
        _try(name, out["features"], func, root)
    for name, module, cls in SCHEMAS:
        _try(name, out["features"], schema_only, root, name, module, cls)
    for name in OPTIONAL_MODULES:
        try:
            mod = importlib.import_module(name)
            out["optional_module_imports"][name] = {
                "status": "IMPORTABLE_ONLY",
                "path": str(getattr(mod, "__file__", "BUILTIN")),
                "render_execution_verified": False,
            }
        except Exception as exc:
            out["optional_module_imports"][name] = {
                "status": "NOT_AVAILABLE",
                "reason": type(exc).__name__ + ": " + str(exc)[:180],
            }
    if fixture:
        _try("native_blender_fixture", out["features"],
             create_blender_fixture, Path(fixture).resolve())
    out["required_source_baseline_passed"] = all(
        out["features"][name]["status"] == "PASS" for name in CORE)
    return out


def verify_blender_roundtrip(report_path, export_path):
    """Independent process uses usd-core to check an actual Blender-exported USD."""
    from pxr import Usd, UsdGeom, UsdLux
    recorded = json.loads(Path(report_path).read_text("utf8"))
    if recorded.get("format") != "nvp.usd_film00.blender_interop.v1" or \
       recorded.get("import_export_returned_success") is not True:
        raise RuntimeError("No real Blender success receipt")
    file = Path(export_path)
    _require(file.is_file() and not file.is_symlink() and
             recorded.get("export_usd_sha256") == sha(file),
             "Blender output changed before independent native verification")
    stage = Usd.Stage.Open(str(file))
    _require(stage, "Native usd-core could not reopen actual Blender export")
    meshes = [p for p in stage.Traverse() if p.IsA(UsdGeom.Mesh)]
    cameras = [p for p in stage.Traverse() if p.IsA(UsdGeom.Camera)]
    lights = [p for p in stage.Traverse() if
              p.IsA(UsdLux.SphereLight) or p.IsA(UsdLux.DistantLight)]
    _require(meshes and max(len(UsdGeom.Mesh(p).GetPointsAttr().Get() or [])
                            for p in meshes) >= 4,
             "Blender mesh geometry was lost through real USD roundtrip")
    _require(cameras, "Blender did not re-export a native USD Camera")
    _require(lights, "Blender did not re-export a native USD Light")
    return {
        "format": "nvp.usd_film00.independent_blender_verify.v1",
        "status": "PASS_BLENDER_EXPORT_NATIVE_REOPEN",
        "independent_export_sha256": sha(file),
        "actual_exported_meshes": len(meshes),
        "actual_exported_cameras": len(cameras),
        "actual_exported_lights": len(lights),
        "renderer_pixels_verified": False,
        "skel_blendshape_roundtrip_verified": False,
        "materialx_color_parity_verified": False,
        "artist_photorealism_verified": False,
    }


def main():
    a = argparse.ArgumentParser(description="Native USD-FILM-00 source capability report")
    a.add_argument("--output", required=True)
    a.add_argument("--fixture")
    a.add_argument("--verify-blender")
    a.add_argument("--blender-export")
    args = a.parse_args()
    output = Path(args.output).resolve()
    if not output.parent.is_dir():
        raise ValueError("Audit output must have an existing parent")
    if args.verify_blender or args.blender_export:
        if not (args.verify_blender and args.blender_export):
            raise ValueError("Independent Blender verification needs both files")
        report = verify_blender_roundtrip(args.verify_blender, args.blender_export)
        failed = False
    else:
        with tempfile.TemporaryDirectory(prefix="nvp-usd-film00-") as tmp:
            report = run_audit(tmp, fixture=args.fixture)
        failed = not report["required_source_baseline_passed"]
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", "utf8")
    print(json.dumps({"format": report["format"], "summary": report.get("status"),
                      "required_baseline_ok": not failed, "report": str(output)},
                     sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
