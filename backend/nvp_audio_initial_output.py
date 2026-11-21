"""Source-bound zero-chunk output publication for a stopped or not-started job.

Caller owns the staging lease and lock. The durable host admission must bind
this exact receipt before creating output. No existing canonical file is
replaced; interrupted initial-stage bytes are retained in the job evidence.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import stat
from backend.nvp_audio01d_chunked_recovery import (
    FORMAT, RATE, CHANNELS, _validate, _source_receipts, _json_bytes,
)


def initial_bytes(spec):
    stems = _validate(spec['plan'], spec['sources'], spec['total_samples'])
    sources = _source_receipts(stems, spec['sources'])
    if {s['stem_id']: s['source_sha256'] for s in sources} != spec['source_sha256']:
        raise PermissionError('Initial output sources changed')
    return _json_bytes(dict(format=FORMAT, status='in_progress', total_samples=spec['total_samples'],
                            sample_rate=RATE, channels=CHANNELS, sources=sources,
                            chunks=[], next_sample=0, final_mix=False, final_master=False))


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _private_dir(path):
    s = path.lstat()
    if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.geteuid() or s.st_mode & 0o077:
        raise PermissionError('Initial output is not a private owned directory')


def _read(path, bound):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        s = os.fstat(fd)
        if (not stat.S_ISREG(s.st_mode) or s.st_uid != os.geteuid() or
                s.st_mode & 0o022 or s.st_size > bound):
            raise PermissionError('Unexpected initial-stage artifact')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(bound + 1)
        if len(raw) != s.st_size:
            raise PermissionError('Initial-stage artifact changed')
        return raw, s
    finally:
        os.close(fd)


def _write_new(path, raw):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())


def publish_initial(spec, expected_sha, evidence, *, recovering=False):
    raw = initial_bytes(spec)
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise PermissionError('Initial output intent hash mismatch')
    root = Path(spec['directory'])
    evidence = Path(evidence)
    if root.resolve() != root or root.parent.resolve() != root.parent:
        raise PermissionError('Unsafe initial output path')
    _private_dir(evidence)
    if not root.exists():
        if recovering:
            raise PermissionError('Missing output requires admission reconciliation')
        root.mkdir(mode=0o700)
        sync_dir(root.parent)
    elif not recovering:
        raise PermissionError('Fresh initial output already exists')
    _private_dir(root)
    final = root / 'checkpoint.json'
    stage = root / 'checkpoint.json.new'
    entries = {p.name for p in root.iterdir()}
    if entries - {final.name, stage.name}:
        raise PermissionError('Unexplained initial output artifacts')
    if final.name in entries:
        old, fs = _read(final, len(raw))
        if old != raw:
            raise PermissionError('Existing initial checkpoint is not source-exact')
        if stage.name in entries:
            pending, ss = _read(stage, len(raw))
            if (pending != raw or fs.st_nlink != 2 or ss.st_nlink != 2 or
                    (ss.st_dev, ss.st_ino) != (fs.st_dev, fs.st_ino)):
                raise PermissionError('Unrelated initial checkpoint publication stage')
            sync_dir(root)
            stage.unlink()
            sync_dir(root)
        elif fs.st_nlink != 1:
            raise PermissionError('Foreign initial checkpoint link')
        return
    if stage.name in entries:
        pending, ss = _read(stage, len(raw))
        if ss.st_nlink != 1 or not raw.startswith(pending):
            raise PermissionError('Initial checkpoint stage cannot be verified')
        if pending != raw:
            # Copy the exact incomplete bytes before disposing of our temporary
            # file. A digest-addressed evidence file is itself replay-safe.
            residue = evidence / ('initial-stage-' + hashlib.sha256(pending).hexdigest() + '.bin')
            if residue.exists() or residue.is_symlink():
                saved, rs = _read(residue, len(raw))
                if not pending.startswith(saved) or rs.st_nlink != 1:
                    raise PermissionError('Initial stage evidence conflicts')
                if saved != pending:
                    fd=os.open(residue,os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW)
                    with os.fdopen(fd,'ab') as f:
                        current=os.fstat(f.fileno())
                        if (current.st_dev,current.st_ino,current.st_size,current.st_nlink)!=(rs.st_dev,rs.st_ino,len(saved),1):
                            raise PermissionError('Initial residue changed')
                        f.write(pending[len(saved):]);f.flush();os.fsync(f.fileno())
            else:
                _write_new(residue, pending)
            sync_dir(evidence)
            stage.unlink()
            sync_dir(root)
    if not stage.exists():
        _write_new(stage, raw)
    os.link(stage, final, follow_symlinks=False)
    sync_dir(root)
    stage.unlink()
    sync_dir(root)
