"""WO4 feature-length file-backed multi-reel DCP publisher.

Consumes a frozen, native-host-approved sequence of already indexed cinema
reel receipts. Source MXFs are never modified/hardlinked into a codec worker.
Copies bounded 1 MiB chunks, writes a CPL containing distinct ordered reels,
a PKL and AssetMap enumerating all MXF essence. An independent structural
audit must pass before OS no-replace publication. No FFmpeg or full-film RAM.
"""
from __future__ import annotations

from datetime import datetime,timezone
from hashlib import sha1,sha256
import base64
import os
from pathlib import Path
import xml.etree.ElementTree as ET

from backend.nvp_wo3_dcp_structure import (
    NS_CPL,NS_PKL,NS_AM,inspect_dcp_structure)
from backend.nvp_wo3_dcp_package import _tag,_xml
from backend.nvp_wo3_atomic_publish import (
    atomic_publish_directory,_fsync_directory)
from backend.nvp_wo3_native_codecs import digest_file
from backend.nvp_wo4_file_dcp import _uuid,_memory_digest
from backend.nvp_wo4_resource_budget import MAX_REELS
from backend.nvp_production_journal import TICKS_PER_SECOND
from backend.nvp_wo3_j2k_audit import PROFILES

FORMAT="nvp.wo4.file_multireel_dcp.v1"
BLOCK=1024*1024
FILM_FRAME_TICKS=TICKS_PER_SECOND//24
MAX_TRACK_BYTES=1024**4

def _check_manifest(reels,ids):
    if (type(reels) is not list or not 2<=len(reels)<=MAX_REELS or
            type(ids) is not dict or set(ids)!={"cpl","pkl","assetmap"}):
        raise ValueError("Approved ordered multi-reel manifest required")
    all_ids=set()
    for val in ids.values():
        _uuid(val)
        all_ids.add(val)
    frame_total=0
    for i,part in enumerate(reels):
        if (type(part) is not dict or
                set(part)!={"start_tick","end_tick","frames",
                            "reel_uuid","picture","sound"}):
            raise PermissionError("Unexpected or missing frozen reel manifest fields")
        for key in ("start_tick","end_tick","frames"):
            if type(part[key]) is not int:
                raise PermissionError("Signed integer Film Time and frame count required")
        if (not 3<=part["frames"]<=7200 or
                part["start_tick"]!=frame_total*FILM_FRAME_TICKS or
                part["end_tick"]!=part["start_tick"]+part["frames"]*FILM_FRAME_TICKS):
            raise PermissionError("Reels must form contiguous exact 24fps film timeline")
        frame_total+=part["frames"]
        _uuid(part["reel_uuid"])
        if part["reel_uuid"] in all_ids:
            raise PermissionError("Duplicated SMPTE reel UUID")
        all_ids.add(part["reel_uuid"])
        for name in ("picture","sound"):
            track=part[name]
            if (type(track) is not dict or
                    set(track)!={"file_path","file_sha256","file_bytes","asset_uuid"}
                    or type(track["file_sha256"]) is not str or
                    len(track["file_sha256"])!=64 or
                    any(c not in "0123456789abcdef" for c in track["file_sha256"])
                    or type(track["file_bytes"]) is not int or
                    not 128<=track["file_bytes"]<=MAX_TRACK_BYTES):
                raise PermissionError("SHA-pinned genuine cinema MXF receipt required")
            _uuid(track["asset_uuid"])
            if track["asset_uuid"] in all_ids:
                raise PermissionError("Duplicated SMPTE asset UUID")
            all_ids.add(track["asset_uuid"])
            path=Path(track["file_path"])
            if not path.is_absolute() or path.is_symlink() or not path.is_file():
                raise PermissionError("Trusted absolute source MXF is unavailable")
            if path.stat().st_size!=track["file_bytes"] or digest_file(path)!=track["file_sha256"]:
                raise PermissionError("Previously verified original MXF changed")
    return frame_total

