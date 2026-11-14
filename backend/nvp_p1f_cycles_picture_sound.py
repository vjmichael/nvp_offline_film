"""P1-F trusted host: original 3D/USD -> supervised Cycles PNG + actor PCM.

This is ONE exact picture instant and its original-source 1/24s stereo audio,
not a long-film export. No Blender executable, script, output or source path
comes from an untrusted model. Production approval and kernel custody remain
the responsibility of the trusted host/OS; failure never publishes a film.
"""
from __future__ import annotations

import base64
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
import wave

from backend.nvp_blender_worker import (
    BlenderOperation, BlenderWorkerSupervisor, sha_file)
from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_p1f_cycles_source_admission import admit_original_frame
from backend.nvp_p1f_p2_reel_plan import (
    P1FReelPlan, SAMPLES_PER_FRAME)
from backend.nvp_temporal_ledger import TICKS_PER_SECOND

FORMAT="nvp.p1f.supervised_original_actor_frame.v1"
RECEIPT="nvp.p1f.independent_picture_audio_receipt.v1"
SHAPES=("jawOpen","lipClose","eyeBlink","browRaise")
MAX_USDA=8*1024*1024
WORKER=Path(__file__).resolve().parents[1]/"tools/nvp_p1f_cycles_actor_worker.py"


