"""G09-F streamable, genuinely portable, source-verified NVP film package.

The delivered .nvpfilm is ZIP64/STORED containing ONLY:
  package.json           metadata and manifest SHA
  manifest.json          the original completed G09-E global film index
  reels/reel-00000.avi   the exact independently checked AVI reel bytes
  ...
No code, executable, external reference, network address, untrusted plugin,
fictional DCP file or physical OS path is embedded.

A SHA256 proves bytes are unchanged relative to the manifest, NOT who
authored the film. No cryptographic identity/signature is claimed.
Pack/unpack copies in bounded 1 MiB pieces; no whole-film in-memory blobs.
The protected G03 source film is never used by this ordinary export path.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from datetime import datetime, timezone
from zipfile import ZipFile,ZipInfo,ZIP_STORED,BadZipFile
import json
import os
import re
import shutil
import uuid

FORMAT="nvp.g09f.portable_film.v1"
EXTENSION=".nvpfilm"
MAX_REELS=1080
MAX_REEL_BYTES=80*1024*1024
MAX_CONTENT_BYTES=32*1024**3
MAX_PACKAGE_BYTES=MAX_CONTENT_BYTES+64*1024**2
MAX_MANIFEST_BYTES=2*1024*1024
MAX_METADATA_BYTES=16384
BUFFER=1024*1024
SHA=re.compile(r"[a-f0-9]{64}\Z")
NAME=re.compile(r"reel-[0-9]{5}\.avi\Z")
TIMESTAMP=(1980,1,1,0,0,0)

def _canonical(data):
    return json.dumps(data,sort_keys=True,ensure_ascii=False,
        separators=(",",":"),allow_nan=False).encode("utf8")

def _verified_manifest(manifest):
    from backend.nvp_g09e_chunk import FRAMES_PER_CHUNK,MAX_FRAMES
    if (type(manifest) is not dict or
        manifest.get("format")!="nvp.g09e.native_reels.v1" or
        manifest.get("not_a_single_gapless_media_file") is not True or
        manifest.get("not_a_professional_master_or_DCP") is not True or
        manifest.get("original_frozen_takes_preserved") is not True):
        raise ValueError("Only actually verified native film reels are distributable")
    n=manifest.get("reel_count")
    total=manifest.get("total_frames")
    if (type(n) is not int or type(total) is not int or
        not 1<=n<=MAX_REELS or not 1<=total<=MAX_FRAMES or
        n!=(total+FRAMES_PER_CHUNK-1)//FRAMES_PER_CHUNK):
        raise ValueError("The film reel count is not complete")
    if (manifest.get("frame_rate")!=24 or
        manifest.get("sample_rate")!=48000 or
        manifest.get("channels")!=2 or
        manifest.get("film_time_ticks_per_second")!=7056000000):
        raise ValueError("The portable film uses an unsupported sound/picture clock")
    refs=manifest.get("reels")
    if type(refs) is not list or len(refs)!=n:
        raise ValueError("A portable film is missing independently checked reels")
    if (type(manifest.get("source_sha256")) is not str or
        not SHA.fullmatch(manifest["source_sha256"])):
        raise ValueError("A film lost its original-source identity")
    sizes=0
    for i,item in enumerate(refs):
        if type(item) is not dict:
            raise ValueError("An independently checked reel is invalid")
        start=i*FRAMES_PER_CHUNK;end=min(total,start+FRAMES_PER_CHUNK)
        name=f"reel-{i:05d}.avi"
        if (item.get("index")!=i or item.get("path")!=name or
            item.get("start_frame")!=start or item.get("end_frame")!=end or
            item.get("start_tick")!=start*294000000 or
            item.get("end_tick")!=end*294000000 or
            item.get("start_sample")!=start*2000 or
            item.get("end_sample")!=end*2000 or
            item.get("independent_reel_verified") is not True or
            type(item.get("sha256")) is not str or
            not SHA.fullmatch(item["sha256"]) or
            type(item.get("bytes")) is not int or
            not 512<=item["bytes"]<=MAX_REEL_BYTES):
            raise ValueError("The portable film contains an incomplete or mismatched reel")
        sizes+=item["bytes"]
        if sizes>MAX_CONTENT_BYTES:
            raise ValueError("The complete film exceeds its portable format budget")
    return refs

def _safe_folder(folder):
    folder=Path(folder)
    if folder.is_symlink() or not folder.is_dir() or folder.resolve()!=folder:
        raise RuntimeError("The completed movie storage path is not trustworthy")
    return folder

def _hash_file(path,expected=None):
    source=Path(path)
    if source.is_symlink() or not source.is_file():
        raise RuntimeError("A completed reel was replaced by an unsafe source")
    h=sha256();size=0
    with open(source,"rb",buffering=BUFFER) as stream:
        while True:
            chunk=stream.read(BUFFER)
            if not chunk:break
            h.update(chunk);size+=len(chunk)
            if size>MAX_REEL_BYTES:raise ValueError("One film reel exceeds its budget")
    digest=h.hexdigest()
    if expected is not None and digest!=expected:
        raise RuntimeError("A completed reel differs from its independently verified film index")
    return digest,size

def _zip_entry(z,name,raw):
    info=ZipInfo(name,date_time=TIMESTAMP)
    info.compress_type=ZIP_STORED
    info.external_attr=0o100644<<16
    z.writestr(info,raw)

def _meta(manifest,manifest_raw):
    return {"format":FORMAT,
        "film_manifest_sha256":sha256(manifest_raw).hexdigest(),
        "original_source_sha256":manifest["source_sha256"],
        "total_frames":manifest["total_frames"],
        "reel_count":manifest["reel_count"],
        "profile":"640x360_24fps_sdr_mjpeg_pcm16_stereo_48000",
        "source_films_modified":False,
        "protected_source_exported":False,
        "independent_reel_verification_reused":True,
        "signature_or_author_identity_verified":False,
        "single_gapless_stream_claimed":False,
        "smpte_dcp_or_hdr_master_claimed":False}

def build_portable(source_dir,manifest,destination,*,cancel=None,progress=None):
    """Write and verify an immutable destination with original-source receipts.

    Exclusive temp path, fsync, publish via no-replace hardlink and verify
    the built ZIP with a separately reopened archive BEFORE publication.
    """
    src=_safe_folder(source_dir)
    dest=Path(destination)
    if dest.parent!=src or dest.name!="film.nvpfilm":
        raise ValueError("Portable deliverables must stay inside the owner's completed film job")
    if dest.exists() or dest.is_symlink():
        raise FileExistsError("The portable film was already created")
    refs=_verified_manifest(manifest)
    manifest_raw=_canonical(manifest)
    if len(manifest_raw)>MAX_MANIFEST_BYTES:
        raise ValueError("The completed film manifest exceeds its size budget")
    metadata=_canonical(_meta(manifest,manifest_raw))
    temp=src/(".film-"+uuid.uuid4().hex+".partial")
    try:
        with ZipFile(temp,"x",compression=ZIP_STORED,allowZip64=True) as z:
            _zip_entry(z,"package.json",metadata)
            _zip_entry(z,"manifest.json",manifest_raw)
            for i,entry in enumerate(refs):
                if cancel and cancel():
                    raise InterruptedError("Portable film packaging cancelled")
                original=src/entry["path"]
                name="reels/"+entry["path"]
                if _hash_file(original,entry["sha256"])[1]!=entry["bytes"]:
                    raise RuntimeError("Reel bytes changed before distribution")
                info=ZipInfo(name,date_time=TIMESTAMP)
                info.compress_type=ZIP_STORED
                info.external_attr=0o100644<<16
                with open(original,"rb",buffering=BUFFER) as reader:
                    with z.open(info,"w",force_zip64=True) as target:
                        while True:
                            chunk=reader.read(BUFFER)
                            if not chunk:break
                            target.write(chunk)
                            if cancel and cancel():
                                raise InterruptedError("Portable film packaging cancelled")
                if progress:progress(i+1,len(refs))
        if temp.stat().st_size>MAX_PACKAGE_BYTES:
            raise ValueError("The portable package exceeds its source-film quota")
        verify_portable(temp,validate_reels=True,cancel=cancel)
        if dest.exists() or dest.is_symlink():
            raise FileExistsError("A different portable film was already published")
        os.link(temp,dest,follow_symlinks=False)
        if os.name!="nt":
            fd=os.open(src,os.O_RDONLY)
            try:os.fsync(fd)
            finally:os.close(fd)
        result={"format":FORMAT,"package_sha256":_hash_package(dest),
            "package_bytes":dest.stat().st_size,
            "reels":len(refs),"original_source_sha256":manifest["source_sha256"],
            "verified":True,"original_filmed_media_unmodified":True}
        return result
    finally:
        if temp.exists() and not temp.is_symlink():temp.unlink()

def _hash_package(path):
    h=sha256()
    with open(path,"rb",buffering=BUFFER) as r:
        for part in iter(lambda:r.read(BUFFER),b""):h.update(part)
    return h.hexdigest()

def verify_portable(path,*,validate_reels=True,cancel=None):
    """Open only a literal fixed file structure; refuse ZIP tricks and bombs."""
    source=Path(path)
    if source.is_symlink() or not source.is_file() or not (
            1024<=source.stat().st_size<=MAX_PACKAGE_BYTES):
        raise ValueError("The portable original film is unsafe or too large")
    with ZipFile(source,"r",allowZip64=True) as z:
        members=z.infolist()
        if not 3<=len(members)<=MAX_REELS+2:
            raise ValueError("An unexpected number of film package files was found")
        names=[x.filename for x in members]
        if names[:2]!=["package.json","manifest.json"] or (
                len(names)!=len(set(names))):
            raise ValueError("Portable film entries or ordering were changed")
        for item in members:
            if (item.compress_type!=ZIP_STORED or item.flag_bits&1 or
                item.is_dir() or item.filename.startswith(("/","\\")) or
                "\\" in item.filename or ".." in item.filename or
                item.file_size>MAX_REEL_BYTES and item.filename.startswith("reels/")):
                raise ValueError("The portable package includes an untrusted file")
            if item.filename=="package.json" and item.file_size>MAX_METADATA_BYTES:
                raise ValueError("Portable film format metadata is unbounded")
            if item.filename=="manifest.json" and item.file_size>MAX_MANIFEST_BYTES:
                raise ValueError("Portable film manifest is unbounded")
        data=json.loads(z.read("package.json"))
        manifest_raw=z.read("manifest.json")
        manifest=json.loads(manifest_raw)
        refs=_verified_manifest(manifest)
        if (data!=_meta(manifest,_canonical(manifest)) or
            manifest_raw!=_canonical(manifest) or
            len(refs)!=len(members)-2 or
            names[2:]!=["reels/"+ref["path"] for ref in refs]):
            raise ValueError("The film package does not match its verified source index")
        if validate_reels:
            for info,ref in zip(members[2:],refs):
                if info.file_size!=ref["bytes"]:
                    raise ValueError("An archived film reel has different bytes")
                digest=sha256();count=0
                with z.open(info,"r") as stream:
                    while True:
                        piece=stream.read(BUFFER)
                        if not piece:break
                        digest.update(piece);count+=len(piece)
                        if count>MAX_REEL_BYTES:
                            raise ValueError("Reel archive is unbounded")
                        if cancel and cancel():raise InterruptedError()
                if count!=ref["bytes"] or digest.hexdigest()!=ref["sha256"]:
                    raise RuntimeError("A portable reel does not match its original film source")
        return {"format":FORMAT,"manifest":manifest,"metadata":data,
                "package_sha256":_hash_package(source),
                "package_bytes":source.stat().st_size,
                "reel_count":len(refs),"verified_all_reels":validate_reels,
                "authentic_author_signature_checked":False}

def import_portable(path,library_folder,*,cancel=None,progress=None):
    """Verify and store a movie through NVP with NO arbitrary file extraction."""
    package=Path(path)
    dest=Path(library_folder)
    if dest.exists() or dest.is_symlink():
        raise FileExistsError("An existing film-library entry must not be overwritten")
    if dest.parent.is_symlink() or not dest.parent.is_dir():
        raise RuntimeError("The film-library root is not trustworthy")
    verified=verify_portable(package,validate_reels=False)
    manifest=verified["manifest"]
    entries=_verified_manifest(manifest)
    stage=dest.parent/("."+dest.name+"-"+uuid.uuid4().hex+".staging")
    stage.mkdir(mode=0o700)
    try:
        with ZipFile(package,"r") as z:
            for i,ref in enumerate(entries):
                name="reels/"+ref["path"]
                out=stage/ref["path"]
                digest=sha256();size=0
                with z.open(name,"r") as reader,open(out,"xb") as writer:
                    while True:
                        part=reader.read(BUFFER)
                        if not part:break
                        size+=len(part)
                        if size>MAX_REEL_BYTES:raise ValueError("An imported reel is unbounded")
                        writer.write(part);digest.update(part)
                        if cancel and cancel():raise InterruptedError()
                    writer.flush();os.fsync(writer.fileno())
                if size!=ref["bytes"] or digest.hexdigest()!=ref["sha256"]:
                    raise RuntimeError("The portable picture/sound reel was modified")
                if progress:progress(i+1,len(entries))
        raw=_canonical(manifest)
        marker=stage/"manifest.json"
        with open(marker,"xb") as f:
            f.write(raw);f.flush();os.fsync(f.fileno())
        stage.rename(dest)
        return {"source_sha256":manifest["source_sha256"],
            "package_sha256":verified["package_sha256"],
            "reels_imported":len(entries),"manifest_sha256":sha256(raw).hexdigest(),
            "ready":True,"original_author_authenticity_verified":False}
    finally:
        if stage.exists() and not stage.is_symlink():
            shutil.rmtree(stage)
