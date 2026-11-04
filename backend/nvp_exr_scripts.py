"""NVP B9 vetted Blender OpenEXR emit and independent pixel-readback scripts.

These Python sources are constant first-party strings pinned by SHA-256 when
staged. No user/model generated source is imported or evaluated.
"""
from __future__ import annotations

EXR_RENDER_SCRIPT = r'''# NVP B9 trusted scene-linear OpenEXR output from an indexed frozen DTP.
import bpy
import json
from pathlib import Path
import sys

args=sys.argv[sys.argv.index("--")+1:]
opts=dict(zip(args[::2],args[1::2]))
assert set(opts)=={"--plan"}
file=Path(opts["--plan"]).resolve()
plan=json.loads(file.read_text("utf8"))
assert plan["format"]=="nvp.exr.render_chunk.v1"
assert plan["engine"]=="BLENDER_WORKBENCH"
assert plan["color_depth"]==32 and plan["color_mode"]=="RGBA"
assert plan["view_transform"]=="Raw" and plan["exr_codec"]=="ZIP"
assert 1<=len(plan["frames"])<=8
scene=bpy.context.scene
assert scene.get("nvp_take_sha")==plan["sequence_sha256"]
assert scene.get("nvp_take_dependencies")==plan["dependency_sha256"]
assert scene.render.fps==plan["fps"] and scene.frame_end==plan["total_frames"]
width,height=plan["resolution"]
assert 64<=width<=3840 and 64<=height<=2160
assert width%2==0 and height%2==0
scene.render.engine="BLENDER_WORKBENCH"
scene.render.resolution_x=width
scene.render.resolution_y=height
scene.render.resolution_percentage=100
scene.render.image_settings.file_format="OPEN_EXR"
scene.render.image_settings.color_mode="RGBA"
scene.render.image_settings.color_depth="32"
scene.render.image_settings.exr_codec="ZIP"
scene.view_settings.view_transform="Raw"
# Raw is a scene-linear, display-untransformed write path. Avoid a
# display look (the available looks depend on the current OCIO config).
scene.view_settings.exposure=0
scene.view_settings.gamma=1
scene.render.film_transparent=False
markers={m.name:m for m in scene.timeline_markers}
for shot in plan["shots"]:
    marker=markers.get("CUT_"+shot["id"])
    assert marker is not None and marker.frame==shot["start_frame"]
    assert marker.camera is not None
for row in plan["frames"]:
    number=row["frame"]
    assert type(number) is int and 1<=number<=plan["total_frames"]
    filename=row["file"]
    assert filename==("frame_%06d.exr"%number)
    target=file.parent/filename
    assert not target.exists()
    available=[s for s in plan["shots"] if s["start_frame"]<=number]
    assert available
    selected=available[-1]
    marker=markers["CUT_"+selected["id"]]
    scene.camera=marker.camera
    scene.frame_set(number)
    scene.render.filepath=str(target)
    bpy.ops.render.render(write_still=True)
    assert target.is_file() and target.stat().st_size>128
''' 

EXR_AUDIT_SCRIPT = r'''# NVP B9 independent 32-bit floating pixel readback in second Blender worker.
import bpy
import hashlib
import json
import math
from pathlib import Path
import sys

args=sys.argv[sys.argv.index("--")+1:]
opts=dict(zip(args[::2],args[1::2]))
assert set(opts)=={"--plan","--audit"}
plan_file=Path(opts["--plan"]).resolve()
plan=json.loads(plan_file.read_text("utf8"))
assert plan["format"]=="nvp.exr.render_chunk.v1"
assert plan["color_depth"]==32 and plan["view_transform"]=="Raw"
width,height=plan["resolution"]
checks=[]
frames=[]
def check(name,ok,evidence):
    checks.append({"check":name,"passed":bool(ok),"evidence":evidence})
for row in plan["frames"]:
    path=plan_file.parent/row["file"]
    assert path.is_file() and not path.is_symlink()
    im=bpy.data.images.load(str(path),check_existing=False)
    try:
        actual=list(im.size)
        floats=bool(im.is_float)
        count=len(im.pixels)
        check("float32:"+str(row["frame"]),floats,{"is_float":floats})
        check("size:"+str(row["frame"]),actual==[width,height],actual)
        check("rgba:"+str(row["frame"]),count==width*height*4,count)
        samples=[]
        if count>=4:
            pixels=width*height
            for idx in sorted({0,pixels//5,pixels//2,4*pixels//5,pixels-1}):
                sample=[float(im.pixels[4*idx+c]) for c in range(4)]
                samples.append(sample)
        good=bool(samples) and all(math.isfinite(ch) for rgba in samples for ch in rgba)
        check("finite:"+str(row["frame"]),good,samples)
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        frames.append({"frame":row["frame"],"file":row["file"],
                       "sha256":digest,"sample_rgba":samples,
                       "reader_colorspace":im.colorspace_settings.name,
                       "decoded_float_buffer":floats})
    finally:
        bpy.data.images.remove(im)
report={"format":"nvp.exr.native_float_readback.v1",
        "blender":bpy.app.version_string,
        "render_engine":plan["engine"],
        "linear_write_transform":plan["view_transform"],
        "required_channel_depth":plan["color_depth"],
        "resolution":plan["resolution"],
        "fps":plan["fps"],
        "take_sequence_sha256":plan["sequence_sha256"],
        "frames":frames,"checks":checks,
        "passed":bool(checks) and all(c["passed"] for c in checks)}
Path(opts["--audit"]).write_text(json.dumps(report,sort_keys=True,indent=2),"utf8")
if not report["passed"]:
    raise RuntimeError("Independent native EXR float image readback failed")
'''
