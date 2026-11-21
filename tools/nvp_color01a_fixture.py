"""COLOR-01A actual Blender/Cycles half-float EXR + FilmIndex restart acceptance.

A frozen Digital Take feeds approved camera frames to Cycles. FFmpeg
independently decodes those frames. A separate controlled emissive reference
demonstrates values >1 and non-8-bit precision. This is NOT calibrated ACES.
"""
from __future__ import annotations
from array import array
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from backend.nvp_presentation_pipeline import PresentationPipeline, PBR_ENGINE
from backend.nvp_color_exr import exr_info, PIXEL_EXR
from tools.nvp_capture01_fixture import fixture as capture_fixture

PROBE_SCRIPT = r'''import bpy,sys
from pathlib import Path
argv=sys.argv[sys.argv.index("--")+1:]
out=Path(argv[0]).resolve()
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
scene=bpy.context.scene
scene.render.engine="CYCLES"
scene.cycles.device="CPU"
scene.cycles.samples=2
scene.cycles.use_denoising=False
scene.render.resolution_x=64
scene.render.resolution_y=64
scene.render.resolution_percentage=100
scene.render.image_settings.file_format="OPEN_EXR"
scene.render.image_settings.color_mode="RGBA"
scene.render.image_settings.color_depth="16"
scene.render.image_settings.exr_codec="ZIP"
scene.view_settings.view_transform="Raw"
bpy.ops.mesh.primitive_plane_add(size=5.0)
plane=bpy.context.object
m=bpy.data.materials.new("LINEAR_REFERENCE")
m.use_nodes=True
n=m.node_tree.nodes
n.clear()
emission=n.new("ShaderNodeEmission")
# Blender color sockets clamp RGBA values to [0,1]; create HDR by
# increasing physical emission strength rather than supplying illegal colors.
emission.inputs["Color"].default_value=(0.75,0.123456,0.01953125,1)
emission.inputs["Strength"].default_value=3.0
surface=n.new("ShaderNodeOutputMaterial")
m.node_tree.links.new(emission.outputs[0],surface.inputs["Surface"])
plane.data.materials.append(m)
bpy.ops.object.camera_add(location=(0,0,3))
scene.camera=bpy.context.object
scene.camera.data.type="ORTHO"
scene.camera.data.ortho_scale=2
scene.render.filepath=str(out)
bpy.ops.render.render(write_still=True)
if not out.is_file(): raise RuntimeError("Missing real EXR diagnostic")
'''


