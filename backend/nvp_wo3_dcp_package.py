"""WO3-04: immutable-source, native-approved SMPTE DCP package author.

Accepts only exact SHA-verified outputs from the trusted native ASDCP wrappers;
never imports original Takes into MXF and never treats an MXF filename as
proof of picture or sound essence. This stage authors real SMPTE package XML,
including CPL/PKL/ASSETMAP/VOLINDEX, and independently reopens its output.
Director approval, immutable FilmIndex Take binding, and no-overwrite
publication are mandatory. Final DCI/decoder/projector acceptance stays open.
"""
from __future__ import annotations
import base64
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import uuid
import xml.etree.ElementTree as ET

from backend.nvp_film_index import FilmIndex,_id,_sha
from backend.nvp_wo3_dcp_structure import (
    inspect_dcp_structure,NS_AM,NS_PKL,NS_CPL)
from backend.nvp_wo3_mxf_native import FORMAT as MXF_FORMAT
from backend.nvp_wo3_j2k_audit import PROFILES

FORMAT="nvp.wo3.source_bound_dcp_candidate.v1"
MAX_REEL_BYTES=1024*1024*1024*1024

def _tag(parent,ns,name,value):
    node=ET.SubElement(parent,"{"+ns+"}"+name)
    node.text=str(value)
    return node

def _u():
    return "urn:uuid:"+str(uuid.uuid4())

def _xml(root):
    return ET.tostring(root,encoding="utf-8",xml_declaration=True)

def _sha_bytes(data):
    return hashlib.sha256(data).hexdigest()

def _hash_pkl(data):
    return base64.b64encode(hashlib.sha1(data).digest()).decode("ascii")

def _asset(track,kind,source_sha):
    if (type(track) is not dict or track.get("format")!=MXF_FORMAT or
        track.get("kind")!=kind or type(track.get("bytes")) is not bytes or
        not 128<=len(track["bytes"])<=MAX_REEL_BYTES or
        track.get("sha256")!=_sha_bytes(track["bytes"]) or
        track.get("original_approved_presentation_sha256")!=source_sha or
        track.get("source_modified") is not False or
        track.get("ffmpeg_used") is not False or
        track.get("edit_rate")!=[24,1] or
        type(track.get("frame_count")) is not int or
        not 1<=track["frame_count"]<=144000 or
        track.get("dci_compliance_verified") is not False):
        raise PermissionError("Only honest approved native MXF receipts accepted")
    if kind=="picture" and track.get("profile") not in PROFILES:
        raise ValueError("Native MXF needs a verified 2K/4K source picture profile")
    value=track.get("asset_uuid")
    try:
        ident=uuid.UUID(value)
    except (TypeError,ValueError,AttributeError) as e:
        raise ValueError("MXF receipt requires exact UUIDv4") from e
    if ident.version!=4 or str(ident)!=value.lower():
        raise ValueError("Native MXF asset UUID not canonical")
    return track


