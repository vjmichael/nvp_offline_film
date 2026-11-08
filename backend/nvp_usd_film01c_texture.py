"""USD-FILM-01C — verified project-local texture resolution for derived film sets.

ONLY the existing FilmIndex-owned nvp-blob://texture/SHA original PNG may
be mapped to short, disposable USD-relative paths. No global resolver, file
pickers, arbitrary URLs or renderer-supplied paths. The authoritative
asset/scene USD and authored texture descriptors are not edited.

Resolves both UsdUVTexture and MaterialX ND_image file attributes; refuses
unknown, dangling, unregistered or cross-project texture sources.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from backend.nvp_native_usd_texture import (
    PREFIX, verified_texture,
)

MAX_TEXTURES_PER_SOURCE = 40
MAX_TEXTURE_STAGED_BYTES = 96 * 1024 * 1024


def source_texture_descriptors(index, pid, *, kind, record):
    """Inspect original FilmIndex documents, not USD-provided filesystem paths."""
    if kind == "asset":
        records = [record]
    elif kind == "scene":
        records = []
        from backend.nvp_openusd_assets import OpenUSDAssetRegistry
        registry = OpenUSDAssetRegistry(index)
        for binding in record["data"].get("asset_bindings", []):
            source, _ = registry.open(
                pid, binding["asset_id"], binding["asset_revision"])
            if source["document_sha256"] != binding["asset_document_sha256"]:
                raise PermissionError("Scene texture asset binding changed")
            records.append(source)
    else:
        raise ValueError("Unsupported texture source type")
    descriptors = {}
    for source in records:
        mat = source["data"].get("preview_material") or {}
        collection = []
        if mat.get("texture") is not None:
            collection.append(mat["texture"])
        if mat.get("pbr_maps"):
            collection.extend(mat["pbr_maps"].values())
        for desc in collection:
            png, _ = verified_texture(index, pid, desc)
            sha = desc["sha256"]
            if len(descriptors) >= MAX_TEXTURES_PER_SOURCE and sha not in descriptors:
                raise ValueError("Too many original textures for one scene")
            if sha in descriptors and descriptors[sha] != png:
                raise RuntimeError("Conflicting source texture hash collision")
            descriptors[sha] = png
    return descriptors


def derive_texture_resolved_layer(index, pid, source_stage, *,
                                  source_kind, source_record):
    """Remap only actual verified USD AssetPath attributes in a derived layer.

    The original source_stage must be a NVP-opened, source-verified stage.
    Returns derived layer bytes + original PNG bytes to be staged privately.
    """
    from pxr import Sdf, Usd
    if not isinstance(source_stage, Usd.Stage):
        raise TypeError("Only a genuine NVP OpenUSD original source stage")
    texture_bytes = source_texture_descriptors(
        index, pid, kind=source_kind, record=source_record)
    derived = source_stage.Flatten(addSourceFileComment=False)
    stage = Usd.Stage.Open(derived)
    expected = {PREFIX + sha for sha in texture_bytes}
    seen = set()
    for prim in stage.TraverseAll():
        for attr in prim.GetAttributes():
            if attr.GetTypeName() != Sdf.ValueTypeNames.Asset:
                continue
            if attr.GetConnections():
                raise PermissionError("USD texture file may not be controlled upstream")
            raw = attr.Get()
            if raw is None or not isinstance(raw, Sdf.AssetPath):
                raise PermissionError("Malformed original USD AssetPath attribute")
            key = str(raw.path)
            if not key:
                continue
            if key not in expected:
                raise PermissionError(
                    "USD source references an unapproved image path or external asset")
            sha = key[len(PREFIX):]
            path = "../textures/" + sha + ".png"
            if not attr.Set(Sdf.AssetPath(path)):
                raise RuntimeError("Could not author private derived texture path")
            seen.add(key)
    if seen != expected:
        raise PermissionError("Original film texture manifest and shader graph differ")
    data = stage.GetRootLayer().ExportToString().encode("utf8")
    return data, texture_bytes


def write_verified_texture_files(directory, texture_bytes):
    """Write immutable verified PNGs to a private directory, rejecting symlinks."""
    import os
    root = Path(directory)
    if not root.is_dir() or root.is_symlink():
        raise PermissionError("Original texture stage directory must be private")
    if sum(map(len, texture_bytes.values())) > MAX_TEXTURE_STAGED_BYTES:
        raise ValueError("World exceeds texture staging budget")
    paths = []
    for sha, png in sorted(texture_bytes.items()):
        if (len(sha) != 64 or sha256(png).hexdigest() != sha or
            any(c not in "0123456789abcdef" for c in sha)):
            raise PermissionError("Source texture checksum differs from FilmIndex")
        target = root / (sha + ".png")
        if target.exists() or target.is_symlink():
            # Deduplicated same verified texture from several original assets.
            if target.is_symlink() or not target.is_file() or \
               sha256(target.read_bytes()).hexdigest() != sha:
                raise PermissionError("Private staged texture was replaced")
        else:
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os,"O_BINARY",0)
            fd = os.open(target,flags,0o600)
            with os.fdopen(fd,"wb") as f:
                f.write(png)
                f.flush()
                os.fsync(f.fileno())
            target.chmod(0o400)
        paths.append(str(target))
    return paths
