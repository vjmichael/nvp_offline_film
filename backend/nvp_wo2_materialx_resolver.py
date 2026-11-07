"""WO2 tightly scoped MaterialX image resolver for independent renderer probes.

A generic USD/Hydra renderer must NEVER resolve nvp-blob:// globally.
Only a separately approved native rendering operation can create disposable
read-only copies of verified project-owned source PNG bytes. An anonymous,
flattened *derived* stage refers to those paths; frozen USD is unchanged.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import os

from backend.nvp_native_usd_texture import verified_texture,PREFIX


@contextmanager
def resolved_materialx_probe(index, project_id, original_stage, descriptors):
    from pxr import Sdf,Usd,UsdShade
    if (type(descriptors) is not list or not 1<=len(descriptors)<=16 or
        not isinstance(original_stage,Usd.Stage)):
        raise ValueError("Trusted USD stage and bounded original textures required")
    verified={}
    for desc in descriptors:
        png,_=verified_texture(index,project_id,desc)
        digest=desc["sha256"]
        if digest in verified and verified[digest]!=png:
            raise RuntimeError("Conflicting original PNG source identity")
        verified[digest]=png
    expected={PREFIX+digest for digest in verified}
    # Flatten ONLY into a new, nonpersistent layer. NEVER apply edits to the
    # frozen original stage, its layer stack or FilmIndex objects.
    copy_layer=original_stage.Flatten()
    resolved=Usd.Stage.Open(copy_layer)
    if not resolved:
        raise RuntimeError("Cannot open disposable flattened USD probe stage")
    files=[]
    for prim in resolved.Traverse():
        node=UsdShade.Shader(prim)
        if not node:continue
        source=node.GetInput("file")
        if source:
            raw=source.GetAttr().Get()
            if not isinstance(raw,Sdf.AssetPath):
                raise RuntimeError("MaterialX file input is not USD asset typed")
            key=str(raw.path)
            if key not in expected:
                raise PermissionError("Source USD shader attempted unapproved file")
            files.append((source,key))
    if not files or {key for _,key in files}!=expected:
        raise RuntimeError("Original USD texture graph differs from approved scope")
    with TemporaryDirectory(prefix="nvp-wo2-materialx-") as directory:
        root=Path(directory)
        paths={}
        for digest,png in verified.items():
            dest=root/(digest+".png")
            flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_BINARY",0)
            fd=os.open(dest,flags,0o600)
            try:
                with os.fdopen(fd,"wb") as file:
                    file.write(png)
                    file.flush()
                    os.fsync(file.fileno())
            except Exception:
                # fdopen owns fd after success; TemporaryDirectory cleans up.
                raise
            paths[PREFIX+digest]=str(dest)
        for source,key in files:
            # A temporary *derived* USD layer may reference an approved
            # file during this context lifetime only.
            source.Set(Sdf.AssetPath(paths[key]))
        evidence={
            "format":"nvp.wo2.scoped_materialx_resolver.v1",
            "approved_original_texture_sha256":sorted(verified),
            "original_layer_mutated":False,
            "external_untrusted_file_admitted":False,
            "derived_probe_only":True,
            "independent_hydra_render_accepted":False,
        }
        yield resolved,evidence