def _compose_xml(picture,sound,*,title,issued):
    am_id=_u();pkl_id=_u();cpl_id=_u();reel_id=_u()
    pic_id="urn:uuid:"+picture["asset_uuid"]
    snd_id="urn:uuid:"+sound["asset_uuid"]
    if pic_id==snd_id:
        raise ValueError("Picture and sound cannot share one asset identity")
    frames=picture["frame_count"]
    if frames!=sound["frame_count"]:
        raise ValueError("No out-of-sync DCP picture/sound package")
    cpl=ET.Element("{"+NS_CPL+"}CompositionPlaylist")
    _tag(cpl,NS_CPL,"Id",cpl_id)
    _tag(cpl,NS_CPL,"AnnotationText",title)
    _tag(cpl,NS_CPL,"IssueDate",issued)
    _tag(cpl,NS_CPL,"Issuer","NVP Source-Preserving Cinema Output")
    _tag(cpl,NS_CPL,"Creator","NVP native deterministic DCP")
    _tag(cpl,NS_CPL,"ContentTitleText",title)
    _tag(cpl,NS_CPL,"ContentKind","feature")
    reels=ET.SubElement(cpl,"{"+NS_CPL+"}ReelList")
    reel=ET.SubElement(reels,"{"+NS_CPL+"}Reel")
    _tag(reel,NS_CPL,"Id",reel_id)
    assets=ET.SubElement(reel,"{"+NS_CPL+"}AssetList")
    for tag,uid in (("MainPicture",pic_id),("MainSound",snd_id)):
        node=ET.SubElement(assets,"{"+NS_CPL+"}"+tag)
        _tag(node,NS_CPL,"Id",uid)
        _tag(node,NS_CPL,"EditRate","24 1")
        _tag(node,NS_CPL,"IntrinsicDuration",frames)
        _tag(node,NS_CPL,"EntryPoint",0)
        _tag(node,NS_CPL,"Duration",frames)
        if tag=="MainPicture":
            width,height,_=PROFILES[picture["profile"]]
            _tag(node,NS_CPL,"ScreenAspectRatio",f"{width} {height}")
    cpl_bytes=_xml(cpl)
    files={
        "picture.mxf":picture["bytes"],
        "sound.mxf":sound["bytes"],
        "CPL.xml":cpl_bytes,
    }
    entries=[
        (pic_id,"picture.mxf","application/mxf"),
        (snd_id,"sound.mxf","application/mxf"),
        (cpl_id,"CPL.xml","text/xml"),
    ]
    pkl=ET.Element("{"+NS_PKL+"}PackingList")
    _tag(pkl,NS_PKL,"Id",pkl_id)
    _tag(pkl,NS_PKL,"AnnotationText",title)
    _tag(pkl,NS_PKL,"IssueDate",issued)
    _tag(pkl,NS_PKL,"Issuer","NVP Source-Preserving Cinema Output")
    _tag(pkl,NS_PKL,"Creator","NVP native deterministic DCP")
    listed=ET.SubElement(pkl,"{"+NS_PKL+"}AssetList")
    for uid,name,mime in entries:
        asset=ET.SubElement(listed,"{"+NS_PKL+"}Asset")
        _tag(asset,NS_PKL,"Id",uid)
        _tag(asset,NS_PKL,"AnnotationText",name)
        _tag(asset,NS_PKL,"Hash",_hash_pkl(files[name]))
        _tag(asset,NS_PKL,"Size",len(files[name]))
        _tag(asset,NS_PKL,"Type",mime)
        _tag(asset,NS_PKL,"OriginalFileName",name)
    files["PKL.xml"]=_xml(pkl)
    amap=ET.Element("{"+NS_AM+"}AssetMap")
    _tag(amap,NS_AM,"Id",am_id)
    _tag(amap,NS_AM,"AnnotationText",title)
    _tag(amap,NS_AM,"IssueDate",issued)
    _tag(amap,NS_AM,"Issuer","NVP Source-Preserving Cinema Output")
    _tag(amap,NS_AM,"Creator","NVP native deterministic DCP")
    _tag(amap,NS_AM,"VolumeCount",1)
    mapped=ET.SubElement(amap,"{"+NS_AM+"}AssetList")
    for uid,name,mime in [(pkl_id,"PKL.xml","text/xml"),*entries]:
        asset=ET.SubElement(mapped,"{"+NS_AM+"}Asset")
        _tag(asset,NS_AM,"Id",uid)
        if uid==pkl_id:_tag(asset,NS_AM,"PackingList","true")
        chunks=ET.SubElement(asset,"{"+NS_AM+"}ChunkList")
        chunk=ET.SubElement(chunks,"{"+NS_AM+"}Chunk")
        _tag(chunk,NS_AM,"Path",name)
        _tag(chunk,NS_AM,"VolumeIndex",1)
        _tag(chunk,NS_AM,"Offset",0)
        _tag(chunk,NS_AM,"Length",len(files[name]))
    files["ASSETMAP.xml"]=_xml(amap)
    vol=ET.Element("{"+NS_AM+"}VolumeIndex")
    _tag(vol,NS_AM,"Index",1)
    files["VOLINDEX.xml"]=_xml(vol)
    return files,{
        "assetmap_uuid":am_id,"packinglist_uuid":pkl_id,
        "composition_uuid":cpl_id,"reel_uuid":reel_id,
        "picture_uuid":pic_id,"sound_uuid":snd_id,"frames":frames}