def _stream_copy(src,dest,expected,check_cancel):
    path=Path(src)
    if path.is_symlink() or not path.is_file():
        raise PermissionError("Source MXF changed while packaging")
    sha1sum=sha1()
    sha256sum=sha256()
    size=0
    with path.open("rb") as inp,dest.open("xb") as out:
        while chunk:=inp.read(BLOCK):
            if check_cancel():
                raise InterruptedError("Feature output was explicitly cancelled")
            size+=len(chunk)
            if size>MAX_TRACK_BYTES:
                raise ValueError("MXF larger than approved feature budget")
            sha1sum.update(chunk)
            sha256sum.update(chunk)
            out.write(chunk)
        out.flush();os.fsync(out.fileno())
    if (size!=expected["file_bytes"] or
            sha256sum.hexdigest()!=expected["file_sha256"] or
            digest_file(path)!=expected["file_sha256"]):
        raise PermissionError("Feature MXF changed during copy")
    return {"bytes":size,"sha256":sha256sum.hexdigest(),
            "sha1_b64":base64.b64encode(sha1sum.digest()).decode("ascii")}

def _make_xml(reels,ids,title,issued,metadata,profile):
    cpl=ET.Element("{"+NS_CPL+"}CompositionPlaylist")
    for k,v in (("Id",_uuid(ids["cpl"])),("AnnotationText",title),
                ("IssueDate",issued),("Issuer","NVP Native Cinema"),
                ("Creator","NVP immutable assembly"),
                ("ContentTitleText",title),("ContentKind","feature")):
        _tag(cpl,NS_CPL,k,v)
    list_el=ET.SubElement(cpl,"{"+NS_CPL+"}ReelList")
    for part in reels:
        reel=ET.SubElement(list_el,"{"+NS_CPL+"}Reel")
        _tag(reel,NS_CPL,"Id",_uuid(part["reel_uuid"]))
        assets=ET.SubElement(reel,"{"+NS_CPL+"}AssetList")
        for kind,tag in (("picture","MainPicture"),("sound","MainSound")):
            entry=ET.SubElement(assets,"{"+NS_CPL+"}"+tag)
            for k,v in (("Id",_uuid(part[kind]["asset_uuid"])),
                        ("EditRate","24 1"),
                        ("IntrinsicDuration",part["frames"]),
                        ("EntryPoint",0),("Duration",part["frames"])):
                _tag(entry,NS_CPL,k,v)
            if kind=="picture":
                width,height,_=PROFILES[profile]
                _tag(entry,NS_CPL,"ScreenAspectRatio",f"{width} {height}")
    xmls={"CPL.xml":_xml(cpl)}
    metadata["CPL.xml"]=_memory_digest(xmls["CPL.xml"])
    entries=[]
    for i,part in enumerate(reels):
        for kind in ("picture","sound"):
            filename=f"{kind}_{i:04d}.mxf"
            entries.append((part[kind]["asset_uuid"],filename,"application/mxf"))
    entries.append((ids["cpl"],"CPL.xml","text/xml"))
    pkl=ET.Element("{"+NS_PKL+"}PackingList")
    for k,v in (("Id",_uuid(ids["pkl"])),("AnnotationText",title),
                ("IssueDate",issued),("Issuer","NVP Native Cinema"),
                ("Creator","NVP immutable assembly")):
        _tag(pkl,NS_PKL,k,v)
    list_el=ET.SubElement(pkl,"{"+NS_PKL+"}AssetList")
    for uid,filename,mime in entries:
        asset=ET.SubElement(list_el,"{"+NS_PKL+"}Asset")
        for k,v in (("Id",_uuid(uid)),("AnnotationText",filename),
                    ("Hash",metadata[filename]["sha1_b64"]),
                    ("Size",metadata[filename]["bytes"]),("Type",mime),
                    ("OriginalFileName",filename)):
            _tag(asset,NS_PKL,k,v)
    xmls["PKL.xml"]=_xml(pkl)
    metadata["PKL.xml"]=_memory_digest(xmls["PKL.xml"])
    amap=ET.Element("{"+NS_AM+"}AssetMap")
    for k,v in (("Id",_uuid(ids["assetmap"])),("AnnotationText",title),
                ("IssueDate",issued),("Issuer","NVP Native Cinema"),
                ("Creator","NVP immutable assembly"),("VolumeCount",1)):
        _tag(amap,NS_AM,k,v)
    list_el=ET.SubElement(amap,"{"+NS_AM+"}AssetList")
    for uid,filename,mime in [(ids["pkl"],"PKL.xml","text/xml"),*entries]:
        asset=ET.SubElement(list_el,"{"+NS_AM+"}Asset")
        _tag(asset,NS_AM,"Id",_uuid(uid))
        if filename=="PKL.xml":
            _tag(asset,NS_AM,"PackingList","true")
        chunks=ET.SubElement(asset,"{"+NS_AM+"}ChunkList")
        chunk=ET.SubElement(chunks,"{"+NS_AM+"}Chunk")
        for k,v in (("Path",filename),("VolumeIndex",1),
                    ("Offset",0),("Length",metadata[filename]["bytes"])):
            _tag(chunk,NS_AM,k,v)
    xmls["ASSETMAP.xml"]=_xml(amap)
    vol=ET.Element("{"+NS_AM+"}VolumeIndex")
    _tag(vol,NS_AM,"Index",1)
    xmls["VOLINDEX.xml"]=_xml(vol)
    for name in ("ASSETMAP.xml","VOLINDEX.xml"):
        metadata[name]=_memory_digest(xmls[name])
    return xmls

