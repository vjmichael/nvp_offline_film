"""Batch 3 durable no-FFmpeg derived picture writer journal.

An original Take remains in FilmIndex. Only explicitly approved native
picture/PCM DERIVATIVES enter this same-filesystem work directory. Every
finished image has a SHA-verified, fsynced JSONL receipt. Restart recovery
requires the same source, grade, OCIO config, cadence and OS destination;
there is no generated source-frame authority. Never overwrite publication.

Cross-process exclusive OS file lock (flock / msvcrt.locking) is released
when a host dies; no PID-based guess releases a working producer's lock.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import sys

FORMAT="nvp.native_color.output_journal.v1"
SAFE_ID=re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,60}\Z")
NAME=re.compile(r"[0-9]{7}\.(?:png|exr)\Z")
MAX_FRAMES=7200
MAX_ROW_BYTES=4096


def _canonical(data):
    return json.dumps(data,sort_keys=True,ensure_ascii=True,
                      separators=(",",":"),allow_nan=False).encode("ascii")


def _file_sha256(path):
    digest=hashlib.sha256()
    with Path(path).open("rb") as file:
        while block:=file.read(1024*1024):
            digest.update(block)
    return digest.hexdigest()


def _atomic_document(path,data):
    tmp=path.parent/(path.name+".new")
    if tmp.is_symlink() or tmp.exists():
        raise RuntimeError("Untrusted ongoing derived color journal metadata")
    with tmp.open("xb") as out:
        out.write(_canonical(data))
        out.flush();os.fsync(out.fileno())
    os.replace(tmp,path)


class NativeColorOutputJournal:
    def __init__(self,output_parent,presentation_id,scope,*,picture_ext):
        parent=Path(output_parent)
        if (parent.is_symlink() or not parent.is_dir() or
            type(presentation_id) is not str or
            not SAFE_ID.fullmatch(presentation_id)):
            raise PermissionError("No trusted native output/workspace identity")
        if picture_ext not in (".png",".exr"):
            raise ValueError("Unapproved native derivative image format")
        self.parent=parent.resolve(strict=True)
        self.scope_sha256=hashlib.sha256(_canonical(scope)).hexdigest()
        self.ext=picture_ext
        self.staged=self.parent/(".nvp-color-work-"+presentation_id)
        self.target=self.parent/("NVP2D_"+presentation_id)
        if self.target.exists() or self.target.is_symlink():
            raise FileExistsError("Color package is already published")
        if self.staged.is_symlink():
            raise PermissionError("No symlinked native color recovery directory")
        fresh=not self.staged.exists()
        if fresh:
            self.staged.mkdir(mode=0o700)
        if not self.staged.is_dir():
            raise PermissionError("Native scene-linear recovery workspace unavailable")
        self.lock=self.staged/"owner.lock"
        self.fd=None
        self.records=[]
        try:
            self._lock()
            self.pictures=self.staged/"pictures"
            if fresh:
                self.pictures.mkdir(mode=0o700)
                _atomic_document(self.staged/"scope.json",{
                    "format":FORMAT,"scope_sha256":self.scope_sha256,
                    "color_pipeline":scope["color_pipeline"],
                    "image_extension":picture_ext,
                    "original_source_modified":False,
                })
            self._recover()
        except BaseException:
            self.release()
            raise

    def _lock(self):
        self.fd=self.lock.open("a+b")
        self.fd.seek(0)
        self.fd.write(b" ")
        self.fd.flush();os.fsync(self.fd.fileno())
        if os.name=="nt":
            import msvcrt
            self.fd.seek(0)
            try:msvcrt.locking(self.fd.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as exc:
                raise RuntimeError("Another native color producer is active") from exc
        else:
            import fcntl
            try:fcntl.flock(self.fd.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError as exc:
                raise RuntimeError("Another native color producer is active") from exc

    def _recover(self):
        meta=self.staged/"scope.json"
        if (meta.is_symlink() or not meta.is_file() or
            meta.stat().st_size>4096 or
            self.pictures.is_symlink() or not self.pictures.is_dir()):
            raise RuntimeError("Native color source-authority journal is corrupted")
        data=json.loads(meta.read_text("utf8"))
        if (set(data)!={"format","scope_sha256","color_pipeline",
                        "image_extension","original_source_modified"} or
            data["format"]!=FORMAT or
            data["scope_sha256"]!=self.scope_sha256 or
            data["image_extension"]!=self.ext or
            data["original_source_modified"] is not False):
            raise RuntimeError("Refusing color resume with different Take/grade/config scope")
        progress=self.staged/"progress.jsonl"
        if progress.is_symlink() or (progress.exists() and
            progress.stat().st_size>MAX_FRAMES*MAX_ROW_BYTES):
            raise RuntimeError("Native color source receipt log tampered")
        if progress.exists():
            with progress.open("rb") as file:
                for line in file:
                    if not line.endswith(b"\n") or len(line)>MAX_ROW_BYTES:
                        raise RuntimeError("Interrupted native picture SHA receipt")
                    row=json.loads(line)
                    self._verify_row(row,len(self.records))
                    self.records.append(row)
            if len(self.records)>MAX_FRAMES:
                raise RuntimeError("Unbounded native color recovery log")
        owned={row["png_file"] if "png_file" in row else row["exr_file"]
               for row in self.records}
        for item in self.pictures.iterdir():
            if (item.is_symlink() or not item.is_file() or
                not NAME.fullmatch(item.name) or
                item.suffix!=self.ext):
                raise RuntimeError("Unexpected file in trusted native staging")
            if item.name not in owned:
                # Process crashed between writing derived picture and its
                # fsynced source receipt. This is disposable DERIVED data.
                item.unlink()
        for other in self.staged.iterdir():
            if (other.name not in {
                    "scope.json","progress.jsonl","owner.lock",
                    "pictures","soundtrack.wav","manifest.json"} or
                other.is_symlink()):
                raise RuntimeError("Unexpected document in native color recovery")
        for name in ("soundtrack.wav","manifest.json"):
            item=self.staged/name
            if item.exists():
                if not item.is_file() or item.is_symlink():
                    raise RuntimeError("Corrupt derived soundtrack/manifest staging")
                item.unlink()  # Always regenerate/verify after a host crash.

    def _verify_row(self,row,index):
        name=f"{index+1:07d}"+self.ext
        if (type(row) is not dict or
            row.get("sample_index")!=index or
            row.get("png_file",row.get("exr_file"))!=name or
            type(row.get("source_tick")) is not str or
            type(row.get("sha256")) is not str or
            not re.fullmatch("[0-9a-f]{64}",row["sha256"])):
            raise RuntimeError("Native picture journal source identity corrupted")
        file=self.pictures/name
        if (file.is_symlink() or not file.is_file() or
            _file_sha256(file)!=row["sha256"]):
            raise RuntimeError("Recovered derived original-color picture SHA changed")

    def append(self,row):
        if len(self.records)>=MAX_FRAMES:
            raise RuntimeError("Bounded source film sequence exceeded")
        self._verify_row(row,len(self.records))
        file=self.pictures/(row.get("png_file") or row["exr_file"])
        with file.open("rb") as stream:os.fsync(stream.fileno())
        progress=self.staged/"progress.jsonl"
        with progress.open("ab") as output:
            raw=_canonical(row)
            if len(raw)+1>MAX_ROW_BYTES:
                raise RuntimeError("Unbounded derived image source receipt")
            output.write(raw+b"\n")
            output.flush();os.fsync(output.fileno())
        self.records.append(row)

    def prepare_publish(self):
        """Keep recovery receipts until the exact no-clobber rename succeeds.

        Removing the scope before the rename would make a crash just before
        publication unrecoverable. Target publish must be the linearization.
        """
        if not (self.staged/"scope.json").is_file():
            raise RuntimeError("Verified native source scope disappeared")
        if self.target.exists() or self.target.is_symlink():
            raise FileExistsError("No replacement of an approved presentation")

    def finish_published(self):
        """Target exists; now remove only internal native recovery metadata."""
        self.release()
        for name in ("scope.json","progress.jsonl","owner.lock"):
            (self.target/name).unlink(missing_ok=True)

    def release(self):
        if self.fd is not None:
            try:
                if os.name=="nt":
                    import msvcrt
                    self.fd.seek(0)
                    msvcrt.locking(self.fd.fileno(),msvcrt.LK_UNLCK,1)
                else:
                    import fcntl
                    fcntl.flock(self.fd.fileno(),fcntl.LOCK_UN)
            finally:
                self.fd.close()
                self.fd=None
