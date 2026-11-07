"""Host-authoritative WO3 crash recovery adapter.

Only the local FilmIndex for the selected project supplies accepted receipts.
No browser/LLM-provided ledger objects, automatic promotion or deletion.
"""
from __future__ import annotations

from pathlib import Path
from backend.nvp_film_index import FilmIndex
from backend.nvp_wo3_dcp_package import FORMAT as DCP_FORMAT
from backend.nvp_wo3_export_recovery import reconcile_dcp_exports


def reconcile_project_dcp_exports(index: FilmIndex, project_id, output_root):
    if not isinstance(index, FilmIndex):
        raise PermissionError("Native local FilmIndex required")
    receipts = []
    for obj in index.list_objects(project_id, kind="presentation",
                                  include_retired=True):
        # Historical revisions are not replaced by later mutable heads.
        history = index.history(project_id, obj["object_id"])
        for revision in history:
            number = revision["revision"]
            record = index.read_revision(project_id, obj["object_id"], number)
            if record["kind"] != "presentation":
                raise RuntimeError("Presentation object kind changed")
            data = record["data"]
            if data.get("format") != DCP_FORMAT:
                continue
            dependencies = record["dependencies"]
            if (len(dependencies) != 1 or dependencies[0]["role"] != "source_take"
                    or data.get("original_data_modified") is not False):
                raise RuntimeError("Trusted cinema receipt has invalid source custody")
            receipts.append({
                "destination_name": data["destination_name"],
                "file_sha256": data["file_sha256"],
            })
    result = reconcile_dcp_exports(output_root, receipts)
    result["trusted_project_ledger_loaded"] = True
    result["project_id"] = project_id
    return result