def publish_multireel_dcp(*,reels,ids,title,profile,output_root,check_cancel):
    if (not callable(check_cancel) or type(title) is not str or
            not 1<=len(title)<=80 or
            any(ord(c)<32 or c in "<>&" for c in title)
            or profile not in PROFILES):
        raise ValueError("Trusted bounded feature publication required")
    frames=_check_manifest(reels,ids)
    root=Path(output_root)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise PermissionError("Host-selected feature output directory required")
    root=root.resolve(strict=True)
    stage=root/(".nvp-feature-stage-"+ids["cpl"])
    target=root/("DCP_FEATURE_"+ids["cpl"])
    if (stage.exists() or stage.is_symlink() or
            target.exists() or target.is_symlink()):
        raise FileExistsError("Existing output or interrupted stage requires review")
    stage.mkdir(mode=0o700)
    metadata={}
    for i,part in enumerate(reels):
        for kind in ("picture","sound"):
            source=part[kind]
            filename=f"{kind}_{i:04d}.mxf"
            metadata[filename]=_stream_copy(
                source["file_path"],stage/filename,source,check_cancel)
    issued=datetime.now(timezone.utc).isoformat(timespec="seconds")
    xmls=_make_xml(reels,ids,title,issued,metadata,profile)
    for name,data in xmls.items():
        if check_cancel():
            raise InterruptedError("Feature packaging cancelled")
        with (stage/name).open("xb") as out:
            out.write(data)
            out.flush();os.fsync(out.fileno())
    report=inspect_dcp_structure(stage)
    if (report["status"]!="STRUCTURE_AND_SHA_VERIFIED" or
            report["reel_count"]!=len(reels) or
            report["reel_durations"]!=[x["frames"] for x in reels] or
            report["cpl_uuid"]!=ids["cpl"]):
        raise RuntimeError("Independent feature DCP structural verification failed")
    if check_cancel():
        raise InterruptedError("Approved creator cancelled before feature publication")
    _fsync_directory(stage)
    atomic_publish_directory(stage,target)
    return {"format":FORMAT,"status":"MULTIREEL_STRUCTURAL_DCP_PUBLISHED",
            "destination":str(target),"cpl_uuid":ids["cpl"],
            "reel_count":len(reels),"total_frames":frames,
            "file_sha256":{k:v["sha256"] for k,v in metadata.items()},
            "whole_feature_in_ram":False,"source_modified":False,
            "production_dcp_accepted":False,
            "independent_dci_acceptance":False}
