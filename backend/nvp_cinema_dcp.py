"""NVP-CINEMA-01A: DCP planning and guarded packaging via DCP-o-matic.

A DCP is a *directory of digital cinema essence and manifests*, not a
QuickTime .mov. This module provides preflight and an opt-in adapter for the
existing DCP-o-matic CLI. Never claim cinema readiness merely because the
packager exits with code 0. The current NVP source lacks approved final audio,
scene-linear/P3 color validation, licensed high-res human assets and independent
theater ingest. Its initial DCP packages are TECHNICAL TEST ONLY.

There is no proprietary NVP DCP muxer. The host must install/configure trusted
DCP-o-matic and verifier applications. Never run arbitrary user-supplied scripts.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import shutil
import subprocess
from backend.nvp_w1g_owned_subprocess import run_owned_subprocess
import xml.etree.ElementTree as ET

from backend.nvp_film_index import FilmIndex, _id
from backend.nvp_full_motion import FullMotionPipeline
from backend.nvp_cinema_essence import audit_dcp_picture_essence
from backend.nvp_cinema_duration import (
    DURATION_EXACT, plan_cinema_duration, validate_duration_contract
)
from backend.nvp_studio import Studio

# Film Festival 2K: selected SMPTE test settings. Content is fitted to one
# profile by the mature packager; current 128/256px source is *upscaled*.
DCP_PROFILES = {
    "smpte_2k_flat_24": {
        "ratio": "185", "raster": [1998, 1080], "fps": 24,
        "standard": "SMPTE", "format": "2K Flat",
    },
    "smpte_2k_scope_24": {
        "ratio": "239", "raster": [2048, 858], "fps": 24,
        "standard": "SMPTE", "format": "2K Scope",
    },
}
DCP_PACKAGE_FORMAT = "nvp.presentation.dcp.technical.v2"
REQUIRED_XML_TAGS = frozenset(("CompositionPlaylist","PackingList","AssetMap"))
SAFE_TITLE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,79}\Z")
MAX_FILES = 300
MAX_DCP_BYTES = 2*1024*1024*1024  # small first-run package, not long-form yet


def _process(args, timeout, purpose):
    try:
        r=run_owned_subprocess(args,capture_output=True,text=True,
                         timeout=timeout,check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(purpose+" timed out; DCP not registered") from exc
    if r.returncode:
        raise RuntimeError(purpose+" failed; DCP not registered: "+
                           (r.stdout+"\n"+r.stderr)[-1000:])
    return r.stdout+"\n"+r.stderr


def _program(name, override):
    found=shutil.which(override if override else name)
    if not found:
        raise RuntimeError("DCP-o-matic executable unavailable: "+name)
    return found


def _sha_file(path):
    h=hashlib.sha256()
    size=0
    with Path(path).open("rb") as handle:
        while block := handle.read(1024*1024):
            size+=len(block)
            if size > MAX_DCP_BYTES:
                raise RuntimeError("DCP file size exceeds current bounded test budget")
            h.update(block)
    return h.hexdigest(),size


def inspect_dcp_folder(path):
    """A structural integrity audit, NOT an independent JPEG2000/MXF decoder.

    In addition to this check, an actual independent DCP validator/projector
    ingest is necessary before advertising cinema compatibility.
    """
    root=Path(path)
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError("DCP output directory missing or symlinked")
    root=root.resolve()
    files=[]
    total=0
    discovered=set()
    for file in sorted(root.rglob("*")):
        if file.is_symlink():
            raise RuntimeError("DCP package contains symbolic link")
        if file.is_dir():
            continue
        if not file.is_file() or not file.resolve().is_relative_to(root):
            raise RuntimeError("Unsafe or missing DCP asset")
        rel=file.relative_to(root).as_posix()
        if len(files)>=MAX_FILES:
            raise RuntimeError("Unbounded DCP asset count")
        digest,size=_sha_file(file)
        if size<1:
            raise RuntimeError("DCP contains empty asset")
        total+=size
        if total>MAX_DCP_BYTES:
            raise RuntimeError("DCP package exceeds 2 GiB technical test budget")
        if file.suffix.lower()==".mxf":
            discovered.add("MXF")
        if file.suffix.lower()==".xml" or file.name.upper() in ("ASSETMAP","VOLINDEX"):
            # No external entities/dynamic network resolution or asset imports.
            if size>16*1024*1024:
                raise RuntimeError("Unexpectedly large DCP XML metadata")
            try:
                tree=ET.parse(file)
            except (ET.ParseError,ValueError) as exc:
                raise RuntimeError("Invalid DCP XML metadata") from exc
            tag=tree.getroot().tag.rsplit("}",1)[-1]
            if tag in REQUIRED_XML_TAGS:
                discovered.add(tag)
        files.append({"path":rel,"sha256":digest,"size_bytes":size})
    if not REQUIRED_XML_TAGS.issubset(discovered) or "MXF" not in discovered:
        raise RuntimeError("DCP is incomplete: missing ASSETMAP/PKL/CPL or MXF essence")
    return {"format":"nvp.dcp.directory.audit.v1","files":files,
            "total_bytes":total,"asset_count":len(files),
            "components":sorted(discovered),
            "status":"structural_only_not_cinema_conformance"}


class CinemaDCP:
    def __init__(self,studio:Studio,index:FilmIndex|None=None):
        self.studio=studio
        self.index=index if index is not None else FilmIndex(studio)
        self.motion=FullMotionPipeline(studio,self.index)

    def preflight(self,project_id,motion_id,*,profile="smpte_2k_flat_24",
                  audio_policy="require_approved_sound",
                  duration_policy=DURATION_EXACT):
        """Grounded, read-only validation that cannot certify exhibition."""
        _id(motion_id,"cinema source presentation ID")
        if profile not in DCP_PROFILES:
            raise ValueError("Unknown requested DCP profile")
        if audio_policy not in ("require_approved_sound","explicit_silent_test"):
            raise ValueError("Unknown cinema soundtrack policy")
        source=self.motion.reopen(project_id,motion_id)
        motion=source["record"]["data"]
        spec=DCP_PROFILES[profile]
        blockers=[]
        warnings=[]
        if motion["source_fps"]!=spec["fps"]:
            blockers.append("Selected DCP profile requires exact 24fps")
        try:
            duration = plan_cinema_duration(
                motion["frame_count"], motion["source_fps"], duration_policy)
        except RuntimeError as exc:
            duration = None
            blockers.append(str(exc))
        if duration and duration["black_tail_frames"]:
            warnings.append(
                "An explicit one-second technical-only duration exception will append "
                + str(duration["black_tail_frames"]) +
                " independently verified black frames, without changing the frozen take")

        if audio_policy=="require_approved_sound":
            blockers.append("NVP has no approved 48kHz/24-bit cinema dialogue/music/sound mix yet")
        else:
            warnings.append("Technical silent-picture test only: an approved soundtrack is absent")
            if motion.get("dialogue_timeline"):
                warnings.append("Original take contains dialogue cues; no audible dialogue will be present")
        if min(motion["width"],motion["height"])<720:
            warnings.append("Small source image will be upscaled for the 2K cinema raster")
        warnings.extend([
            "Source color is not yet independently measured/validated as DCI X'Y'Z' 12-bit",
            "OpenEXR/real high-bit-depth master and theater ingestion are not yet validated",
            "DCP packaging requires DCP-o-matic CLI; NVP does not supply a proprietary MXF/J2K encoder",
            "This does not certify DCI/SMPTE Bv2.1 or any theater's projection server",
        ])
        return {"status":"blocked" if blockers else "technical_test_only",
                "source_motion_id":motion_id,
                "source_motion_sha256":source["record"]["document_sha256"],
                "source_video_sha256":source["media"]["sha256"],
                "source_fps":motion["source_fps"],
                "source_frames":motion["frame_count"],
                "profile":profile,"spec":dict(spec),
                "audio_policy":audio_policy,
                "duration_policy":duration_policy,
                "duration_contract":duration,
                "blockers":blockers,"warnings":warnings}

    def package_technical_test(self,project_id,motion_id,dcp_id,output_root, *,
                               name="NVP Technical Test",
                               profile="smpte_2k_flat_24",
                               audio_policy="require_approved_sound",
                               director_silent_test_approval=False,
                               duration_policy=DURATION_EXACT,
                               director_padding_approval=False,
                               create_bin=None,encode_bin=None,verify_bin=None,
                               timeout=600):
        """Opt-in technical DCP, not projector-certified and not final film.

        To protect the filmmaker, absent approved audio blocks by default.
        Even an explicitly confirmed silent test does not become an approved
        theatrical master. An independent verification tool is mandatory.
        """
        _id(dcp_id,"cinema package ID")
        if not SAFE_TITLE.fullmatch(name):
            raise ValueError("Use an ASCII film name with simple cinema filename characters")
        if type(timeout) is not int or not 20<=timeout<=7200:
            raise ValueError("Invalid DCP worker budget")
        plan=self.preflight(project_id,motion_id,profile=profile,
                            audio_policy=audio_policy,
                            duration_policy=duration_policy)
        if plan["blockers"]:
            raise RuntimeError("Cinema preflight blocked: "+"; ".join(plan["blockers"]))
        if audio_policy!="explicit_silent_test" or not director_silent_test_approval:
            raise RuntimeError("Explicit creator acceptance is required for a silent DCP technical test")
        if plan["duration_contract"]["black_tail_frames"] and not director_padding_approval:
            raise RuntimeError("Explicit director approval required for technical black-tail padding")

        try:
            self.index.read_revision(project_id,dcp_id)
        except KeyError:
            pass
        else:
            raise RuntimeError("DCP identity already published; never overwrite a finished version")
        create=_program("dcpomatic2_create",create_bin)
        encode=_program("dcpomatic2_cli",encode_bin)
        verify=_program("dcpomatic2_verify_cli",verify_bin)
        root=Path(output_root)
        if root.is_symlink():
            raise RuntimeError("Cinema output directory is a symlink")
        root=root.resolve()
        root.mkdir(parents=True,exist_ok=True)
        # Derive workspace name from identity, never user-supplied path strings.
        workspace=root/("cinema_"+hashlib.sha256(
            (project_id+"|"+dcp_id).encode("utf-8")).hexdigest()[:24])
        workspace.mkdir(exist_ok=False)
        project_dir=workspace/"project"
        media=self.motion.reopen(project_id,motion_id,check_decode=True)
        if media["record"]["document_sha256"]!=plan["source_motion_sha256"]:
            raise RuntimeError("Cinema source changed after preflight")
        # DCP-o-matic's CLI owns all SMPTE conforming JPEG2000 and MXF logic.
        # Source is a 24-fps project-linked, content-hash-verified media file.
        source=media["media"]["path"]
        _process([create,"-n",name,"--no-encrypt","-c","TST","-f","24",
                  "--twok","--twod","--standard","SMPTE",
                  "--container-ratio",plan["spec"]["ratio"],
                  "-a","6","--colourspace","rec709",
                  "-o",str(project_dir),source],
                 timeout,"DCP-o-matic film setup")
        # Restrict to local encoder processes (no silent remote machine upload).
        _process([encode,"--no-remote","--threads","2",str(project_dir)],
                 timeout,"DCP-o-matic film encode")
        # Find actual generated DCP, not a newly invented filesystem layout.
        candidates=[]
        for folder in project_dir.rglob("*"):
            if folder.is_dir() and (
                (folder/"ASSETMAP").is_file() or
                (folder/"ASSETMAP.xml").is_file()):
                candidates.append(folder)
        if len(candidates)!=1:
            raise RuntimeError("Expected exactly one cinema package from the installed packager")
        dcp_dir=candidates[0]
        structure=inspect_dcp_folder(dcp_dir)
        # Decode the real unencrypted JPEG 2000 picture essence independently.
        # Do not equate picture verification with color or theater approval.
        picture=audit_dcp_picture_essence(
            dcp_dir, expected_raster=plan["spec"]["raster"],
            expected_fps=plan["spec"]["fps"],
            expected_frames=plan["source_frames"],
            duration_contract=plan["duration_contract"], timeout=timeout)
        # An independent DCP conformance check is obligatory. The exact
        # executable/CLI contract is tool-version dependent; a successful
        # subprocess result is not theater ingest certification.
        output=_process([verify,str(dcp_dir)],timeout,"Independent DCP package verifier")
        if re.search(r"(?i)(?:\b[1-9]\d*\s+errors?\b|\berror\s*:|\bfatal\s*:|\bverification failed\b)",output):
            raise RuntimeError("Independent DCP verifier reported errors")
        # Rehash source *again* before committing a linked package receipt.
        current=self.motion.reopen(project_id,motion_id,check_decode=True)
        if (current["record"]["document_sha256"]!=plan["source_motion_sha256"] or
            current["media"]["sha256"]!=plan["source_video_sha256"]):
            raise RuntimeError("Cinema source changed during packaging")
        data={"format":DCP_PACKAGE_FORMAT,"status":"verified_technical_dcp_not_screening_ready",
              "source_motion_id":motion_id,
              "source_motion_sha256":plan["source_motion_sha256"],
              "source_video_sha256":plan["source_video_sha256"],
              "source_take_id":current["record"]["data"].get("source_take_id"),
              "source_take_sha256":current["record"]["data"].get("source_take_sha256"),
              "duration_contract":plan["duration_contract"],
              "director_padding_approval":bool(director_padding_approval and
                  plan["duration_contract"]["black_tail_frames"]),
              "profile":profile,"audio_policy":audio_policy,
              "director_silent_test_approval":True,
              "dcp_path":str(dcp_dir),"structure":structure,
              "picture_evidence":picture,
              "creator_warnings":plan["warnings"],
              "validator":"dcpomatic2_verify_cli",
              "limitation":"Independent theater/projector ingest and color/sound quality not certified"}
        if (not isinstance(data["source_take_id"],str) or
            not isinstance(data["source_take_sha256"],str) or
            len(data["source_take_sha256"])!=64):
            raise RuntimeError("Cinema source missing frozen source-take lineage")
        receipt=self.index.register_revision(project_id,dcp_id,"presentation",data,
            dependencies=[
                {"object_id":motion_id,"revision":1,"role":"presentation"},
                {"object_id":data["source_take_id"],"revision":1,"role":"source_take"},
            ])
        return {"record":receipt,"source":plan,"structure":structure,
                "picture_evidence":picture,
                "package_dir":str(dcp_dir),"status":data["status"]}

    def reopen(self,project_id,dcp_id,*,check_decode=False):
        record=self.index.read_revision(project_id,dcp_id)
        data=record["data"]
        if record["kind"]!="presentation" or data.get("format")!=DCP_PACKAGE_FORMAT:
            raise RuntimeError("Not an indexed technical cinema package")
        expected=sorted([
            {"object_id":data["source_motion_id"],
             "revision":1,"role":"presentation"},
            {"object_id":data["source_take_id"],
             "revision":1,"role":"source_take"},
        ],key=lambda x:(x["object_id"],x["revision"],x["role"]))
        if record["dependencies"]!=expected:
            raise RuntimeError("DCP lineage is not bound to its exact video presentation")
        source=self.motion.reopen(project_id,data["source_motion_id"])
        if (source["record"]["document_sha256"]!=data["source_motion_sha256"] or
            source["media"]["sha256"]!=data.get("source_video_sha256")):
            raise RuntimeError("DCP was not bound to the original movie bytes and motion source")
        motion_data=source["record"]["data"]
        if (motion_data.get("source_take_id")!=data.get("source_take_id") or
            motion_data.get("source_take_sha256")!=data.get("source_take_sha256")):
            raise RuntimeError("DCP no longer has the approved source take identity")
        expected_duration=validate_duration_contract(
            data.get("duration_contract"), motion_data["frame_count"],
            motion_data["source_fps"])
        if (expected_duration["black_tail_frames"] and
            data.get("director_padding_approval") is not True):
            raise RuntimeError("Stored DCP black-tail exception lacks creator approval")
        if (data.get("picture_evidence",{}).get("duration_contract")!=expected_duration or
            data["picture_evidence"].get("source_frames")!=expected_duration["source_frames"]):
            raise RuntimeError("DCP picture proof is not bound to its duration contract")

        if data.get("picture_evidence",{}).get("status")!=\
                "independent_mxf_jpeg2000_decode_technical_only":
            raise RuntimeError("Missing independently decoded DCP picture evidence")
        check=inspect_dcp_folder(data["dcp_path"])
        if check!=data["structure"]:
            raise RuntimeError("DCP package bytes or manifests changed since indexing")
        if check_decode:
            source_verified=self.motion.reopen(
                project_id,data["source_motion_id"],check_decode=True)
            if source_verified["media"]["sha256"]!=data["source_video_sha256"]:
                raise RuntimeError("Source movie changed during cinema reopen audit")
            measured=audit_dcp_picture_essence(
                data["dcp_path"],
                expected_raster=DCP_PROFILES[data["profile"]]["raster"],
                expected_fps=expected_duration["fps"],
                expected_frames=expected_duration["source_frames"],
                duration_contract=expected_duration)
            if measured!=data["picture_evidence"]:
                raise RuntimeError("Independent DCP picture/decode evidence disagrees on reopen")
        return {"record":record,"structure":check,
                "status":"stored_technical_dcp_integrity_only",
                "screening_ready":False}
