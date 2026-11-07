"""WO4-LF02/04 file-backed SMPTE DCP output from immutable MXF receipts.

The earlier WO3 author accepts entire MXF byte arrays. This author instead
streams approved picture/sound files into same-volume stage storage, creates
CPL/PKL/AssetMap/VOLINDEX using exact file hashes, independently reopens and
audits the staged package, then uses the existing OS-enforced NO-REPLACE
directory promotion. It never deletes uncommitted stage evidence.

This component publishes a STRUCTURAL candidate only. FilmIndex commit is a
separate durable supervisor transition; projector/independent DCI validation
is not implied. No FFmpeg.
"""
from __future__ import annotations

import base64
from datetime import datetime,timezone
import hashlib
import os
from pathlib import Path
import re
import uuid
import xml.etree.ElementTree as ET

from backend.nvp_wo3_dcp_package import _tag, _xml, FORMAT as PACKAGE_FORMAT
from backend.nvp_wo3_dcp_structure import (
    NS_AM,NS_PKL,NS_CPL,inspect_dcp_structure)
from backend.nvp_wo3_atomic_publish import atomic_publish_directory,_fsync_directory
from backend.nvp_wo3_native_codecs import digest_file
from backend.nvp_wo3_j2k_audit import PROFILES

FORMAT="nvp.wo4.file_backed_smpte_dcp.v1"
MAX_ASSET_BYTES=1024*1024*1024*1024
COPY_BLOCK=1024*1024
UUID4=re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
SHA=re.compile(r"[0-9a-f]{64}\Z")

def _uuid(value):
    if type(value) is not str or not UUID4.fullmatch(value):
        raise ValueError("Canonical DCP UUIDv4 required")
    return "urn:uuid:"+value

def _stream_digest(file):
    file=Path(file)
    if file.is_symlink() or not file.is_file():
        raise PermissionError("DCP source MXF missing or symlinked")
    sha1=hashlib.sha1()
    sha256=hashlib.sha256()
    total=0
    with file.open("rb") as source:
        while chunk:=source.read(COPY_BLOCK):
            total+=len(chunk)
            if total>MAX_ASSET_BYTES:
                raise ValueError("MXF exceeds bounded cinema asset limit")
            sha1.update(chunk)
            sha256.update(chunk)
    return {
        "bytes":total,
        "sha1_b64":base64.b64encode(sha1.digest()).decode("ascii"),
        "sha256":sha256.hexdigest()
    }

def _track(track,kind,source_sha,profile,frames):
    if (type(track) is not dict or
            track.get("kind")!=kind or
            track.get("asset_uuid") is None or
            track.get("source_take_sha256")!=source_sha or
            track.get("file_sha256") is None or
            not SHA.fullmatch(track["file_sha256"]) or
            type(track.get("file_bytes")) is not int or
            not 128<=track["file_bytes"]<=MAX_ASSET_BYTES or
            track.get("frame_count")!=frames or
            track.get("edit_rate")!=[24,1] or
            track.get("source_modified") is not False or
            track.get("production_dcp_accepted") is not False):
        raise PermissionError("Exact native file-backed MXF track receipt required")
    _uuid(track["asset_uuid"])
    file=Path(track.get("file_path",""))
    if not file.is_absolute() or file.is_symlink() or not file.is_file():
        raise PermissionError("Trusted host-verified MXF file path required")
    if kind=="picture" and track.get("profile")!=profile:
        raise PermissionError("Picture MXF source profile differs")
    actual=_stream_digest(file)
    if (actual["sha256"]!=track["file_sha256"] or
            actual["bytes"]!=track["file_bytes"]):
        raise PermissionError("Source MXF changed before DCP creation")
    return file,actual

