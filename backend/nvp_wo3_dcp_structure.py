"""WO3-01: strict independent *structural* SMPTE DCP integrity audit.

Reads a pre-existing, explicitly selected package directory. Never runs a
codec, shell, FFmpeg, user-supplied plugin or a browser-provided path.
Verifies UUIDv4 asset identity, bounded XML, path safety, AssetMap/PKL/CPL
references, file sizes and full PKL SHA-1 hashes. SHA-1 is required by this
SMPTE PKL interchange convention, NOT a security or source-identity hash;
the receipt additionally records SHA-256 for every file.

Passing structural checks is NOT DCI-certified MXF/JPEG2000/PCM essence,
calibrated color, a valid cinema master, or projector acceptance. Production
approval must require independent native codestream/track validators.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
from pathlib import Path
import re
import uuid
import xml.etree.ElementTree as ET

FORMAT="nvp.wo3.independent_dcp_structure.v1"
MAX_XML_BYTES=8*1024*1024
MAX_ASSETS=10000
MAX_PACKAGE_BYTES=2*1024*1024*1024*1024
UUID4=re.compile(r"urn:uuid:([0-9a-fA-F-]{36})\Z")
SAFE_FILE=re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,180}\Z")
NS_AM="http://www.smpte-ra.org/schemas/429-9/2007/AM"
NS_PKL="http://www.smpte-ra.org/schemas/429-8/2007/PKL"
NS_CPL="http://www.smpte-ra.org/schemas/429-7/2006/CPL"


def _uuid(value):
    if type(value) is not str or not UUID4.fullmatch(value):
        raise ValueError("DCP asset must have canonical urn:uuid identity")
    ident=uuid.UUID(UUID4.fullmatch(value).group(1))
    if ident.version!=4 or str(ident)!=value[9:].lower():
        raise ValueError("SMPTE DCP asset identity must be UUIDv4")
    return str(ident)


def _child(node,name,namespace,required=True):
    result=node.find("{"+namespace+"}"+name)
    if result is None and required:
        raise ValueError("Missing mandatory SMPTE DCP XML field: "+name)
    return result


def _value(node,name,namespace):
    elem=_child(node,name,namespace)
    if elem.text is None or not elem.text.strip():
        raise ValueError("Empty mandatory DCP XML field: "+name)
    return elem.text.strip()


def _asset_file(folder,filename):
    if type(filename) is not str or not SAFE_FILE.fullmatch(filename) or (
        filename in (".","..") or filename.upper() in ("CON","PRN","AUX","NUL")):
        raise PermissionError("DCP asset must be a plain scoped filename")
    file=folder/filename
    if file.is_symlink() or not file.is_file():
        raise PermissionError("Missing or linked DCP package asset")
    if file.resolve(strict=True).parent!=folder:
        raise PermissionError("DCP asset escaped the approved directory")
    return file


def _xml(folder,filename,namespace,root_name):
    file=_asset_file(folder,filename)
    size=file.stat().st_size
    if not 0<size<=MAX_XML_BYTES:
        raise ValueError("SMPTE XML is missing or over its audited bound")
    data=file.read_bytes()
    if (b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper() or
        b"\x00" in data):
        raise ValueError("External entities and DTD are forbidden in DCP XML")
    try:
        node=ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError("Malformed SMPTE cinema XML") from exc
    if node.tag!="{"+namespace+"}"+root_name:
        raise ValueError("Wrong SMPTE DCP profile or root namespace")
    return node


def _hash_file(file):
    sha1=hashlib.sha1()
    sha256=hashlib.sha256()
    total=0
    with file.open("rb") as stream:
        while True:
            chunk=stream.read(1024*1024)
            if not chunk:break
            total+=len(chunk)
            if total>MAX_PACKAGE_BYTES:
                raise ValueError("Unbounded independent DCP package asset")
            sha1.update(chunk);sha256.update(chunk)
    return total,base64.b64encode(sha1.digest()).decode("ascii"),sha256.hexdigest()


def inspect_dcp_structure(folder):
    root=Path(folder)
    if root.is_symlink() or not root.is_dir():
        raise PermissionError("A local trusted directory must be selected")
    root=root.resolve(strict=True)
    assetmap=_xml(root,"ASSETMAP.xml",NS_AM,"AssetMap")
    _uuid(_value(assetmap,"Id",NS_AM))
    if _value(assetmap,"VolumeCount",NS_AM)!="1":
        raise ValueError("Only complete single-volume DCP packages accepted")
    entries=_child(assetmap,"AssetList",NS_AM).findall(
        "{"+NS_AM+"}Asset")
    if not 3<=len(entries)<=MAX_ASSETS:
        raise ValueError("Incomplete or oversized DCP asset map")
    locations={}
    pkls=[]
    for entry in entries:
        ident=_uuid(_value(entry,"Id",NS_AM))
        if ident in locations:
            raise ValueError("Duplicate DCP UUID in AssetMap")
        chunks=_child(entry,"ChunkList",NS_AM).findall(
            "{"+NS_AM+"}Chunk")
        if len(chunks)!=1:
            raise ValueError("Missing or multi-volume DCP asset chunk")
        chunk=chunks[0]
        name=_value(chunk,"Path",NS_AM)
        if (_value(chunk,"VolumeIndex",NS_AM)!="1" or
            _value(chunk,"Offset",NS_AM)!="0"):
            raise ValueError("Nonzero offset/multi-volume DCP not supported")
        locations[ident]=name
        if (_child(entry,"PackingList",NS_AM,False) is not None and
            _value(entry,"PackingList",NS_AM).lower()=="true"):
            pkls.append(ident)
    if len(set(locations.values()))!=len(locations):
        raise ValueError("DCP AssetMap aliases different assets to one file")
    if len(pkls)!=1:
        raise ValueError("One exact SMPTE packing list required")
    pkl_file=locations[pkls[0]]
    pkl=_xml(root,pkl_file,NS_PKL,"PackingList")
    if _uuid(_value(pkl,"Id",NS_PKL))!=pkls[0]:
        raise ValueError("AssetMap and PKL identities disagree")
    declared=_child(pkl,"AssetList",NS_PKL).findall(
        "{"+NS_PKL+"}Asset")
    if not 2<=len(declared)<=MAX_ASSETS:
        raise ValueError("Packing list must contain CPL and MXF tracks")
    packed={}
    seen_paths=set()
    for entry in declared:
        ident=_uuid(_value(entry,"Id",NS_PKL))
        if ident==pkls[0] or ident in packed or ident not in locations:
            raise ValueError("PKL duplicate/self-reference or unmapped asset")
        expected_bytes=_value(entry,"Size",NS_PKL)
        if not expected_bytes.isdecimal():
            raise ValueError("Invalid SMPTE PKL byte count")
        expected=int(expected_bytes)
        if not 0<expected<=MAX_PACKAGE_BYTES:
            raise ValueError("Unsafe SMPTE PKL asset size")
        expected_hash=_value(entry,"Hash",NS_PKL)
        try:
            decoded=base64.b64decode(expected_hash,validate=True)
        except (binascii.Error,ValueError) as exc:
            raise ValueError("Malformed SMPTE PKL SHA-1") from exc
        if len(decoded)!=20:
            raise ValueError("SMPTE PKL must contain 20-byte SHA-1 digest")
        mime=_value(entry,"Type",NS_PKL)
        if mime not in ("application/mxf","text/xml"):
            raise ValueError("Unsupported SMPTE DCP package asset MIME")
        filename=locations[ident]
        if filename in seen_paths:
            raise ValueError("DCP output filename reused")
        seen_paths.add(filename)
        file=_asset_file(root,filename)
        actual_size,actual_hash,actual_sha256=_hash_file(file)
        if (actual_size!=expected or
            actual_hash!=expected_hash):
            raise RuntimeError("Independent DCP asset size or digest mismatch")
        packed[ident]={
            "filename":filename,"mime":mime,
            "bytes":actual_size,"sha256":actual_sha256,
            "pkl_sha1_verified":True,
        }
    if set(locations)!=(set(packed)|set(pkls)):
        raise ValueError("AssetMap and PackingList do not enumerate same files")
    cpls=[(uid,p) for uid,p in packed.items() if p["mime"]=="text/xml"]
    if len(cpls)!=1:
        raise ValueError("One independently hash-verified SMPTE CPL required")
    cpl_id,cpl_record=cpls[0]
    cpl=_xml(root,cpl_record["filename"],NS_CPL,"CompositionPlaylist")
    if _uuid(_value(cpl,"Id",NS_CPL))!=cpl_id:
        raise ValueError("Composition Playlist UUID differs from packing list")
    tracks=[]
    reels=_child(cpl,"ReelList",NS_CPL).findall("{"+NS_CPL+"}Reel")
    if not reels or len(reels)>1000:
        raise ValueError("DCP needs bounded real reels")
    for reel in reels:
        assets=_child(reel,"AssetList",NS_CPL)
        picture=_child(assets,"MainPicture",NS_CPL)
        sound=_child(assets,"MainSound",NS_CPL)
        for kind,node in (("picture",picture),("sound",sound)):
            uid=_uuid(_value(node,"Id",NS_CPL))
            if uid not in packed or packed[uid]["mime"]!="application/mxf":
                raise ValueError("CPL references unverified or non-MXF track")
            tracks.append({"kind":kind,"asset_id":uid,
                           "filename":packed[uid]["filename"]})
    if not tracks or not any(x["kind"]=="picture" for x in tracks):
        raise ValueError("Missing real picture track reference")
    return {
        "format":FORMAT,"status":"STRUCTURE_AND_SHA_VERIFIED",
        "asset_count":len(packed),
        "reel_count":len(reels),"tracks":tracks,
        "assets":packed,
        "assetmap_filename":"ASSETMAP.xml",
        "pkl_uuid":pkls[0],"cpl_uuid":cpl_id,
        "source_original_files_modified":False,
        "metadata_and_asset_hashes_verified":True,
        "mxf_essence_verified":False,
        "jpeg2000_xyz12_verified":False,
        "pcm24_track_verified":False,
        "independent_dci_compliance_verified":False,
        "production_dcp_accepted":False,
        "ffmpeg_used":False,
        "outstanding":[
            "independent_MXF_KLV_essence_and_track_validator",
            "independent_JPEG2000_12bit_XYZ_DCI_profile_decoder",
            "native_24bit_PCM_48kHz_sound_track_validator",
            "schema_check_SMPTE_429_7_8_9",
            "independent_DCP_validator_and_projector_ingest"],
    }
