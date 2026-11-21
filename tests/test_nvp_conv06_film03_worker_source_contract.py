"""Exact original Film03 fixed-script provenance and protected-host source gate.

Source-only: this does not prove Blender/SCM/cgroup/physical render acceptance.
"""
from __future__ import annotations
import ast
from hashlib import sha1
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
BLOBS = {
    "tools/nvp_film03_actor_animation_worker.py": "5d765f5dfe7c11249be2c4e1dffbb3f5034ff484",
    "tools/nvp_film03_actor_animation_reopen.py": "a60e47e19d1a5b890297d94b11044fd23bba9751",
    "tools/nvp_film03_real_face_blender_worker.py": "78e55445633ffdcc0a5bd77454391c7ca21ec1c8",
    "tools/nvp_film03_real_face_blender_reopen.py": "528fb21f27d722d23ff69cb43bbce5d4f7d781ca",
}


class OriginalFilm03WorkerContracts(unittest.TestCase):
    def test_fixed_first_party_blender_worker_blobs_and_no_network_exec(self):
        for filename, blob in BLOBS.items():
            with self.subTest(source=filename):
                raw = (ROOT / filename).read_bytes()
                self.assertEqual(sha1(b"blob "+str(len(raw)).encode("ascii")+
                                      b"\0"+raw).hexdigest(), blob)
                tree = ast.parse(raw, filename=filename)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        names = [alias.name for alias in node.names]
                    elif isinstance(node, ast.ImportFrom):
                        names = [node.module or ""]
                    else:
                        names = []
                    self.assertFalse(any(name.split(".")[0] in {
                        "subprocess","socket","requests","urllib","httpx",
                        "importlib"} for name in names))
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                        self.assertNotIn(node.func.id, {"eval","exec"})

    def test_existing_real_actor_and_face_hosts_enforce_private_kernel_custody(self):
        actor=(ROOT/"backend/nvp_film03_actor_animation_host.py").read_text()
        face=(ROOT/"backend/nvp_film03_blender_face_host.py").read_text()
        for source in (actor,face):
            self.assertIn("BlenderWorkerSupervisor",source)
            self.assertIn("require_linux_cgroup_v2=True",source)
            self.assertIn("require_private_isolation=True",source)
        self.assertIn("nvp_film03_actor_animation_worker.py",actor)
        self.assertIn("nvp_film03_real_face_blender_worker.py",face)
        self.assertIn("nvp_film03_real_face_blender_reopen.py",face)


if __name__ == "__main__":
    unittest.main()