def _xml_package(*,title,issued,ids,profile,frames,metadata):
    pic_id=_uuid(ids["picture"])
    snd_id=_uuid(ids["sound"])
    cpl_id=_uuid(ids["cpl"])
    pkl_id=_uuid(ids["pkl"])
    am_id=_uuid(ids["assetmap"])
    reel_id=_uuid(ids["reel"])
    if len(set(ids.values()))!=len(ids):
        raise ValueError("All DCP identifiers must be distinct")
    cpl=ET.Element("{"+NS_CPL+"}CompositionPlaylist")
    for k,v in (("Id",cpl_id),("AnnotationText",title),("IssueDate",issued),
                ("Issuer","NVP Source-Preserving Cinema Output"),
                ("Creator","NVP native deterministic DCP"),
                ("ContentTitleText",title),("ContentKind","feature")):
        _tag(cpl,NS_CPL,k,v)
    reels=ET.SubElement(cpl,"{"+NS_CPL+"}ReelList")
    reel=ET.SubElement(reels,"{"+NS_CPL+"}Reel")
    _tag(reel,NS_CPL,"Id",reel_id)
    assets=ET.SubElement(reel,"{"+NS_CPL+"}AssetList")
    for tag,uid in (("MainPicture",pic_id),("MainSound",snd_id)):
        entry=ET.SubElement(assets,"{"+NS_CPL+"}"+tag)
        for k,v in (("Id",uid),("EditRate","24 1"),
                    ("IntrinsicDuration",frames),("EntryPoint",0),
                    ("Duration",frames)):
            _tag(entry,NS_CPL,k,v)
        if tag=="MainPicture":
            w,h,_=PROFILES[profile]
            _tag(entry,NS_CPL,"ScreenAspectRatio",f"{w} {h}")
    xmls={"CPL.xml":_xml(cpl)}
    entries=[(pic_id,"picture.mxf","application/mxf"),
             (snd_id,"sound.mxf","application/mxf"),
             (cpl_id,"CPL.xml","text/xml")]
    metadata["CPL.xml"]=_memory_digest(xmls["CPL.xml"])
    pkl=ET.Element("{"+NS_PKL+"}PackingList")
    for k,v in (("Id",pkl_id),("AnnotationText",title),("IssueDate",issued),
                ("Issuer","NVP Source-Preserving Cinema Output"),
                ("Creator","NVP native deterministic DCP")):
        _tag(pkl,NS_PKL,k,v)
    listed=ET.SubElement(pkl,"{"+NS_PKL+"}AssetList")
    for asset_id,name,mime in entries:
        entry=ET.SubElement(listed,"{"+NS_PKL+"}Asset")
        for k,v in (("Id",asset_id),("AnnotationText",name),
                    ("Hash",metadata[name]["sha1_b64"]),
                    ("Size",metadata[name]["bytes"]),
                    ("Type",mime),("OriginalFileName",name)):
            _tag(entry,NS_PKL,k,v)
    xmls["PKL.xml"]=_xml(pkl)
    metadata["PKL.xml"]=_memory_digest(xmls["PKL.xml"])
    amap=ET.Element("{"+NS_AM+"}AssetMap")
    for k,v in (("Id",am_id),("AnnotationText",title),("IssueDate",issued),
                ("Issuer","NVP Source-Preserving Cinema Output"),
                ("Creator","NVP native deterministic DCP"),
                ("VolumeCount",1)):
        _tag(amap,NS_AM,k,v)
    mapped=ET.SubElement(amap,"{"+NS_AM+"}AssetList")
    for asset_id,name,_mime in [(pkl_id,"PKL.xml","text/xml"),*entries]:
        entry=ET.SubElement(mapped,"{"+NS_AM+"}Asset")
        _tag(entry,NS_AM,"Id",asset_id)
        if name=="PKL.xml":
            _tag(entry,NS_AM,"PackingList","true")
        chunks=ET.SubElement(entry,"{"+NS_AM+"}ChunkList")
        chunk=ET.SubElement(chunks,"{"+NS_AM+"}Chunk")
        for k,v in (("Path",name),("VolumeIndex",1),("Offset",0),
                    ("Length",metadata[name]["bytes"])):
            _tag(chunk,NS_AM,k,v)
    xmls["ASSETMAP.xml"]=_xml(amap)
    vol=ET.Element("{"+NS_AM+"}VolumeIndex")
    _tag(vol,NS_AM,"Index",1)
    xmls["VOLINDEX.xml"]=_xml(vol)
    for name in ("ASSETMAP.xml","VOLINDEX.xml"):
        metadata[name]=_memory_digest(xmls[name])
    return xmls

def _memory_digest(value):
    return {
        "bytes":len(value),
        "sha256":hashlib.sha256(value).hexdigest(),
        "sha1_b64":base64.b64encode(hashlib.sha1(value).digest()).decode("ascii")
    }

