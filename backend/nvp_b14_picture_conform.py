"""B14 worker-side, non-destructive conform of B13 editorial picture revisions.

This is an SDR16 review-picture conform, NOT a Rec.709 master, final video,
picture lock, or sound conform. Native authorization/worker supervision is
required by callers before reaching this module.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from backend.nvp_b12_editorial_delivery import verify_editorial_handoff, RATE
from backend.nvp_b13_editorial_roundtrip import verify_imported_edit, FORMAT as EDIT_FORMAT
from backend.nvp_film_index import _id
from backend.nvp_presentation_pipeline import _png_info

FORMAT = "nvp.presentation.b14.sdr16_picture_conform.v1"
MAX_FRAMES = 480


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf8")


def _new_file(path: Path, data: bytes) -> None:
    if path.is_symlink() or path.exists():
        raise RuntimeError("Conform refuses existing or symlinked output")
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _safe_directory(path: Path) -> None:
    """The native host must choose and authorize the destination parent."""
    if path.is_symlink() or path.exists():
        raise RuntimeError("Conform destination must be absent")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise RuntimeError("Conform destination parent is unsafe")


def _source_rows(edit: dict, original: dict):
    mapping = edit["editorial_map"]
    rows = mapping["frame_map"]
    original_frames = original["media_frames"]
    if (mapping["fps"] != RATE or not 1 <= len(rows) <= MAX_FRAMES or
        mapping["frame_count"] != len(rows) or
        len(original_frames) != original["frame_count"]):
        raise RuntimeError("Unbounded or incomplete editorial source frame mapping")
    for n, row in enumerate(rows, 1):
        srcno = row["source_frame"]
        if (type(srcno) is not int or not 1 <= srcno <= len(original_frames) or
            row["edit_frame"] != n):
            raise RuntimeError("Conform edit frames are not contiguous or bounded")
        src = original_frames[srcno - 1]
        if (src["frame"] != srcno or row["shot_id"] != src["shot_id"] or
            row["original_png16_sha256"] != src["png16_sha256"] or
            row["original_rgb48_sha256"] != src["rgb48_sha256"] or
            row["original_float32_sha256"] != src["source_exr_sha256"]):
            raise RuntimeError("Conform frame map disagrees with immutable FilmIndex media")
        yield n, src


def _frame_name(n: int) -> str:
    return f"edit_{n:06d}.png"


def conform_sdr16_picture(capture, project_id: str, edit_id: str, revision: int,
                           package: Path, destination: Path, presentation_id: str):
    """Executed ONLY in creator-approved, OS-contained B14 worker.

    A failed build cannot publish FilmIndex; an already-committed presentation
    remains verifiable by its immutable hashes. Failed output staging is retained
    for trusted cleanup, not automatically promoted or overwritten.
    """
    _id(presentation_id, "conformed presentation ID")
    if type(revision) is not int or revision < 1:
        raise ValueError("B14 requires an explicit exact edit revision")
    destination, package = Path(destination), Path(package)
    _safe_directory(destination)
    edit_record = capture.index.read_revision(project_id, edit_id, revision)
    edit = edit_record["data"]
    if edit_record["kind"] != "edit" or edit.get("format") != EDIT_FORMAT:
        raise RuntimeError("B14 only conforms genuine B13 imported edits")
    proof = verify_imported_edit(capture, project_id, edit_id, package, revision=revision)
    if proof["status"] != "VERIFIED_EDITED_OTIO_REVISION":
        raise RuntimeError("Edited source did not pass B13 verification")
    delivery_id = edit["source_delivery_id"]
    verify_editorial_handoff(capture, project_id, delivery_id, package, check_decode=False)
    source_record = capture.index.read_revision(project_id, delivery_id, 1)
    if source_record["document_sha256"] != edit["source_delivery_sha256"]:
        raise RuntimeError("B14 source B12 version changed")
    original = source_record["data"]
    width, height = original["resolution"]
    rows = list(_source_rows(edit, original))
    destination.mkdir(mode=0o700)
    media = destination / "media"
    media.mkdir(mode=0o700)
    result_rows = []
    for n, src in rows:
        name = _frame_name(n)
        raw = capture.index.get_blob(project_id, src["png16_sha256"])
        if _sha(raw) != src["png16_sha256"]:
            raise RuntimeError("Indexed source PNG bytes changed")
        if (_png_info(raw) != (width, height) or
            raw[24] != 16 or raw[25] != 2):
            raise RuntimeError("B14 requires genuine RGB16 review PNG")
        output = media / name
        _new_file(output, raw)
        result_rows.append({
            "edit_frame": n, "source_frame": src["frame"], "shot_id": src["shot_id"],
            "relative_path": "media/" + name, "png16_sha256": _sha(raw),
            "source_exr_sha256": src["source_exr_sha256"],
            "source_rgb48_sha256": src["rgb48_sha256"],
            "size_bytes": len(raw),
        })
    manifest = {
        "format": FORMAT, "status": "technical_sdr16_picture_conform_unapproved",
        "project_id": project_id, "edit_id": edit_id, "edit_revision": revision,
        "edit_sha256": edit_record["document_sha256"],
        "source_delivery_id": delivery_id,
        "source_delivery_sha256": source_record["document_sha256"],
        "source_take_id": edit["source_take_id"],
        "source_take_sha256": edit["source_take_sha256"],
        "fps": RATE, "frame_count": len(result_rows),
        "resolution": [width, height],
        "color": "ACES2_SDR100_sRGB_16bit_RGB",
        "frames": result_rows,
        "source_take_modified": False, "audio_present": False,
        "picture_locked": False, "technical_mov_rendered": False,
        "final_master": False, "dcp_delivered": False,
    }
    _new_file(destination / "conform_manifest.json", _canonical(manifest))
    deps = [
        {"object_id": edit_id, "revision": revision, "role": "timeline"},
        {"object_id": delivery_id, "revision": 1, "role": "presentation"},
        {"object_id": edit["source_take_id"], "revision": 1, "role": "source_take"},
    ]
    rec = capture.index.register_revision(project_id, presentation_id, "presentation",
                                          manifest, expected_revision=0, dependencies=deps)
    check = verify_conformed_sdr16(capture, project_id, presentation_id, package,
                                   destination, edit_revision=revision)
    return {**check, "document_sha256": rec["document_sha256"]}


def verify_conformed_sdr16(capture, project_id: str, presentation_id: str,
                           package: Path, destination: Path, *, edit_revision: int):
    record = capture.index.read_revision(project_id, presentation_id, 1)
    data = record["data"]
    if (record["kind"] != "presentation" or record["revision"] != 1 or
        data.get("format") != FORMAT or data.get("project_id") != project_id or
        data.get("status") != "technical_sdr16_picture_conform_unapproved" or
        data.get("edit_revision") != edit_revision or
        data.get("source_take_modified") is not False or
        data.get("audio_present") is not False or
        data.get("picture_locked") is not False or
        data.get("technical_mov_rendered") is not False or
        data.get("final_master") is not False or
        data.get("dcp_delivered") is not False):
        raise RuntimeError("B14 was incorrectly classified as an approved final master")
    original_edit = capture.index.read_revision(project_id, data["edit_id"], edit_revision)
    if original_edit["document_sha256"] != data["edit_sha256"]:
        raise RuntimeError("B14 source edit revision was changed")
    edit_proof = verify_imported_edit(capture, project_id, data["edit_id"],
                                      Path(package), revision=edit_revision)
    if edit_proof["status"] != "VERIFIED_EDITED_OTIO_REVISION":
        raise RuntimeError("B14 original edit verification failed")
    source = capture.index.read_revision(project_id, data["source_delivery_id"], 1)
    if source["document_sha256"] != data["source_delivery_sha256"]:
        raise RuntimeError("B14 source delivery SHA changed")
    expected_deps = sorted([
        {"object_id": data["edit_id"], "revision": edit_revision, "role": "timeline"},
        {"object_id": data["source_delivery_id"], "revision": 1, "role": "presentation"},
        {"object_id": data["source_take_id"], "revision": 1, "role": "source_take"},
    ], key=lambda x: (x["object_id"], x["revision"], x["role"]))
    if record["dependencies"] != expected_deps:
        raise RuntimeError("B14 immutable FilmIndex dependency edges changed")
    if data["source_take_sha256"] != original_edit["data"]["source_take_sha256"]:
        raise RuntimeError("Frozen Digital Take provenance changed")
    if (data["fps"] != RATE or data["color"] != "ACES2_SDR100_sRGB_16bit_RGB"
        or data["resolution"] != source["data"]["resolution"]):
        raise RuntimeError("Edited review output falsely advertised its timebase or color")
    rows = list(_source_rows(original_edit["data"], source["data"]))
    if len(rows) != data["frame_count"] or len(rows) != len(data["frames"]):
        raise RuntimeError("Edited picture lost or added frames")
    destination = Path(destination)
    if not destination.is_dir() or destination.is_symlink():
        raise RuntimeError("Conformed output directory is missing or symlinked")
    manifest = destination / "conform_manifest.json"
    if (manifest.is_symlink() or not manifest.is_file() or
        manifest.read_bytes() != _canonical(data)):
        raise RuntimeError("B14 exported manifest differs from immutable FilmIndex")
    media = destination / "media"
    if not media.is_dir() or media.is_symlink():
        raise RuntimeError("B14 media directory is unsafe")
    width, height = data["resolution"]
    for (n, src), output in zip(rows, data["frames"]):
        rel = "media/" + _frame_name(n)
        if (output["edit_frame"] != n or output["source_frame"] != src["frame"] or
            output["shot_id"] != src["shot_id"] or output["relative_path"] != rel or
            output["png16_sha256"] != src["png16_sha256"] or
            output["source_exr_sha256"] != src["source_exr_sha256"] or
            output["source_rgb48_sha256"] != src["rgb48_sha256"]):
            raise RuntimeError("B14 exported frame order differs from B13 edit")
        file = media / _frame_name(n)
        if not file.is_file() or file.is_symlink():
            raise RuntimeError("B14 exported picture file is missing or symlinked")
        raw = file.read_bytes()
        if (len(raw) != output["size_bytes"] or _sha(raw) != src["png16_sha256"] or
            capture.index.get_blob(project_id, src["png16_sha256"]) != raw or
            _png_info(raw) != (width, height) or raw[24] != 16 or raw[25] != 2):
            raise RuntimeError("B14 conformed image is not the original indexed SDR16 frame")
    return {"format": FORMAT, "status": "VERIFIED_SDR16_PICTURE_CONFORM",
            "presentation_id": presentation_id, "edit_id": data["edit_id"],
            "edit_revision": edit_revision, "frames": len(rows), "fps": RATE,
            "source_unchanged": True, "audio_present": False,
            "picture_locked": False, "technical_mov_rendered": False}
