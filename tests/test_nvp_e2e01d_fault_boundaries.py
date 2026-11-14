"""E2E-01D: prove each declared AUDIO-01I/J/K injection is live.

All fault switches run in actual isolated Python subprocesses so os._exit
cannot kill the test runner. AST audits actual source and worker files to
detect a boundary that is declared but not wired at a side-effect site.

This is checkpoint wiring acceptance, NOT real approved-media crash recovery.
"""
from __future__ import annotations
import ast
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
CASES={
    "i": {
        "module":"backend.nvp_audio01i_fault_matrix",
        "env":"NVP_AUDIO01I",
        "sources":["backend/nvp_audio01i_native_host.py",
                   "backend/nvp_audio01i_mastering.py",
                   "tools/nvp_audio01i_native_worker.py"],
    },
    "j": {
        "module":"backend.nvp_audio01j_fault_matrix",
        "env":"NVP_AUDIO01J",
        "sources":["backend/nvp_audio01j_native_host.py",
                   "backend/nvp_audio01j_final_av.py",
                   "tools/nvp_audio01j_native_worker.py"],
    },
    "k": {
        "module":"backend.nvp_audio01k_fault_matrix",
        "env":"NVP_AUDIO01K",
        "sources":["backend/nvp_audio01k_native_host.py",
                   "backend/nvp_audio01k_distribution.py"],
    },
}


def called_checkpoints(paths):
    names=set()
    for rel in paths:
        path=ROOT/rel
        tree=ast.parse(path.read_text("utf8"),filename=str(path))
        for node in ast.walk(tree):
            if (isinstance(node,ast.Call)
                and isinstance(node.func,ast.Name)
                and node.func.id=="crash_after"
                and len(node.args)==1
                and isinstance(node.args[0],ast.Constant)
                and isinstance(node.args[0].value,str)):
                names.add(node.args[0].value)
    return names


def isolated_gate(module,env,point,mode):
    environment=os.environ.copy()
    # Strip other active injection controls to avoid inheriting toxic dev env.
    for config in CASES.values():
        environment.pop(config["env"]+"_FAULT_TEST",None)
        environment.pop(config["env"]+"_CRASH_AFTER",None)
    if mode!="disabled":
        environment[env+"_CRASH_AFTER"]=point
    if mode=="enabled":
        environment[env+"_FAULT_TEST"]="enabled"
    code=("from "+module+" import crash_after; crash_after("+repr(point)+")")
    return subprocess.run([sys.executable,"-c",code],cwd=ROOT,
        env=environment,stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        timeout=15,check=False)


class NativeFaultBoundaryWiring(unittest.TestCase):
    def test_all_declared_i_j_k_checkpoint_calls_exist(self):
        for category,config in CASES.items():
            module=__import__(config["module"],fromlist=["BOUNDARIES"])
            declared=set(module.BOUNDARIES)
            self.assertEqual(len(declared),len(module.BOUNDARIES),
                             category+": duplicate checkpoint")
            present=called_checkpoints(config["sources"])
            self.assertEqual(declared,present,
                category+": declared checkpoints must match actual code")

    def test_each_checkpoint_really_terminates_an_isolated_process(self):
        count=0
        for category,config in CASES.items():
            module=__import__(config["module"],fromlist=["BOUNDARIES","EXIT_CODE"])
            for point in module.BOUNDARIES:
                with self.subTest(group=category,boundary=point):
                    result=isolated_gate(config["module"],config["env"],point,"enabled")
                    self.assertEqual(result.returncode,module.EXIT_CODE,
                                     result.stderr.decode("utf8","replace"))
                    count+=1
        self.assertGreaterEqual(count,40)

    def test_fault_switch_requires_explicit_test_opt_in(self):
        for category,config in CASES.items():
            module=__import__(config["module"],fromlist=["BOUNDARIES"])
            for point in module.BOUNDARIES:
                with self.subTest(group=category,boundary=point):
                    disabled=isolated_gate(config["module"],config["env"],
                                           point,"disabled")
                    self.assertEqual(disabled.returncode,0)
                    wrong_mode=isolated_gate(config["module"],config["env"],
                                             point,"point_only")
                    self.assertEqual(wrong_mode.returncode,0)


if __name__=="__main__":
    unittest.main()