def publish_file_backed_dcp(*,job_id,picture,sound,title,profile,frames,
                             output_root,ids,check_cancel):
    if (type(job_id) is not str or
            type(title) is not str or not 1<=len(title)<=80 or
            any(ord(c)<32 or c in "<>&" for c in title) or
            profile not in PROFILES or type(frames) is not int or
            not 3<=frames<=7200 or not callable(check_cancel) or
            type(ids) is not dict or set(ids)!={
                "picture","sound","cpl","pkl","assetmap","reel"}):
        raise ValueError("Native approved source-bound DCP publication scope required")
    # Name comes only from trusted UUIDv4 stored in the journal.
    from uuid import UUID
    if str(UUID(job_id))!=job_id:
        raise ValueError("Canonical job identity required")
    for value in ids.values():_uuid(value)
    root=Path(output_root)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise PermissionError("Trusted OS-selected output directory required")
    root=root.resolve(strict=True)
    if (picture.get("source_take_sha256")!=sound.get("source_take_sha256")
            or picture.get("asset_uuid")!=ids["picture"]
            or sound.get("asset_uuid")!=ids["sound"]):
        raise PermissionError("Original Take and MXF asset identities disagree")
    pic,_=_track(picture,"picture",picture["source_take_sha256"],profile,frames)
    snd,_=_track(sound,"sound",picture["source_take_sha256"],profile,frames)
    stage=root/(".nvp-wo4-dcp-stage-"+job_id)
    target=root/("DCP_"+ids["cpl"])
    if stage.is_symlink() or stage.exists() or target.is_symlink() or target.exists():
        raise FileExistsError("Existing or interrupted DCP stage requires review")
    stage.mkdir(mode=0o700)
    # Deliberately retain stage for post-crash/manual review; never rmtree it.
    try:
        metadata={}
        for src,name,expected in ((pic,"picture.mxf",picture),
                                  (snd,"sound.mxf",sound)):
            if check_cancel():
                raise InterruptedError("Creator cancelled DCP stage")
            destination=stage/name
            sha1=hashlib.sha1()
            sha256=hashlib.sha256()
            total=0
            with src.open("rb") as stream, destination.open("xb") as out:
                while chunk:=stream.read(COPY_BLOCK):
                    if check_cancel():
                        raise InterruptedError("Creator cancelled DCP copy")
                    total+=len(chunk)
                    if total>MAX_ASSET_BYTES:
                        raise ValueError("DCP MXF larger than safe asset bound")
                    sha1.update(chunk);sha256.update(chunk);out.write(chunk)
                out.flush();os.fsync(out.fileno())
            if (total!=expected["file_bytes"] or
                    sha256.hexdigest()!=expected["file_sha256"] or
                    digest_file(src)!=expected["file_sha256"]):
                raise PermissionError("Source or private-copy MXF hash mismatch")
            metadata[name]={
                "bytes":total,"sha256":sha256.hexdigest(),
                "sha1_b64":base64.b64encode(sha1.digest()).decode("ascii")}
        now=datetime.now(timezone.utc).isoformat(timespec="seconds")
        xmls=_xml_package(title=title,issued=now,ids=ids,profile=profile,
                           frames=frames,metadata=metadata)
        for name,data in xmls.items():
            with (stage/name).open("xb") as out:
                out.write(data)
                out.flush();os.fsync(out.fileno())
        audit=inspect_dcp_structure(stage)
        if (audit["status"]!="STRUCTURE_AND_SHA_VERIFIED" or
                audit["reel_count"]!=1 or
                audit["reel_durations"]!=[frames] or
                audit["cpl_uuid"]!=ids["cpl"]):
            raise RuntimeError("Independent SMPTE DCP package audit rejected")
        if check_cancel():
            raise InterruptedError("Creator cancelled before package promotion")
        _fsync_directory(stage)
        atomic_publish_directory(stage,target)
        # A crash after promotion but before journal commit leaves the exact
        # target directory; reconciliation will require creator review.
        return {"format":FORMAT,"status":"STRUCTURAL_FILE_DCP_PUBLISHED",
                "destination":str(target),"target_name":target.name,
                "file_sha256":{k:v["sha256"] for k,v in metadata.items()},
                "assetmap_uuid":"urn:uuid:"+ids["assetmap"],
                "pkl_uuid":"urn:uuid:"+ids["pkl"],
                "cpl_uuid":"urn:uuid:"+ids["cpl"],
                "frame_count":frames,
                "source_take_sha256":picture["source_take_sha256"],
                "independent_structure_sha_verified":True,
                "mxf_essence_independently_verified":False,
                "production_dcp_accepted":False,"source_modified":False,
                "ffmpeg_used":False,"whole_mxf_loaded_into_ram":False}
    except BaseException:
        # Never touch creator-approved source or delete a crash-stage.
        raise
