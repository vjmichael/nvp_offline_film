"""AUDIO-01K.1 approved-film distribution custody, no counterfeit DCP.

The first bounded distribution profile is a lossless COPY of the verified
AUDIO-01J ProRes+PCM24 MOV. This does NOT transcode, certify or package a DCP.
The trusted native host owns creator-event authorization and publication.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil

from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_audio01k_fault_matrix import crash_after
from backend.nvp_audio01j_final_av import FORMAT as FINAL_AV_FORMAT
from backend.nvp_audio01i_mastering import sha_file
from backend.nvp_film_index import _id

FORMAT="nvp.audio01k.distribution_package.v1"
PROFILE="mezzanine_prores_pcm24_mov_v1"
MAX_COPY_BYTES=5*1024*1024*1024


def _safe_file(path):
    p=Path(path)
    if p.is_symlink() or not p.is_file():
        raise RuntimeError("Missing or symlinked media input")
    return p


def _copy_fsync(source,dest):
    """No overwrite; bound copy and SHA original bytes while writing."""
    total=0
    digest=hashlib.sha256()
    with source.open("rb") as inp,dest.open("xb") as output:
        while part:=inp.read(1024*1024):
            total+=len(part)
            if total>MAX_COPY_BYTES:
                raise RuntimeError("Distribution media exceeds bounded copy size")
            output.write(part)
            digest.update(part)
        output.flush()
        os.fsync(output.fileno())
    return digest.hexdigest(),total


def publish_mezzanine(capture,project_id,export_id,distribution_id,final_av_dir,
                      destination,*,verify_native_master):
    """Host-authorized and pre-verified exact source copy; not creator approval."""
    _id(distribution_id,"distribution ID")
    if not callable(verify_native_master):
        raise PermissionError("Native final-master verifier is required")
    try:capture.index.read_revision(project_id,distribution_id)
    except KeyError:pass
    else:raise RuntimeError("Distribution identity already indexed")
    source=capture.index.read_revision(project_id,export_id,1)
    if (source["kind"]!="master" or source["data"].get("format")!=FINAL_AV_FORMAT
        or source["data"].get("final_master") is not True
        or source["data"].get("director_approved") is not True
        or source["data"].get("dcp_delivered") is not False):
        raise PermissionError("Only creator-approved audiovisual master may be packaged")
    verified=verify_native_master()
    if (verified.get("status")!="VERIFIED_FINAL_AV_MASTER"
        or verified.get("final_master") is not True):
        raise RuntimeError("AUDIO-01J native worker/creator proof is unavailable")
    origin=Path(final_av_dir)
    movie=_safe_file(origin/"final_picture_sound.mov")
    if origin.is_symlink() or not origin.is_dir():
        raise RuntimeError("Unsafe source AV directory")
    expected=source["data"]["rendered_mov_sha256"]
    if sha_file(movie)!=expected:
        raise RuntimeError("Approved AV master bytes changed")
    target=Path(destination).absolute()
    staged=target.with_name("."+target.name+".audio01k.stage")
    if (target.exists() or target.is_symlink() or staged.exists() or
        staged.is_symlink() or not target.parent.is_dir() or
        target.parent.is_symlink()):
        raise RuntimeError("Delivery destination/staging already exists")
    staged.mkdir(mode=0o700)
    crash_after("staging_directory_created")
    dest_movie=staged/"feature_master.mov"
    digest,size=_copy_fsync(movie,dest_movie)
    crash_after("movie_bytes_fsynced")
    if digest!=expected or sha_file(movie)!=expected:
        raise RuntimeError("Distribution source/copy SHA mismatch")
    # A checked copy is not a DCP; profile is intentionally explicit.
    document={
        "format":FORMAT,"status":"verified_mezzanine_distribution",
        "profile":PROFILE,"project_id":project_id,"export_id":export_id,
        "export_revision":1,"export_document_sha256":source["document_sha256"],
        "source_movie_sha256":expected,"delivered_movie_sha256":digest,
        "delivered_movie_bytes":size,"movie_filename":"feature_master.mov",
        "frames":source["data"]["frames"],"fps":24,"sample_rate":48000,
        "audio_channels":2,"audio_bit_depth":24,
        "video_codec_intent":"source_prores_stream_copy",
        "creator_approved_export":True,"final_master":True,
        "dcp_delivered":False,"dcp_compliant":False
    }
    with (staged/"manifest.json").open("xb") as f:
        f.write(canonical_bytes(document))
        f.flush()
        os.fsync(f.fileno())
    crash_after("manifest_fsynced")
    checksums=staged/"SHA256SUMS"
    with checksums.open("xb") as f:
        f.write((digest+"  feature_master.mov\n").encode("ascii"))
        f.flush()
        os.fsync(f.fileno())
    crash_after("checksums_fsynced")
    os.replace(staged,target)
    if os.name=="posix":
        fd=os.open(str(target.parent),os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
        try:os.fsync(fd)
        finally:os.close(fd)
    crash_after("directory_promoted")
    indexed=capture.index.register_revision(
        project_id,distribution_id,"master",document,
        expected_revision=0,
        dependencies=[{"object_id":export_id,"revision":1,"role":"presentation"}])
    crash_after("filmindex_registered")
    return {"status":"MEZZANINE_DISTRIBUTION_PUBLISHED",
            "distribution_id":distribution_id,
            "document_sha256":indexed["document_sha256"],
            "movie_sha256":digest,"dcp_delivered":False}


def verify_mezzanine(capture,project_id,distribution_id,destination,*,
                     verify_native_master):
    record=capture.index.read_revision(project_id,distribution_id,1)
    doc=record["data"]
    if (record["kind"]!="master" or record["revision"]!=1
        or doc.get("format")!=FORMAT or doc.get("profile")!=PROFILE
        or doc.get("status")!="verified_mezzanine_distribution"
        or doc.get("dcp_delivered") is not False
        or doc.get("dcp_compliant") is not False):
        raise RuntimeError("Not an indexed mezzanine distribution")
    source=capture.index.read_revision(project_id,doc["export_id"],1)
    if (source["kind"]!="master" or
        source["document_sha256"]!=doc["export_document_sha256"] or
        source["data"].get("rendered_mov_sha256")!=doc["source_movie_sha256"]):
        raise RuntimeError("Mezzanine master provenance changed")
    deps=[{"object_id":doc["export_id"],"revision":1,"role":"presentation"}]
    if record["dependencies"]!=deps:
        raise RuntimeError("Mezzanine dependency edges changed")
    proof=verify_native_master()
    if proof.get("status")!="VERIFIED_FINAL_AV_MASTER":
        raise PermissionError("Native final audiovisual approval was revoked or missing")
    folder=Path(destination)
    if folder.is_symlink() or not folder.is_dir():
        raise RuntimeError("Missing distribution output directory")
    movie=_safe_file(folder/"feature_master.mov")
    manifest=_safe_file(folder/"manifest.json")
    sums=_safe_file(folder/"SHA256SUMS")
    if (manifest.read_bytes()!=canonical_bytes(doc) or
        sums.read_bytes()!=(doc["delivered_movie_sha256"]+
                           "  feature_master.mov\n").encode("ascii") or
        sha_file(movie)!=doc["delivered_movie_sha256"] or
        movie.stat().st_size!=doc["delivered_movie_bytes"]):
        raise RuntimeError("Distribution manifest, checksums or bytes changed")
    return {"status":"VERIFIED_MEZZANINE_DISTRIBUTION",
            "movie_sha256":doc["delivered_movie_sha256"],
            "dcp_delivered":False}