def run(args, label, *, timeout=240, binary=False):
    try:
        p=subprocess.run(args,capture_output=True,text=not binary,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise RuntimeError(label+" could not execute") from exc
    if p.returncode:
        err=p.stderr if isinstance(p.stderr,str) else p.stderr.decode("utf-8","replace")
        raise RuntimeError(label+" failed: "+err[-700:])
    return p


def fixture(out, *, blender="blender", ffmpeg="ffmpeg"):
    root=Path(out).resolve()
    root.mkdir(parents=True,exist_ok=True)
    source=capture_fixture(root/"frozen",render_preview=False)
    if source["status"]!="passed_frozen_native_blender" or not source["live_scene_was_invalidated"]:
        raise RuntimeError("Real frozen and independently reopened Digital Take required")
    db=root/"frozen"/"film.sqlite3"
    studio=Studio(db)
    pid=studio.list_projects()[0]["id"]
    pipe=PresentationPipeline(studio)
    take=pipe.capture.reopen(pid,"take_real_captured")
    take_sha=take["record"]["document_sha256"]
    generated=pipe.render(pid,"take_real_captured","color01a_scene_linear_exr",
        root/"renders",engine=PBR_ENGINE,style="pbr_studio",
        pixel_contract=PIXEL_EXR,frame_mode="keyframes",
        width=128,height=72,samples=2,timeout=1500,executable=blender)
    # New Studio: original take, approved camera cuts and each frame SHA
    # must survive database/cache reinitialization.
    fresh=PresentationPipeline(Studio(db))
    verified=fresh.reopen(pid,"color01a_scene_linear_exr")
    if (verified["audit"]["pixel_contract"]!=PIXEL_EXR or
        verified["audit"]["frame_count"]!=4 or
        verified["audit"]["source_take_sha256"]!=take_sha):
        raise RuntimeError("Scene-linear EXR FilmIndex proof disagrees")
    if verified["record"]["dependencies"]!=[
        {"object_id":"take_real_captured","revision":1,"role":"source_take"}]:
        raise RuntimeError("EXR does not reference frozen take revision")
    idx=FilmIndex(Studio(db))
    frames=verified["record"]["data"]["rendered_frames"]
    frameproof=[]
    for frame in frames:
        raw=idx.get_blob(pid,frame["image_sha256"])
        info=exr_info(raw)
        if (info["width"],info["height"])!=(128,72) or info["pixel_type"]!="HALF":
            raise RuntimeError("Non-16-bit-half or invalid EXR source")
        staged=root/("verified_%06d.exr"%frame["frame"])
        staged.write_bytes(raw)
        run([ffmpeg,"-nostdin","-v","error","-xerror","-i",str(staged),
             "-frames:v","1","-f","null","-"],"Independent EXR pixel decoder")
        frameproof.append({"frame":frame["frame"],"sha256":frame["image_sha256"],
                           "full_decode":True,"metadata":info})
    # Create a controlled scene-linear emissive pixel range reference in a
    # separate Blender scene; never change the approved take to insert probes.
    probe_py=root/"hdr_control.py"
    probe_py.write_text(PROBE_SCRIPT,"utf-8")
    probe=root/"hdr_control.exr"
    run([blender,"-b","-t","2","--python",str(probe_py),"--",str(probe)],
        "Blender half-float HDR diagnostic",timeout=240)
    probe_info=exr_info(probe.read_bytes())
    if (probe_info["width"],probe_info["height"])!=(64,64):
        raise RuntimeError("HDR probe header mismatch")
    decoded=run([ffmpeg,"-nostdin","-v","error","-xerror","-i",str(probe),
                 "-frames:v","1","-pix_fmt","gbrapf32le","-f","rawvideo","-"],
                "Independent native RGBA float32 EXR decoder",binary=True)
    samples=array("f")
    samples.frombytes(decoded.stdout)
    if sys.byteorder!="little":samples.byteswap()
    n=64*64
    # Keep alpha. FFmpeg swscale GBRAPf32 -> GBRf32 clips >1 radiance,
    # so converting to RGB before measuring would invent a false failure.
    if len(samples)!=n*4:
        raise RuntimeError("Independent native RGBA float32 sample size mismatch")
    center=32*64+32
    green,blue,red=samples[center],samples[n+center],samples[2*n+center]
    if (not 1.9<red<2.6 or not .32<green<.42 or not .045<blue<.075 or
        abs(green-round(green*255)/255)<.0002):
        raise RuntimeError("EXR HDR was clipped, quantized or transformed: "+
                           repr((red,green,blue)))
    # Restore a tampered stored frame and insist that a new FilmIndex refuses it.
    path=idx._blob_path(pid,frames[0]["image_sha256"])
    valid=path.read_bytes()
    try:
        corrupt=bytearray(valid)
        corrupt[-1]^=1
        path.write_bytes(corrupt)
        try:
            PresentationPipeline(Studio(db)).reopen(pid,"color01a_scene_linear_exr")
        except RuntimeError:
            pass
        else:
            raise RuntimeError("Forged EXR survived independent FilmIndex reopen")
    finally:
        path.write_bytes(valid)
    PresentationPipeline(Studio(db)).reopen(pid,"color01a_scene_linear_exr")
    if fresh.capture.reopen(pid,"take_real_captured")["record"]["document_sha256"]!=take_sha:
        raise RuntimeError("Original Digital Take changed during EXR acceptance")
    report={"format":"nvp.color01a.native.acceptance.v1",
            "status":"real_cycles_scene_linear_half_float_verified",
            "scene_linear_exr_source_count":len(frameproof),
            "frozen_take_sha256":take_sha,
            "presentation_sha256":verified["record"]["document_sha256"],
            "frame_evidence":frameproof,"hdr_emission_rgb":[red,green,blue],
            "hdr_probe_sha256":hashlib.sha256(probe.read_bytes()).hexdigest(),
            "independent_decoder":"ffmpeg","restart_reopen":True,
            "tampered_exr_refused":True,"original_take_unchanged":True,
            "not_certified":["ACES/OCIO conversion","colorimetric accuracy",
                             "theatrical DCP mastering","approved sound","photoreal assets"]}
    (root/"color01a_report.json").write_text(json.dumps(report,indent=2,sort_keys=True),"utf-8")
    return report

if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",required=True)
    parser.add_argument("--blender",default="blender")
    parser.add_argument("--ffmpeg",default="ffmpeg")
    args=parser.parse_args()
    print(json.dumps(fixture(args.out,blender=args.blender,ffmpeg=args.ffmpeg),indent=2))
