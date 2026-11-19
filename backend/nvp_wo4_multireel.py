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
from backend.nvp_wo3_dcp_package import _tag,_xml,_content_version
from backend.nvp_wo3_atomic_publish import (
    atomic_publish_directory,_fsync_directory)
from backend.nvp_wo3_native_codecs import digest_file
from backend.nvp_wo4_file_dcp import _uuid,_memory_digest,_track,_export_root,_assert_export_root,_stream_digest
from backend.nvp_wo4_pcm_stream import _protected_path,_hash_stream
from backend.nvp_wo3_native_codecs import _sha
from backend.nvp_wo3_dcp_structure import _linked_entry
from copy import deepcopy
from backend.nvp_wo4_resource_budget import MAX_REELS,require_stage_space
from backend.nvp_temporal_ledger import TICKS_PER_SECOND
from backend.nvp_wo3_j2k_audit import PROFILES

FORMAT="nvp.wo4.file_multireel_dcp.v1"
BLOCK=1024*1024
FILM_FRAME_TICKS=TICKS_PER_SECOND//24
MAX_TRACK_BYTES=1024**4

def _check_manifest(reels,ids,source_take_sha256,profile,*,source_reel_authority=None):
    if (type(reels) is not list or not 2<=len(reels)<=MAX_REELS or
            type(ids) is not dict or set(ids)!={"cpl","pkl","assetmap"}):
        raise ValueError("Approved ordered multi-reel manifest required")
    _sha(source_take_sha256)
    if source_reel_authority is not None:
        if type(source_reel_authority) is not list or len(source_reel_authority)!=len(reels):
            raise PermissionError('Ordered feature source authority required')
        for entry in source_reel_authority:
            if type(entry) is not dict or set(entry)!={'source_take_sha256','mastering_decision_sha256','indexed_receipt_sha256'}:
                raise PermissionError('Exact indexed reel authority required')
            for digest in entry.values(): _sha(digest)
    all_ids=set()
    for val in ids.values():
        _uuid(val)
        all_ids.add(val)
    if len(all_ids)!=len(ids):
        raise PermissionError("Duplicate package identity")
    source_files=set()
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
            origin=source_take_sha256 if source_reel_authority is None else source_reel_authority[i]["source_take_sha256"]
            path,_=_track(track,name,origin,profile,part["frames"])
            identity=_protected_path(path)
            if identity in source_files or track["asset_uuid"] in all_ids:
                raise PermissionError("Duplicated source file or SMPTE asset identity")
            source_files.add(identity)
            all_ids.add(track["asset_uuid"])
    return frame_total

def _stream_copy(src,dest,expected,check_cancel):
    path=Path(src)
    identity=_protected_path(path)
    sha1sum=sha1()
    sha256sum=sha256()
    size=0
    with path.open("rb") as inp,dest.open("xb") as out:
        info=os.fstat(inp.fileno())
        if (info.st_dev,info.st_ino)!=identity:
            raise PermissionError("Source MXF changed at open")
        while chunk:=inp.read(BLOCK):
            if check_cancel():
                raise InterruptedError("Feature output was explicitly cancelled")
            size+=len(chunk)
            if size>expected["file_bytes"]:
                raise ValueError("MXF larger than approved feature budget")
            sha1sum.update(chunk)
            sha256sum.update(chunk)
            out.write(chunk)
        out.flush();os.fsync(out.fileno())
    if (size!=expected["file_bytes"] or
            sha256sum.hexdigest()!=expected["file_sha256"] or
            _protected_path(path)!=identity or
            _hash_stream(path)!=(expected["file_sha256"],expected["file_bytes"])):
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
    _content_version(cpl,title,ids["cpl"])
    list_el=ET.SubElement(cpl,"{"+NS_CPL+"}ReelList")
    for i,part in enumerate(reels):
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
            _tag(entry,NS_CPL,"Hash",metadata[f"{kind}_{i:04d}.mxf"]["sha1_b64"])
            if kind=="picture":
                _tag(entry,NS_CPL,"FrameRate","24 1")
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
                ("Creator","NVP immutable assembly"),("VolumeCount",1),
                ("IssueDate",issued),("Issuer","NVP Native Cinema")):
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

