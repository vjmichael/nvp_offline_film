"""DA-02D: durable, fail-closed original microphone interruption evidence.

The original PCM spool is a RECOVERABLE UNAPPROVED source after host crash,
never an automatically frozen Take. A new host may inspect the local journal
and ask the creator for a separate decision. No derived picture, background
repair process, FFmpeg, arbitrary path from JS, or automatic salvage.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import secrets

FORMAT="nvp.data_av.capture_recovery.v1"
MAX_CATALOG=128
MAX_NOTE_BYTES=8192
ID=re.compile(r"nvp-live-original-[A-Za-z0-9_-]{8,80}\Z")
GOOD_PHASES=frozenset((
    "CAPTURING","DRAINED","FROZEN","FAILED_UNAPPROVED",
    "CANCELLED","INTERRUPTED_UNAPPROVED","SALVAGED_SOURCE_ONLY"))
SAFE_FIELDS=frozenset((
    "format","project_id","take_id","source_id","scene_sha256",
    "camera_timeline_sha256","start_sample","sample_rate","phase",
    "durable_sample_count","source_pcm_sha256","original_take_sha256",
    "creator_approved","salvaged_source_id","salvaged_source_sha256"))


def _atomic_json(path,data):
    raw=json.dumps(data,sort_keys=True,separators=(",",":"),
                   allow_nan=False).encode("utf8")
    if len(raw)>MAX_NOTE_BYTES:
        raise ValueError("Original capture journal receipt exceeds bound")
    target=path.parent/(".receipt-"+secrets.token_hex(16)+".tmp")
    fd=os.open(str(target),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    try:
        with os.fdopen(fd,"wb") as out:
            out.write(raw);out.flush();os.fsync(out.fileno())
        os.replace(target,path)
        if os.name=="posix":
            fd_dir=os.open(str(path.parent),os.O_RDONLY)
            try:os.fsync(fd_dir)
            finally:os.close(fd_dir)
    finally:
        if target.exists():target.unlink()


class OriginalCaptureJournal:
    def __init__(self,root):
        path=Path(root)
        if path.is_symlink():
            raise PermissionError("Native capture recovery root must not be symlinked")
        path.mkdir(mode=0o700,parents=True,exist_ok=True)
        if not path.is_dir():
            raise PermissionError("Native capture recovery root is not a directory")
        self.root=path.resolve(strict=True)

    def begin(self,directory,scope):
        directory=Path(directory).resolve(strict=True)
        if (directory.parent!=self.root or
            not ID.fullmatch(directory.name)):
            raise PermissionError("Only trusted original capture spool is journalled")
        if not isinstance(scope,dict):
            raise TypeError("Native capture scope required")
        data={
            "format":FORMAT,"project_id":scope["project_id"],
            "take_id":scope["take_id"],"source_id":scope["source_id"],
            "scene_sha256":scope["scene_sha256"],
            "camera_timeline_sha256":scope["camera_timeline_sha256"],
            "start_sample":0,"sample_rate":scope["sample_rate"],
            "phase":"CAPTURING","durable_sample_count":0,
            "source_pcm_sha256":None,"original_take_sha256":None,
            "creator_approved":False,
            "salvaged_source_id":None,"salvaged_source_sha256":None}
        _atomic_json(directory/"receipt.json",data)
        return data

    def update(self,directory,*,phase,recorded_samples=None,
               pcm_sha256=None,take_sha256=None):
        if phase not in GOOD_PHASES:
            raise ValueError("Invalid recovery phase")
        directory=Path(directory).resolve(strict=True)
        if directory.parent!=self.root or not ID.fullmatch(directory.name):
            raise PermissionError("Unrecognized original capture spool")
        receipt=directory/"receipt.json"
        data=self._read(receipt)
        if data["phase"] in ("FROZEN","CANCELLED"):
            raise RuntimeError("Completed original recording may not be rewritten")
        if (data["phase"]=="CAPTURING" and
            phase not in ("DRAINED","FAILED_UNAPPROVED","CANCELLED",
                          "INTERRUPTED_UNAPPROVED") or
            data["phase"]=="DRAINED" and
            phase not in ("FROZEN","FAILED_UNAPPROVED","CANCELLED",
                          "SALVAGED_SOURCE_ONLY") or
            data["phase"]=="FAILED_UNAPPROVED" and
            phase not in ("CANCELLED","SALVAGED_SOURCE_ONLY") or
            data["phase"] in ("INTERRUPTED_UNAPPROVED","SALVAGED_SOURCE_ONLY")
            and phase!="CANCELLED"):
            raise RuntimeError("Invalid original capture recovery transition")
        if recorded_samples is not None:
            if type(recorded_samples) is not int or recorded_samples<0:
                raise ValueError("Invalid durable original PCM sample count")
            data["durable_sample_count"]=recorded_samples
        if pcm_sha256 is not None:
            if (type(pcm_sha256) is not str or
                not re.fullmatch("[0-9a-f]{64}",pcm_sha256)):
                raise ValueError("Invalid durable PCM source checksum")
            data["source_pcm_sha256"]=pcm_sha256
        if take_sha256 is not None:
            if (type(take_sha256) is not str or
                not re.fullmatch("[0-9a-f]{64}",take_sha256) or
                phase!="FROZEN"):
                raise ValueError("Only confirmed frozen Take may seal source")
            data["original_take_sha256"]=take_sha256
            data["creator_approved"]=True
        data["phase"]=phase
        _atomic_json(receipt,data)
        return data

    @staticmethod
    def _read(path):
        if path.is_symlink() or path.stat().st_size>MAX_NOTE_BYTES:
            raise RuntimeError("Untrusted original source journal")
        data=json.loads(path.read_text("utf8"))
        if (type(data) is not dict or set(data)!=SAFE_FIELDS or
            data["format"]!=FORMAT or data["phase"] not in GOOD_PHASES):
            raise RuntimeError("Native recovery journal source identity corrupted")
        return data

    def salvage_original_mono_source(
            self,index,project_id,capture_reference,new_source_id,
            *,native_creator_approval):
        """Explicit source recovery only; never author a Take or soundtrack.

        Only a stopped writer with a fsynced full original mono PCM checksum
        can be salvaged. Interrupted unverified or dual-channel spools stay
        quarantined for separate host-level forensic reconciliation.
        """
        from backend.nvp_data_av_source import RecordedSoundSources
        from backend.nvp_film_index import FilmIndex,_id,_require_pid
        if not isinstance(index,FilmIndex) or not callable(native_creator_approval):
            raise TypeError("Source recovery needs original index and native approval")
        _require_pid(project_id);_id(new_source_id,"recovered source identity")
        if (type(capture_reference) is not str or
            not ID.fullmatch(capture_reference)):
            raise PermissionError("Unrecognized native PCM recovery session")
        directory=self.root/capture_reference
        if directory.is_symlink() or not directory.is_dir() or (
                directory.resolve(strict=True).parent!=self.root):
            raise PermissionError("Recovered source is not in trusted native custody")
        data=self._read(directory/"receipt.json")
        if (data["project_id"]!=project_id or
            data["phase"] not in ("DRAINED","FAILED_UNAPPROVED") or
            not data["source_pcm_sha256"] or
            data["durable_sample_count"]<1 or
            new_source_id in (data["source_id"],data["take_id"])):
            raise PermissionError("No independently sealed original mono source")
        pcm=directory/"recording.pcm"
        if (not pcm.is_file() or pcm.is_symlink() or
            pcm.stat().st_size!=data["durable_sample_count"]*2 or
            pcm.stat().st_size>600*48000*2):
            raise RuntimeError("Recovered original PCM file is incomplete or changed")
        digest=sha256()
        with pcm.open("rb") as source:
            while chunk:=source.read(1024*1024):
                digest.update(chunk)
        if digest.hexdigest()!=data["source_pcm_sha256"]:
            raise RuntimeError("Original microphone recovery checksum mismatch")
        scope={"operation":"nvp.original_sound.salvage_unapproved_pcm.v1",
               "project_id":project_id,"capture_reference":capture_reference,
               "new_source_id":new_source_id,
               "pcm_sha256":data["source_pcm_sha256"],
               "recorded_samples":data["durable_sample_count"],
               "output_is_original_signal":True,
               "creates_frozen_digital_take":False}
        if native_creator_approval(scope) is not True:
            raise PermissionError("Creator declined recovery of original audio")
        def chunks():
            with pcm.open("rb") as reader:
                while part:=reader.read(1024*1024):
                    if len(part)%2:raise RuntimeError("Corrupt recovered original PCM")
                    yield part
        record=RecordedSoundSources(index).publish(
            project_id,new_source_id,chunks(),expected_revision=0)
        # A concurrent unexpected mutation must not create an approved Take.
        actual=sha256()
        with pcm.open("rb") as reader:
            while part:=reader.read(1024*1024):actual.update(part)
        if actual.hexdigest()!=data["source_pcm_sha256"]:
            raise RuntimeError("Source spool changed during recovery; Take not approved")
        update={
            **data,"phase":"SALVAGED_SOURCE_ONLY",
            "salvaged_source_id":new_source_id,
            "salvaged_source_sha256":record["document_sha256"]}
        _atomic_json(directory/"receipt.json",update)
        return {"format":FORMAT,"status":"RECOVERED_UNATTACHED_ORIGINAL_MONO",
                "source_id":new_source_id,
                "source_document_sha256":record["document_sha256"],
                "recorded_samples":data["durable_sample_count"],
                "original_source_sha256":data["source_pcm_sha256"],
                "created_frozen_take":False,"original_source_modified":False}

    def catalog(self,project_id):
        """Read-only startup reconciliation; no old PCM is deleted/frozen."""
        report=[]
        for directory in sorted(self.root.iterdir()):
            if len(report)>=MAX_CATALOG:
                break
            if (directory.is_symlink() or not directory.is_dir() or
                    not ID.fullmatch(directory.name)):
                continue
            receipt=directory/"receipt.json"
            if not receipt.is_file() or receipt.is_symlink():
                continue
            try:
                row=self._read(receipt)
                if row["project_id"]!=project_id or row["phase"] in (
                        "FROZEN","CANCELLED","SALVAGED_SOURCE_ONLY"):
                    continue
                # A writer could still belong to another running native
                # application. We never imply this spool is safe to delete.
                report.append({
                    "capture_reference":directory.name,
                    "take_id":row["take_id"],
                    "phase":row["phase"],
                    "durable_sample_count":row["durable_sample_count"],
                    "recoverable_sealed_mono":(
                        row["phase"] in ("DRAINED","FAILED_UNAPPROVED")
                        and row["source_pcm_sha256"] is not None
                        and row["durable_sample_count"]>0
                        and (directory/"recording.pcm").is_file()
                        and not (directory/"recording.pcm").is_symlink()),
                    "source_verified_for_freeze":False,
                    "take_approved":False,
                    "requires_native_owner_reconciliation":True,
                })
            except (OSError,ValueError,RuntimeError,KeyError):
                # Malformed entries must not be treated as safe recordings.
                report.append({"capture_reference":directory.name,
                               "phase":"CORRUPT_UNAPPROVED",
                               "take_approved":False,
                               "requires_native_owner_reconciliation":True})
        return {"format":FORMAT,"status":"READ_ONLY_RECOVERY_EVIDENCE",
                "items":report,"auto_freeze":False,"auto_delete":False}
