"""Immutable sealed section bodies, indexed only by the live film transaction.

The current G03 SQLite snapshot remains the single authority. Unindexed pages
are never listed or adopted as edits. Legacy inline section rows still open.
No alternate key custody, plaintext staging, or automatic orphan deletion.
"""
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import shutil

from backend.nvp_g03_windows_vault import _no_link, _token, _encrypt_file, _decrypt_file, VaultError
from backend.nvp_wo3_atomic_publish import atomic_publish_directory

FORMAT = 'nvp.g07.sealed_section_page.v1'
MAX_BYTES = 256 * 1024
SHA = re.compile(r'[a-f0-9]{64}\Z')


def _location(folder, key, sha, *, create=False, missing_directory=False):
    if type(sha) is not str or not SHA.fullmatch(sha):
        raise VaultError('Invalid protected section page identity')
    _no_link(folder)
    root = Path(folder) / 'editorial-pages'
    if create:
        root.mkdir(exist_ok=True)
    try:
        _no_link(root)
    except FileNotFoundError:
        if not missing_directory:raise
    else:
        if not root.is_dir():raise VaultError('Protected section directory missing')
    return root / _token('editorial-page/' + sha, key)


def read_page(folder, pid, key, sha):
    try:
        target = _location(folder,key,sha)
        _no_link(target)
        body = target/'body.nvpsealed'
        _no_link(body)
        if not target.is_dir() or not body.is_file():raise VaultError("Protected section page missing")
    except OSError as exc:
        raise VaultError("Protected section page missing") from exc
    sink = io.BytesIO()
    receipt = _decrypt_file(body,sink,key=key,project_id=pid,
        name='editorial-page/'+sha,max_plain_bytes=MAX_BYTES)
    if receipt['sha256'] != sha:
        raise VaultError('Protected section page digest changed')
    return sink.getvalue().decode('utf8')


def seal_page(folder,pid,key,raw,sha):
    if type(raw) is not str:
        raise TypeError('Canonical section document required')
    data=raw.encode('utf8')
    if len(data)>MAX_BYTES or hashlib.sha256(data).hexdigest()!=sha:
        raise VaultError('Protected section page exceeds its approved identity or size')
    target=_location(folder,key,sha,create=True)
    if target.exists():
        if read_page(folder,pid,key,sha)!=raw:
            raise VaultError('Existing protected section page differs')
    else:
        stage=Path(tempfile.mkdtemp(prefix='.sealed-page-',dir=target.parent))
        try:
            _encrypt_file(io.BytesIO(data),stage/'body.nvpsealed',key=key,
                          project_id=pid,name='editorial-page/'+sha)
            # Authenticated readback before the immutable directory is visible.
            sink=io.BytesIO()
            r=_decrypt_file(stage/'body.nvpsealed',sink,key=key,project_id=pid,
                name='editorial-page/'+sha,max_plain_bytes=MAX_BYTES)
            if r['sha256']!=sha or sink.getvalue()!=data:
                raise VaultError('Protected section readback failed')
            atomic_publish_directory(stage,target)
        finally:
            if stage.exists():shutil.rmtree(stage)
        if read_page(folder,pid,key,sha)!=raw:
            raise VaultError('Published protected section page differs')
    return json.dumps({'format':FORMAT,'sha256':sha},sort_keys=True,separators=(',',':'))


def resolve(raw, sha, *, folder=None, pid=None, key=None):
    """Legacy inline canonical documents remain unchanged; sealed pointers fail closed."""
    if type(raw) is not str or len(raw.encode('utf8'))>MAX_BYTES:
        raise VaultError('Section record exceeds its bounded size')
    doc=json.loads(raw)
    if isinstance(doc,dict) and doc.get('format')==FORMAT:
        if doc!={'format':FORMAT,'sha256':sha} or folder is None or key is None:
            raise VaultError('Protected section page ownership missing')
        return read_page(folder,pid,key,sha)
    return raw