def publish_multireel_dcp(*,reels,ids,title,profile,output_root,check_cancel,
                          approve,source_take_sha256,mastering_decision_sha256,
                          source_reel_authority=None,feature_assembly_sha256=None):
    if (not callable(check_cancel) or not callable(approve) or type(title) is not str or
            not 1<=len(title)<=80 or
            any(ord(c)<32 or c in "<>&" for c in title)
            or profile not in PROFILES):
        raise ValueError("Trusted bounded feature publication required")
    _sha(source_take_sha256)
    _sha(mastering_decision_sha256)
    reels,ids=deepcopy(reels),deepcopy(ids)
    source_reel_authority=deepcopy(source_reel_authority)
    if source_reel_authority is not None:
        _sha(feature_assembly_sha256)
        if (type(source_reel_authority) is not list or not source_reel_authority or
            type(source_reel_authority[0]) is not dict or
            source_reel_authority[0].get("source_take_sha256")!=source_take_sha256 or
            source_reel_authority[0].get("mastering_decision_sha256")!=mastering_decision_sha256):
            raise PermissionError("Leading reel identity differs from approved feature scope")
    elif feature_assembly_sha256 is not None:
        raise PermissionError('Feature assembly requires ordered reel authority')
    frames=_check_manifest(reels,ids,source_take_sha256,profile,source_reel_authority=source_reel_authority)
    root,root_identity=_export_root(output_root)
    # The approved source MXF sizes bound the data copied into one feature
    # package. Require storage headroom before creating any stage output.
    require_stage_space(root,sum(part[kind]["file_bytes"]
        for part in reels for kind in ("picture","sound"))+
        (len(reels)+2)*1024*1024)
    stage=root/(".nvp-feature-stage-"+ids["cpl"])
    target=root/("DCP_FEATURE_"+ids["cpl"])
    if (stage.exists() or _linked_entry(stage) or
            target.exists() or _linked_entry(target)):
        raise FileExistsError("Existing output or interrupted stage requires review")
    scope={"operation":"nvp.wo4.export_multireel_candidate.v1",
           "source_take_sha256":source_take_sha256,
           "mastering_decision_sha256":mastering_decision_sha256,
           "reels":reels,"ids":ids,"title":title,"profile":profile,
           "source_reel_authority":source_reel_authority,"feature_assembly_sha256":feature_assembly_sha256,
           "frames":frames,"output_root":str(root),
           "plaintext_export_explicitly_requested":True}
    if approve(deepcopy(scope)) is not True:
        return {"format":FORMAT,"status":"DENIED","source_modified":False}
    _assert_export_root(root,root_identity)
    _check_manifest(reels,ids,source_take_sha256,profile,source_reel_authority=source_reel_authority)
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
    from backend.nvp_dci_package import inspect_cinema_package
    approved=[]
    start=0
    for part in reels:
        approved.append({"reel_uuid":part["reel_uuid"],"start_frame":start,"frames":part["frames"],"picture_uuid":part["picture"]["asset_uuid"],"sound_uuid":part["sound"]["asset_uuid"]})
        start+=part["frames"]
    report=inspect_cinema_package(stage,expected_profile=profile,expected_reels=approved)
    if (report["status"]!="STRUCTURE_AND_SHA_VERIFIED" or
            report["reel_count"]!=len(reels) or
            report["reel_durations"]!=[x["frames"] for x in reels] or
            report["cpl_uuid"]!=ids["cpl"]):
        raise RuntimeError("Independent feature DCP structural verification failed")
    if check_cancel():
        raise InterruptedError("Approved creator cancelled before feature publication")
    _assert_export_root(root,root_identity)
    if set(p.name for p in stage.iterdir())!=set(metadata) or any(
            _stream_digest(stage/name)!=record for name,record in metadata.items()):
        raise PermissionError("Feature stage changed after audit")
    _fsync_directory(stage)
    atomic_publish_directory(stage,target)
    return {"format":FORMAT,"status":"MULTIREEL_STRUCTURAL_DCP_PUBLISHED",
            "destination":str(target),"cpl_uuid":ids["cpl"],
            "reel_count":len(reels),"total_frames":frames,
            "source_take_sha256":source_take_sha256,
            "mastering_decision_sha256":mastering_decision_sha256,
            "source_reel_authority":source_reel_authority,"feature_assembly_sha256":feature_assembly_sha256,
            "file_sha256":{k:v["sha256"] for k,v in metadata.items()},
            "whole_feature_in_ram":False,"source_modified":False,
            "production_dcp_accepted":False,
            "independent_dci_acceptance":False}
