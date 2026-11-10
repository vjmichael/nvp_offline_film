"""PLAN-03: independently executed, source-bound original OpenUSD PNG worker.

This is a *trusted NVP child process* of NativeOriginalSceneRender. It never
receives a script, external executable, movie file, or creator approval from
the manifest. It reads only a locally saved frozen original Digital Take,
revalidates one exact Film Time source window and writes a disposable PNG.
The parent must separately authorize, supervise, and audit the worker.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

# Only NVP's trusted, pinned module path is added for a separately spawned
# source-run Python process. Never accept a browser- or model-supplied path.
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_plan02d_derived_raster import SourceSelectedNativeRaster
from backend.nvp_plan02d_source_selection import ExactSourceWindowSelector


FORMAT="nvp.plan03.native_original_source_render_worker.v1"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def render(manifest_path: Path):
    manifest_path=Path(manifest_path)
    root=manifest_path.parent.resolve(strict=True)
    if (manifest_path.is_symlink() or not manifest_path.is_file() or
            manifest_path.parent!=root):
        raise PermissionError("Refusing unpinned or symlinked render manifest")
    manifest=json.loads(manifest_path.read_text("utf8"))
    if type(manifest) is not dict or set(manifest)!={
            "format","project_id","request","selection_sha256",
            "source_tick","db_path","take_document_sha256"} or
            manifest["format"]!=FORMAT:
        raise ValueError("Only an exact original source render manifest")
    tick=manifest["source_tick"]
    if type(tick) is not int or tick<0:
        raise ValueError("Only exact integer Film Time tick")
    db=Path(manifest["db_path"])
    if not db.is_absolute() or db.is_symlink() or not db.is_file() or db.is_relative_to(root):
        raise ValueError("Only an existing original source SQLite database outside job workspace")
    studio=Studio(db)
    index=FilmIndex(studio)
    scope=ExactSourceWindowSelector(index).preview(manifest["project_id"],manifest["request"])
    if (scope["selection_sha256"]!=manifest["selection_sha256"] or
            scope["take_document_sha256"]!=manifest["take_document_sha256"] or
            not scope["first_tick"]<=tick<scope["last_tick_exclusive"]):
        raise PermissionError("Render no longer matches frozen source selection")
    actual=SourceSelectedNativeRaster(index,ask_native=lambda _scope:False).preview(
        manifest["project_id"],manifest["request"],scope["selection_sha256"],tick)
    png=actual["png_bytes"]
    if (_sha(png)!=actual["png_sha256"] or len(png)>12_000_000 or
            not png.startswith(bytes.fromhex("89504e470d0a1a0a"))):
        raise RuntimeError("Unverified native source PNG")
    output=root/"derived_source.png"
    if output.is_symlink() or output.exists():
        raise FileExistsError("Renderer must not overwrite any existing derived image")
    with output.open("xb") as stream:
        stream.write(png);stream.flush()
        import os
        os.fsync(stream.fileno())
    if _sha(output.read_bytes())!=actual["png_sha256"]:
        raise RuntimeError("Rendered PNG was altered on disk")
    if index.read_revision(manifest["project_id"],manifest["request"]["take_id"],1)[
            "document_sha256"]!=manifest["take_document_sha256"]:
        raise RuntimeError("Frozen source changed after render")
    receipt={
        "format":FORMAT,
        "status":"DERIVED_OPENUSD_IMAGE_ONLY",
        "selection_sha256":scope["selection_sha256"],
        "project_id":manifest["project_id"],
        "source_tick":tick,
        "take_document_sha256":manifest["take_document_sha256"],
        "png_sha256":actual["png_sha256"],
        "png_bytes":len(png),
        "creator_approval_conferred_by_child":False,
        "original_source_modified":False,
        "ffmpeg_used":False,
        "cinema_master_published":False,
    }
    dest=root/"render_receipt.json"
    with dest.open("x",encoding="utf8") as stream:
        json.dump(receipt,stream,sort_keys=True,indent=2)
        stream.flush();import os;os.fsync(stream.fileno())
    return receipt


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--manifest",required=True)
    arguments=p.parse_args(argv)
    render(Path(arguments.manifest))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
