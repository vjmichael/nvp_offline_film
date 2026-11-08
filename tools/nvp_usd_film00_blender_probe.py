"""USD-FILM-00 independent Blender 5.2 real USD importer/exporter audit.

Must run inside the PINNED, real Blender binary, not NVP's Python. A
reported operator flag is only an API capability; only the actual exported
USD, independently reopened by usd-core, counts as the real roundtrip.
This does not claim facial-rig fidelity, Hydra, MaterialX parity or pixels.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

import bpy

FORMAT = "nvp.usd_film00.blender_interop.v1"


def file_sha(path):
    h = sha256()
    with Path(path).open("rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def checked_file(raw, *, must_exist):
    value = Path(raw).resolve()
    if not value.is_absolute() or value.is_symlink() or not value.parent.is_dir():
        raise ValueError("Native Blender audit needs regular workspace files")
    if must_exist and not value.is_file():
        raise RuntimeError("Actual source/USD review file not present")
    if not must_exist and value.exists():
        raise RuntimeError("Audit worker may not overwrite prior evidence")
    return value


def run(source, target, report):
    src = checked_file(source, must_exist=True)
    dst = checked_file(target, must_exist=False)
    audit = checked_file(report, must_exist=False)
    if dst == src or audit in (src, dst):
        raise PermissionError("Source and audit outputs must be separate")
    original = file_sha(src)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    importer = bpy.ops.wm.usd_import
    exporter = bpy.ops.wm.usd_export
    import_flags = set(importer.get_rna_type().properties.keys())
    export_flags = set(exporter.get_rna_type().properties.keys())
    required_import = {
        "filepath", "import_meshes", "import_cameras", "import_lights",
        "import_blendshapes", "import_materials", "import_volumes",
        "support_scene_instancing",
    }
    required_export = {
        "filepath", "export_meshes", "export_cameras", "export_lights",
        "export_shapekeys", "export_materials", "export_volumes",
        "use_instancing",
    }
    if not required_import <= import_flags or not required_export <= export_flags:
        raise RuntimeError("Actual Blender build lacks declared USD importer/exporter support")
    result = importer(
        filepath=str(src), import_meshes=True, import_cameras=True,
        import_lights=True, import_blendshapes=True, import_materials=True,
        import_volumes=True, support_scene_instancing=True,
    )
    if "FINISHED" not in result:
        raise RuntimeError("Actual Blender USD import failed")
    imported = {
        "meshes": sum(x.type == "MESH" for x in bpy.data.objects),
        "cameras": sum(x.type == "CAMERA" for x in bpy.data.objects),
        "lights": sum(x.type == "LIGHT" for x in bpy.data.objects),
    }
    if min(imported.values()) < 1:
        raise RuntimeError("Original OpenUSD mesh, camera or light did not import")
    result = exporter(
        filepath=str(dst), export_meshes=True, export_cameras=True,
        export_lights=True, export_shapekeys=True,
        export_materials=True, export_volumes=True,
        use_instancing=False,
    )
    if "FINISHED" not in result or not dst.is_file() or dst.stat().st_size < 256:
        raise RuntimeError("Actual Blender USD export did not produce geometry")
    if file_sha(src) != original:
        raise RuntimeError("Blender unexpectedly modified the original USD test source")
    record = {
        "format": FORMAT,
        "blender_version": bpy.app.version_string,
        "blender_version_tuple": list(bpy.app.version),
        "actual_blender_usd_importer_flags": sorted(import_flags),
        "actual_blender_usd_exporter_flags": sorted(export_flags),
        "source_usd_sha256": original,
        "export_usd_sha256": file_sha(dst),
        "actual_imported": imported,
        "import_export_returned_success": True,
        "native_export_reopen_verified": False,
        "blender_usd_skeletal_roundtrip_verified": False,
        "blender_materialx_parity_verified": False,
        "actual_photoreal_pictures_produced": False,
    }
    audit.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", "utf8")
    print("USD_FILM00_ACTUAL_BLENDER_OPERATOR_AUDIT", record["blender_version"])


def main():
    import sys
    argv = sys.argv[sys.argv.index("--") + 1:]
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True)
    p.add_argument("--export", required=True)
    p.add_argument("--report", required=True)
    args = p.parse_args(argv)
    run(args.source, args.export, args.report)


if __name__ == "__main__":
    main()
