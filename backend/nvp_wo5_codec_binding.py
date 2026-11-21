"""WO5 protected native finished-film decoder admission.

Reuse actual WO3 Windows Program Files, pinned manifest, finite native
command grammar, EFS and AppContainer/Job authority. The trusted desktop
host supplies a fresh per-project cancellation/approval closure. Neither
project data, browser requests nor ambient executable environment grant it.
"""
from pathlib import Path
import json
import sys

from backend.nvp_wo3_native_codecs import (
    ProtectedCodecAuthority, ApprovedCodecBinary, common_codec_authority, ROLES, _sha)
from backend.nvp_wo3_dcp_structure import _linked_entry
from backend._nvp_wo5_release_pin import RELEASE_CODEC_MANIFEST_SHA256

PRODUCTS=("ASDCP-asdcp_unwrap","OpenJPEG-opj_decompress")


def pinned_codec_pair(root,manifest,expected_manifest_sha256,*,authority,project_id,check_cancel):
    """Return only the decoder pair admitted under one actual host authority."""
    pin=_sha(expected_manifest_sha256)
    if (not isinstance(authority,ProtectedCodecAuthority) or
            not callable(check_cancel) or type(project_id) is not str or
            authority.pin!=pin or authority.project_id!=project_id or
            authority.cancel is not check_cancel or
            type(manifest) is not dict or manifest!=authority.manifest):
        raise PermissionError("Exact project, build pin and protected decoder authority required")
    path=Path(root)
    if (not path.is_absolute() or any(_linked_entry(p) for p in (path,*path.parents)) or
            path.resolve(strict=True)!=authority.bundle):
        raise PermissionError("Decoder bundle differs from approved installed roster")
    records=authority._verify_bundle()
    codecs=tuple(ApprovedCodecBinary(authority.bundle/records[ROLES[p]]["filename"],
                sha256=records[ROLES[p]]["binary_sha256"],product=p,authority=authority)
                for p in PRODUCTS)
    if common_codec_authority(*codecs) is not authority:
        raise PermissionError("Decoder pair has no common protected authority")
    return codecs


def desktop_finished_decoder_provider(bundle_root,*,authority_factory=None):
    """No release pin or no trusted host factory -> disabled (never fallback)."""
    if not getattr(sys,"frozen",False) or not RELEASE_CODEC_MANIFEST_SHA256:
        return None
    if not callable(authority_factory):
        return None
    pin=_sha(RELEASE_CODEC_MANIFEST_SHA256)
    from backend.nvp_wo5_codec_provision import check_installed
    try:
        root=check_installed(pin)
    except (OSError,ValueError,PermissionError):
        return None
    if root!=Path(bundle_root)/"native-codecs"/pin:
        return None
    manifest_file=root/"nvp-codec-manifest.json"
    if (not root.is_absolute() or any(_linked_entry(p) for p in (manifest_file,*manifest_file.parents)) or
            not manifest_file.is_file() or not 1<=manifest_file.stat().st_size<=128*1024):
        return None
    try:
        raw=manifest_file.read_bytes()
        manifest=json.loads(raw)
    except (ValueError,OSError):
        return None
    from hashlib import sha256
    if sha256(raw).hexdigest()!=pin:
        return None
    def provider(project_id,check_cancel):
        authority=authority_factory(project_id,check_cancel)
        return pinned_codec_pair(root,manifest,pin,authority=authority,
                                 project_id=project_id,check_cancel=check_cancel)
    return provider
