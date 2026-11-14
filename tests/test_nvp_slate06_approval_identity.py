"""Independent original SLATE-06 creator-approval identity regression.

This uses the EXACT fixture, source cut and trusted creator-event path from the
original SLATE-06 test. It does not alter authorization or bypass a policy.
"""
import hashlib
import json
import unittest
from pathlib import Path
from test_nvp_slate06_geometry_native import Slate06NativeTests
from backend.nvp_slate_preview_host import (
    _adapter_for, SCRIPT_FILE, SOURCE_FILE, OUTPUT_FILE, canonical, sha, _digest)
from backend.nvp_blender_worker import BlenderOperation, sha_file


class Slate06ApprovalIdentity(unittest.TestCase):
    def test_original_geometry_approval_exact_identity(self):
        original=Slate06NativeTests(
            "test_native_host_approval_and_distinct_geometry_worker_script")
        original.setUp()
        try:
            host=original.host
            def examine(approval_id,digest,document):
                ok=host._approval_check(approval_id,digest,document)
                if ok:
                    return True
                with original.activity._db() as db:
                    row=db.execute(
                        "SELECT * FROM nvp_slate_preview_consents WHERE approval_id=?",
                        (approval_id,)).fetchone()
                if row is None:
                    raise AssertionError("Actual preview consent absent")
                names=("approval_id","task_id","project_id","edit_id",
                       "edit_revision","film_tick","quality","cache_key",
                       "ticket_sha256","source_manifest_sha256","spec_sha256",
                       "issued_at","expires_at","revoked_at","queued_at",
                       "presentation","camera_path")
                row=dict(zip(names,row))
                op=BlenderOperation(**document["operation"])
                adapter=_adapter_for(row["presentation"])
                ticket=host.lazy.select(
                    row["project_id"],row["edit_id"],row["edit_revision"],
                    film_tick=row["film_tick"],quality=row["quality"])
                directory=host.supervisor.root/op.job_id
                source=json.loads((directory/SOURCE_FILE).read_text("utf8"))
                expected={
                    "digest": (row["spec_sha256"],digest),
                    "canonical":(_digest(document),digest),
                    "task_id":(row["task_id"],document["task_id"]),
                    "operation_kind":("blender",document["kind"]),
                    "script_path":(SCRIPT_FILE,op.script),
                    "script_digest":(sha(adapter.BLENDER_SCRIPT.encode()),op.script_sha256),
                    "source_path":({SOURCE_FILE:row["source_manifest_sha256"]},op.inputs),
                    "output_path":({OUTPUT_FILE:"png"},op.outputs),
                    "args":({"--manifest":SOURCE_FILE,"--preview":OUTPUT_FILE},op.arguments),
                    "source_payload_sha":(row["source_manifest_sha256"],sha_file(directory/SOURCE_FILE)),
                    "ticket_sha":(row["ticket_sha256"],sha(canonical(ticket))),
                    "manifest_format":(adapter.FORMAT,source.get("format")),
                    "renderer_version":(adapter.RENDERER_VERSION,source.get("renderer_version")),
                    "worker_script":(op.script_sha256,source.get("worker_script_sha256")),
                    "source_cache":(row["cache_key"],source.get("source_cache_key")),
                    "source_take":(ticket["source_take_document_sha256"],source.get("source_take_sha256")),
                    "source_shot":(ticket["source_shot_document_sha256"],source.get("source_shot_sha256")),
                    "source_tick":(ticket["source_tick"],source.get("source_tick")),
                    "ticket_cache":(ticket["cache_key"],source.get("cache_key")),
                    "width":(adapter.DIMENSIONS[row["quality"]][0],source.get("width")),
                    "height":(adapter.DIMENSIONS[row["quality"]][1],source.get("height")),
                    "camera":(row["camera_path"],source.get("camera",{}).get("path")),
                    "final_approved":(False,source.get("final_presentation_approved")),
                    "pending_state":("PENDING",host.cache._job(op.job_id)["state"]),
                    "pending_key":(row["cache_key"],host.cache._job(op.job_id)["cache_key"]),
                    "pending_recipe":(row["source_manifest_sha256"],host.cache._job(op.job_id)["recipe_sha256"]),
                }
                failures={k:{"expected":a,"observed":b}
                          for k,(a,b) in expected.items() if a!=b}
                if not failures:
                    failures={"unknown": "Original _approval_check returns false despite listed matching fields"}
                raise AssertionError("ORIGINAL_SLATE06_APPROVAL_MISMATCH="+
                                     json.dumps(failures,sort_keys=True,default=str))
            host.dispatcher.bindings.approval_check=examine
            outcome=original.request(camera_path="/World/Camera")
            self.assertEqual(outcome["status"],"QUEUED")
        finally:
            original.doCleanups()


if __name__=="__main__":
    unittest.main()