def _canonical(v):
    return json.dumps(v,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")


def _add_file(path,data):
    if type(data) is not bytes or path.exists() or path.is_symlink():
        raise RuntimeError("Refuse preexisting/altered supervised source file")
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _wav_pcm(pcm):
    if type(pcm) is not bytes or len(pcm)!=SAMPLES_PER_FRAME*4:
        raise RuntimeError("Original source audio does not match one 24fps interval")
    out=io.BytesIO()
    with wave.open(out,"wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(48000)
        f.writeframes(pcm)
    return out.getvalue()


class P1FOriginalPictureSound:
    def __init__(self,index:FilmIndex,supervisor:BlenderWorkerSupervisor,
                 *,approve_render, verify_isolated_worker,
                 public_fixture_mode=False):
        if (not isinstance(index,FilmIndex) or
                not isinstance(supervisor,BlenderWorkerSupervisor) or
                not callable(approve_render) or
                not callable(verify_isolated_worker)):
            raise TypeError("Native FilmIndex, OS-supervised Blender and creator approval required")
        if not WORKER.is_file() or WORKER.is_symlink():
            raise RuntimeError("Reviewed bundled Cycles script is unavailable")
        self.index=index
        self.supervisor=supervisor
        if type(public_fixture_mode) is not bool:
            raise TypeError("Production vs synthetic test mode must be explicit")
        if public_fixture_mode and os.environ.get("NVP_PUBLIC_SYNTHETIC_CI")!="1":
            raise PermissionError("Public fixture exception unavailable in installed NVP")
        self.public_fixture_mode=public_fixture_mode
        self.approve=approve_render
        self.verify_isolated_worker=verify_isolated_worker
        self.plan=P1FReelPlan(index)

    def _original(self,pid,plan_id,reel,frame):
        admission=admit_original_frame(self.index,pid,plan_id,reel,frame)
        if len(admission["actor_geometry"])!=1:
            raise RuntimeError("Single P1-F sample frame requires one verified imported actor")
        path=next(iter(admission["actor_geometry"]))
        record=self.index.read_revision(pid,admission["take_id"],1)
        src=record["data"]
        scene,stage=OpenUSDSceneBridge(self.index).open(
            pid,src["scene_id"],src["scene_revision"])
        from pxr import Usd,UsdSkel
        prim=stage.GetPrimAtPath(path+"/Animation")
        if not prim or not prim.IsA(UsdSkel.Animation):
            raise RuntimeError("Cannot evaluate original actor facial source animation")
        animation=UsdSkel.Animation(prim)
        names=tuple(str(x) for x in animation.GetBlendShapesAttr().Get() or [])
        if names!=SHAPES:
            raise RuntimeError("Source facial controls changed after approved Take")
        vals=animation.GetBlendShapeWeightsAttr().Get(
            Usd.TimeCode(float(admission["source_tick"])))
        if vals is None or len(vals)!=len(SHAPES):
            raise RuntimeError("Original facial performance cannot be sampled")
        facial=[float(v) for v in vals]
        actor=stage.GetPrimAtPath(path)
        actor_id=actor.GetAttribute("nvp:actorID").Get()
        if type(actor_id) is not str or not actor_id.startswith("ACT_"):
            raise RuntimeError("Composed original actor lost its authoritative ActorID")
        flattened=stage.Flatten().ExportToString().encode("utf8")
        if (not 100<=len(flattened)<=MAX_USDA or
                b"@" in flattened or
                not flattened.lstrip().startswith(b"#usda 1.0")):
            raise RuntimeError("Original composed shot cannot be flattened without external assets")
        return admission,path,actor_id,facial,flattened

    def render_frame(self,pid,plan_id,reel_index,frame_offset,job_id, *,
                     creator_event,width=320,height=180,samples=12):
        _require_pid(pid)
        _id(plan_id,"original film source reel")
        _id(job_id,"non-replayable Blender job ID")
        if (type(width) is not int or type(height) is not int or
                not 128<=width<=1920 or not 72<=height<=1080 or
                type(samples) is not int or not 4<=samples<=128):
            raise ValueError("Invalid bounded genuine Cycles output contract")
        original,path,actor_id,facial,usda=self._original(
            pid,plan_id,reel_index,frame_offset)
        reel=self.plan.read(pid,plan_id)
        source=self.plan.picture_instant(pid,plan_id,reel_index,frame_offset)
        first=source["output_tick"]//(TICKS_PER_SECOND//48000)
        edit_doc=reel["data"]
        selected=self.plan.editor.plan(
            pid,edit_doc["edit_id"],edit_doc["edit_revision"],
            first_sample=first,count=1)
        for sound in selected["slices"][0]["audio"]:
            if sound["enabled"] and sound["actor_id"]!=actor_id:
                raise RuntimeError("Actor-owned PCM and original 3D actor identity disagree")
        mix=self.plan.audio_window(
            pid,plan_id,reel_index,
            first_sample=first,count=SAMPLES_PER_FRAME)
        pcm=base64.b64decode(mix["pcm_base64"],validate=True)
        if sha256(pcm).hexdigest()!=mix["pcm_sha256"]:
            raise RuntimeError("Source-based audio bytes mismatch verified PCM digest")
        wav=_wav_pcm(pcm)
        spec={
            "format":FORMAT,
            "scene_sha256":original["scene_document_sha256"],
            "usd_sha256":sha256(usda).hexdigest(),
            "camera":original["camera_path"],
            "actor_id":actor_id,
            "actor_path":path,
            "source_tick":original["source_tick"],
            "expected_face_weights":facial,
            "width":width,"height":height,"samples":samples,
        }
        approved_scope={
            "operation":"nvp.p1f.render_original_cycles_frame.v1",
            "project_id":pid,"plan_id":plan_id,
            "plan_document_sha256":reel["document_sha256"],
            "source_admission_sha256":original["receipt_sha256"],
            "usda_sha256":spec["usd_sha256"],
            "pcm_sha256":mix["pcm_sha256"],
            "job_id":job_id,
        }
        if self.approve(creator_event,dict(approved_scope)) is not True:
            raise PermissionError("Creator did not authorize exact source-bound Cycles frame")
        # Windows Job/delegated Linux cgroup controls resource/process custody,
        # but neither proves a restricted filesystem namespace or no egress.
        # The independently trusted production host MUST affirm an actual,
        # finite OS boundary for this exact source/job. No CI bypass for real
        # creator film content and no unsafe 'isolated=True' caller flag.
        sandbox_scope={
            **approved_scope,"require_no_network":True,
            "require_private_filesystem_isolation":True,
            "worker_executable_sha256":self.supervisor.binary_sha256,
            "fixed_script_sha256":sha256(WORKER.read_bytes()).hexdigest(),
        }
        if self.verify_isolated_worker(dict(sandbox_scope)) is not True:
            raise PermissionError("Genuine private film Cycles worker isolation not established")
        if not self.public_fixture_mode:
            # No caller-supplied True can bypass native OS preflight. Linux
            # requires a root-owned bubblewrap namespace and delegated
            # cgroup; Windows private AppContainer/WFP remains fail closed.
            from backend.nvp_worker_private_sandbox import prove_private_kernel_boundary
            # A successful constructor/argv check is not kernel proof. This
            # launches and independently observes a real delegated cgroup +
            # private mount/network namespace before any actor USD/PCM bytes
            # are staged for the production Blender worker.
            prove_private_kernel_boundary(self.supervisor.root)
        jobdir=self.supervisor.root/job_id
        jobdir.mkdir(parents=False,exist_ok=False)
        source_script=WORKER.read_bytes()
        _add_file(jobdir/"fixed_cycles.py",source_script)
        _add_file(jobdir/"original.usda",usda)
        _add_file(jobdir/"original_pcm.wav",wav)
        _add_file(jobdir/"frame_spec.json",_canonical(spec))
        op=BlenderOperation(
            job_id=job_id,script="fixed_cycles.py",
            script_sha256=sha256(source_script).hexdigest(),
            inputs={
                "original.usda":sha256(usda).hexdigest(),
                "original_pcm.wav":sha256(wav).hexdigest(),
                "frame_spec.json":sha_file(jobdir/"frame_spec.json"),
            },
            outputs={"original_frame.png":"png","cycles_audit.json":"json_audit"},
            arguments={
                "--plan":"frame_spec.json",
                "--take":"original.usda",
                "--output":"original_frame.png",
                "--audit":"cycles_audit.json",
            },
            timeout_seconds=600,memory_limit_mb=8192,
            # Kernel-level whole-tree containment is REQUIRED; do not use
            # the legacy Linux PDEATHSIG/process-group-only fallback.
            require_linux_cgroup_v2=True,
            require_private_isolation=not self.public_fixture_mode)
        outcome=self.supervisor.run(op)
        if outcome.get("state")!="SUCCEEDED":
            return {"status":"NOT_DELIVERED","job_id":job_id,
                    "worker_state":outcome.get("state"),
                    "worker_error":outcome.get("error")}
        receipt=self._verify_bytes(
            pid,plan_id,job_id,original,source,mix,width,height,samples)
        payload={"format":RECEIPT,"passed":True,
                 "project_id":pid,"plan_id":plan_id,
                 "job_id":job_id,
                 "plan_document_sha256":reel["document_sha256"],
                 "original_source":original,
                 "original_picture":receipt["picture"],
                 "original_derived_audio":receipt["audio"],
                 "worker_receipt":outcome["spec_sha256"],
                 "picture_rendered":True,
                 "entire_film_rendered":False,
                 "master_approved":False}
        _add_file(jobdir/"host_delivery_receipt.json",_canonical(payload))
        return payload

    def _verify_bytes(self,pid,plan_id,job_id,original,frame,mix,width,height,samples):
        jobdir=self.supervisor.root/job_id
        worker=self.supervisor.verify_completed(job_id)
        audit=json.loads((jobdir/"cycles_audit.json").read_text("utf8"))
        spec=json.loads((jobdir/"frame_spec.json").read_text("utf8"))
        if (audit.get("passed") is not True or
                audit.get("format")!=FORMAT or
                audit.get("render_engine")!="CYCLES" or
                audit.get("source_tick")!=original["source_tick"] or
                audit.get("scene_sha256")!=original["scene_document_sha256"] or
                audit.get("input_usd_sha256")!=spec["usd_sha256"] or
                audit.get("original_camera")!=original["camera_path"].rsplit("/",1)[-1] or
                audit.get("imported_armature_count",0)<1 or
                audit.get("width")!=width or audit.get("height")!=height or
                audit.get("samples")!=samples):
            raise RuntimeError("Independently reopened Cycles result/source identity mismatch")
        faces=audit.get("actual_shape_keys")
        if (type(faces) is not dict or set(faces)!=set(SHAPES) or
                any(abs(faces[name]-spec["expected_face_weights"][i])>.035
                    for i,name in enumerate(SHAPES))):
            raise RuntimeError("Rendered facial performance changed from original USD")
        png=jobdir/"original_frame.png"
        if sha_file(png)!=audit["png_sha256"]:
            raise RuntimeError("Blender PNG no longer matches worker picture receipt")
        from PIL import Image
        with Image.open(png) as image:
            image.load()
            if image.format!="PNG" or image.size!=(width,height):
                raise RuntimeError("Independent picture decode or dimensions failed")
            extrema=image.convert("RGB").getextrema()
            if not any(hi>lo for lo,hi in extrema):
                raise RuntimeError("Cycles frame is a blank/constant image")
        wav=jobdir/"original_pcm.wav"
        with wave.open(str(wav),"rb") as f:
            if (f.getnchannels()!=2 or f.getframerate()!=48000 or
                    f.getsampwidth()!=2 or
                    f.getnframes()!=SAMPLES_PER_FRAME):
                raise RuntimeError("Delivered actor-owned sound clock changed")
            delivered=f.readframes(SAMPLES_PER_FRAME)
        if sha256(delivered).hexdigest()!=mix["pcm_sha256"]:
            raise RuntimeError("Independent sound WAV readback differs from original 3D scene")
        sound_again=self.plan.audio_window(
            pid,plan_id,frame["reel_index"],
            first_sample=frame["output_tick"]//(TICKS_PER_SECOND//48000),
            count=SAMPLES_PER_FRAME)
        if sound_again["pcm_sha256"]!=mix["pcm_sha256"]:
            raise RuntimeError("Original actor PCM changed between render and independent verification")
        return {"picture":{"png_sha256":sha_file(png),"width":width,"height":height,
                           "engine":"Cycles","source_tick":original["source_tick"]},
                "audio":{"wav_sha256":sha_file(wav),
                         "pcm_sha256":mix["pcm_sha256"],
                         "sample_count":SAMPLES_PER_FRAME,
                         "source_owned":True}}

    def verify_delivered(self,pid,plan_id,job_id):
        """Restart-safe recheck; a completed Blender journal alone is NOT a film."""
        _require_pid(pid);_id(plan_id,"source plan");_id(job_id,"worker job")
        jobdir=self.supervisor.root/job_id
        receipt_path=jobdir/"host_delivery_receipt.json"
        if not receipt_path.is_file() or receipt_path.is_symlink():
            raise RuntimeError("No independently verified P1-F delivery receipt")
        receipt=json.loads(receipt_path.read_text("utf8"))
        plan=self.plan.read(pid,plan_id)
        if (receipt.get("format")!=RECEIPT or receipt.get("passed") is not True or
                receipt.get("project_id")!=pid or receipt.get("plan_id")!=plan_id or
                receipt.get("job_id")!=job_id or
                receipt.get("plan_document_sha256")!=plan["document_sha256"] or
                receipt.get("entire_film_rendered") is not False or
                receipt.get("master_approved") is not False):
            raise RuntimeError("P1-F delivery receipt lost source/approval identity")
        original=receipt["original_source"]
        expected=self.plan.picture_instant(
            pid,plan_id,
            next(i for i,x in enumerate(plan["data"]["reels"])
                 if x["first_frame"]<=original["output_tick"]//(TICKS_PER_SECOND//24)
                 <x["first_frame"]+x["frame_count"]),
            (original["output_tick"]//(TICKS_PER_SECOND//24))%240)
        if (expected["source_take_sha256"]!=original["take_document_sha256"] or
                expected["source_tick"]!=original["source_tick"]):
            raise RuntimeError("Original source conform differs after restart")
        spec=json.loads((jobdir/"frame_spec.json").read_text("utf8"))
        mix=self.plan.audio_window(
            pid,plan_id,
            original["output_tick"]//(TICKS_PER_SECOND*10),
            first_sample=original["output_tick"]//(TICKS_PER_SECOND//48000),
            count=SAMPLES_PER_FRAME)
        checked=self._verify_bytes(
            pid,plan_id,job_id,original,
            {"reel_index":original["output_tick"]//(TICKS_PER_SECOND*10),
             "output_tick":original["output_tick"]},
            mix,spec["width"],spec["height"],spec["samples"])
        if (checked["picture"]!=receipt["original_picture"] or
                checked["audio"]!=receipt["original_derived_audio"] or
                self.supervisor.inspect(job_id)["spec_sha256"]!=receipt["worker_receipt"]):
            raise RuntimeError("Restart/replay picture/sound receipt changed")
        return receipt