def publish_dcp_candidate(index:FilmIndex,pid,*,take_id,take_revision,
                          take_sha256,picture,sound,output_root,
                          title,approve):
    if not isinstance(index,FilmIndex) or not callable(approve):
        raise PermissionError("Trusted native FilmIndex and creator approval")
    _id(take_id,"original approved Take")
    _sha(take_sha256)
    take=index.read_revision(pid,take_id,take_revision)
    if take["kind"]!="take" or take["document_sha256"]!=take_sha256 or (
        take["data"].get("frozen") is not True):
        raise PermissionError("Cinema output must bind one frozen original Take")
    from backend.nvp_openusd_take import OpenUSDTakeCapture
    source_verifier=OpenUSDTakeCapture(
        index,verify_creator_action=lambda *_:False)
    evidence=source_verifier.verify_take(pid,take_id)
    if (evidence["status"]!="VERIFIED_FROZEN_DATA_TAKE" or
        evidence["take_document_sha256"]!=take_sha256):
        raise PermissionError("Source OpenUSD/temporal Take verification failed")
    picture=_asset(picture,"picture",take_sha256)
    sound=_asset(sound,"sound",take_sha256)
    if type(title) is not str or not 1<=len(title)<=80 or (
        any(ord(c)<32 or c in "<>&" for c in title)):
        raise ValueError("Bounded plain-text film title required")
    root=Path(output_root)
    if root.is_symlink() or not root.is_dir() or not root.is_absolute():
        raise PermissionError("Native host must pick an existing output folder")
    root=root.resolve(strict=True)
    bound={
        "format":FORMAT,"take_id":take_id,"take_revision":take_revision,
        "original_take_sha256":take_sha256,
        "picture_sha256":picture["sha256"],
        "sound_sha256":sound["sha256"],
        "frames":picture["frame_count"],
        "title":title,
        "output_root":str(root),
        "original_modified":False,
    }
    if approve(dict(bound)) is not True:
        return {"format":FORMAT,"status":"DENIED","source_modified":False}
    if index.read_revision(pid,take_id,take_revision)[
        "document_sha256"]!=take_sha256:
        raise PermissionError("Original source changed during OS approval")
    if source_verifier.verify_take(pid,take_id)[
            "take_document_sha256"]!=take_sha256:
        raise PermissionError("Original USD content changed after native consent")
    issued=datetime.now(timezone.utc).isoformat(timespec="seconds")
    files,identifiers=_compose_xml(picture,sound,title=title,issued=issued)
    target_name="DCP_"+identifiers["composition_uuid"][9:]
    target=root/target_name
    stage=Path(tempfile.mkdtemp(prefix=".nvp-wo3-",dir=root))
    promoted=False
    try:
        for name,data in files.items():
            file=stage/name
            with file.open("xb") as writer:
                writer.write(data)
                writer.flush();os.fsync(writer.fileno())
        reviewed=inspect_dcp_structure(stage)
        if reviewed["status"]!="STRUCTURE_AND_SHA_VERIFIED":
            raise RuntimeError("Independent output package integrity rejected")
        # No existing project, user file or previous package may be
        # overwritten by NVP. Final release locks the destination parent.
        if target.exists() or target.is_symlink():
            raise FileExistsError("DCP package already exists")
        stage.rename(target)
        promoted=True
        rec=index.register_revision(
            pid,"WO3DCP_"+identifiers["composition_uuid"][9:].replace("-",""),
            "presentation",{
                "format":FORMAT,
                "title":title,"original_take_sha256":take_sha256,
                "destination_name":target_name,
                "file_sha256":{name:_sha_bytes(data) for name,data in files.items()},
                "assetmap_uuid":identifiers["assetmap_uuid"],
                "pkl_uuid":identifiers["packinglist_uuid"],
                "cpl_uuid":identifiers["composition_uuid"],
                "frame_count":identifiers["frames"],
                "structural_integrity_verified":True,
                "independent_essence_decode_verified":False,
                "production_dcp_accepted":False,
                "original_data_modified":False,
                "ffmpeg_used":False,
            },dependencies=[{
                "object_id":take_id,"revision":take_revision,"role":"source_take"}])
        return {
            "format":FORMAT,"status":"STRUCTURAL_DCP_CANDIDATE_PUBLISHED",
            "destination":str(target),
            "output_receipt_sha256":rec["document_sha256"],
            "original_take_sha256":take_sha256,
            "structural_integrity_verified":True,
            "independent_essence_decode_verified":False,
            "production_dcp_accepted":False,
            "original_source_modified":False,"ffmpeg_used":False,
        }
    finally:
        if not promoted and stage.exists():shutil.rmtree(stage)
