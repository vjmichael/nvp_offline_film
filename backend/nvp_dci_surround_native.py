"""Host-only protected cinema surround MXF qualification.

This adds a discrete delivery-derivative sound qualification route to the
existing pinned ASDCP workers, not new process or project authority. Returned
files remain private stage evidence; integration with creator feature export
and full package verification is a subsequent gate.
"""
from __future__ import annotations
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import UUID

from backend.nvp_dci_surround import (validate_layout, write_mapped_reel,
    verify_surround_reels, inspect_mxf_sound_metadata, MCA_EXPRESSION, _digest)
from backend.nvp_wo3_native_codecs import common_codec_authority, MAX_STAGE_BYTES
from backend.nvp_wo3_mxf_native import _read_info, _verify_info
from backend.nvp_wo4_pcm_stream import _protected_path, _hash_stream
from backend.nvp_wo4_resource_budget import require_stage_space


@contextmanager
def _opened(path, identity, cancel):
    if cancel() or _protected_path(path)!=identity:
        raise PermissionError("Protected PCM source changed or cancelled")
    with path.open("rb") as f:
        st=os.fstat(f.fileno())
        if (st.st_dev,st.st_ino)!=identity:
            raise PermissionError("Protected PCM replaced at open")
        yield f
    if _protected_path(path)!=identity:
        raise PermissionError("Protected PCM source replaced")


class _Window:
    def __init__(self, source, remaining, cancel):
        self.source=source;self.remaining=remaining;self.cancel=cancel
    def read(self, count):
        if self.cancel():raise InterruptedError("Creator cancelled surround processing")
        chunk=self.source.read(min(count,self.remaining))
        self.remaining-=len(chunk)
        return chunk


def qualify_native_surround(wrap,info,unwrap,*,source_path,source_sha256,
                            source_take_sha256,profile,labels,total_edit_units,
                            reels,approve):
    """Exact approved longplay source -> mapped WAV -> actual MXF -> WAV.

    Expected reel source hashes and span IDs are host supplied; no expected
    reference is derived from a decoded track. Returns only qualification
    evidence. Nothing here is approved for general release/export yet.
    """
    channels=validate_layout(profile,labels)
    labels=tuple(labels)
    _digest(source_sha256);_digest(source_take_sha256)
    if ((wrap.product,info.product,unwrap.product)!=("ASDCP-asdcp_wrap","ASDCP-asdcp_info","ASDCP-asdcp_unwrap") or
            not callable(approve)):
        raise PermissionError("Existing native host and creator callback required")
    authority=common_codec_authority(wrap,info,unwrap)
    cancel=authority.cancel
    if (type(total_edit_units) is not int or not 24<=total_edit_units<=2592000 or
            type(reels) is not list or not 1<=len(reels)<=1000):
        raise ValueError("Exact bounded reel plan required")
    schedule=[];cursor=0;ids=set()
    for reel in reels:
        if type(reel) is not dict or set(reel)!={"id","first_edit_unit","edit_units","source_pcm_sha256"}:
            raise ValueError("Exact approved source reel ledger required")
        ident,first,units,digest=(reel[k] for k in ("id","first_edit_unit","edit_units","source_pcm_sha256"))
        if (type(ident) is not str or str(UUID(ident))!=ident or UUID(ident).version!=4 or ident in ids or
                type(first) is not int or first!=cursor or type(units) is not int or not 24<=units<=7200 or
                3*units*2000*16*3+32*1024*1024>MAX_STAGE_BYTES):
            raise ValueError("Invalid contiguous bounded native reel")
        schedule.append((ident,first,units,_digest(digest)));cursor+=units;ids.add(ident)
    if cursor!=total_edit_units:raise ValueError("Reels do not cover approved source")
    source=Path(source_path); identity=_protected_path(source); source=source.resolve(strict=True)
    expected_size=total_edit_units*2000*channels*3
    if _hash_stream(source)!=(source_sha256,expected_size):
        raise PermissionError("Original longplay PCM exact size or SHA differs")
    scope={"operation":"nvp.dci.qualify_surround_pcm24.v1","source_pcm_sha256":source_sha256,
           "source_path":str(source),"source_take_sha256":source_take_sha256,
           "profile":profile,"source_labels":list(labels),"container_channels":16,
           "sample_rate":48000,"reels":[list(x) for x in schedule],"total_edit_units":total_edit_units,
           "production_audio_accepted":False}
    canonical=json.dumps(scope,sort_keys=True,separators=(",",":"))
    if cancel() or approve(json.loads(canonical)) is not True:
        raise PermissionError("Creator surround qualification not approved")
    if _protected_path(source)!=identity:raise PermissionError("Source replaced during consent")
    scope_sha=sha256(canonical.encode()).hexdigest()
    mapped_ledger=[];metadata=[];decoded_paths={}
    for ident,first,units,digest in schedule:
        stage_sha=sha256((scope_sha+ident).encode("ascii")).hexdigest()
        with wrap.stage(stage_sha) as stage:
            require_stage_space(stage,3*units*2000*16*3+32*1024*1024)
            if cancel():raise InterruptedError("Creator cancelled surround qualification")
            with _opened(source,identity,cancel) as src, (stage/"source.wav").open("xb") as target:
                st=os.fstat(target.fileno())
                if _protected_path(stage/"source.wav")!=(st.st_dev,st.st_ino):
                    raise PermissionError("Private EFS WAV replaced at open")
                src.seek(first*2000*channels*3)
                mapped=write_mapped_reel(_Window(src,units*2000*channels*3,cancel),target,
                    profile=profile,labels=labels,edit_units=units,source_sha256=digest)
                target.flush();os.fsync(target.fileno())
            args=["-L","-a",ident.replace("-",""),"-p","24","-d",str(units),
                  "-w","-m",MCA_EXPRESSION[profile],"source.wav","sound.mxf"]
            wrapper=wrap.run(args,cwd=stage,timeout=3600)
            props,inspection=_read_info(info,"sound.mxf",stage)
            _verify_info(props,ident,units)
            header=info.run(["-i","-d","-H","sound.mxf"],cwd=stage,include_stdout=True)
            audit=inspect_mxf_sound_metadata(header.pop("stdout"),profile)
            extraction=unwrap.run(["-d",str(units),"sound.mxf","audio"],cwd=stage,timeout=3600)
            audio=stage/"audio"; decoded_paths[ident]=(audio,_protected_path(audio))
            mapped_ledger.append({"id":ident,"first_edit_unit":first,"edit_units":units,
                                  "mapped_pcm_sha256":mapped["mapped_pcm_sha256"]})
            metadata.append({"id":ident,"metadata":audit,"wrapper":wrapper,"info":inspection,
                             "header":header,"unwrap":extraction,"mxf_sha256":_hash_stream(stage/"sound.mxf")[0]})
    def open_reel(ident):
        path, ident_key=decoded_paths[ident]
        return _opened(path,ident_key,cancel)
    with _opened(source,identity,cancel) as src:
        readback=verify_surround_reels(_Window(src,expected_size+1,cancel),profile=profile,labels=labels,
            source_sha256=source_sha256,total_edit_units=total_edit_units,reels=mapped_ledger,open_reel=open_reel)
    if _hash_stream(source)!=(source_sha256,expected_size):raise PermissionError("Original PCM changed during qualification")
    return {**readback,"status":"PROTECTED_NATIVE_SURROUND_REFERENCE_EXACT",
            "mxf_channel_metadata_verified":True,"native_metadata":metadata,
            "source_take_sha256":source_take_sha256,"scope_sha256":scope_sha,
            "production_audio_accepted":False,"physical_playback_accepted":False}
