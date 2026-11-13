"""Real first-party C++ native worker functional acceptance.

Runs actual amd64 PE64/ELF64 binaries, checks independently computed output
bytes and SHA receipts and input immutability. Windows requires the ORIGINAL
suspended-then-Job-assigned launch and kernel process-tree accounting.
Linux runs direct subprocess functional fixtures ONLY; delegated cgroup-v2
custody remains separately required for production approval. These FIVE
slices are NOT device recording, Blender/OpenUSD, editing, spatial sound or DCP.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

from tools.nvp_w1g_worker_package import (
    _verify_binary,_check_roster,provision_native_workers,verify_native_workers,
)

EXPECTED={
    "original_capture":("capture.manifest","pcm16_verified_intake"),
    "scene_render":("render.ppm","bounded_native_math_picture"),
    "editorial":("edit.pcm","bounded_pcm_non_destructive_cut"),
    "audio":("mix.pcm","bounded_native_pcm_gain"),
    "delivery":("delivery.bundle","finite_native_media_bundle"),
}
ORIGINAL_SAMPLES=(0,1,500,-500,30000,-30000)
PCM=struct.pack("<"+("h"*len(ORIGINAL_SAMPLES)),*ORIGINAL_SAMPLES)


def _sha(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()


def _input(directory:Path,role:str,render_bytes:bytes,mix_bytes:bytes):
    if role in ("original_capture","editorial","audio"):
        (directory/"source.pcm").write_bytes(PCM)
    if role=="editorial":
        (directory/"edit.txt").write_text("1 3\n",encoding="ascii")
    if role=="scene_render":
        (directory/"scene.txt").write_text("64 48\n",encoding="ascii")
    if role=="audio":
        (directory/"gain.txt").write_text("2 1\n",encoding="ascii")
    if role=="delivery":
        (directory/"render.ppm").write_bytes(render_bytes)
        (directory/"mix.pcm").write_bytes(mix_bytes)


def _execute(executable:Path,work:Path,*,expect_success=True):
    path=work/"plan.json"
    command=[str(executable.resolve()),"--plan",str(path.resolve())]
    if os.name=="nt":
        # Actual suspended CreateProcess + Job assignment BEFORE resuming.
        from backend.nvp_worker_containment import launch_contained
        from backend.nvp_w1g_kernel_custody import verified_native_worker_exit
        with (work/"stdout.log").open("xb") as out,(
                work/"stderr.log").open("xb") as err:
            worker=launch_contained(command,cwd=str(work),
                                    stdout=out,stderr=err,memory_mb=512)
            rc=worker.wait(timeout=30)
            evidence=verified_native_worker_exit(worker)
        assert evidence["process_tree_custody_verified"] is True
        assert evidence["active_processes_at_close"]==0
        os_evidence="windows-original-job-object"
    else:
        completed=subprocess.run(command,cwd=work,stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,timeout=30,check=False)
        rc=completed.returncode
        evidence=None
        os_evidence="linux-functional-only-no-delegated-cgroup-claim"
    if expect_success:
        if rc!=0:
            if os.name=="nt":
                diagnostic=(work/"stderr.log").read_bytes()[:8192].decode(
                    "utf8",errors="replace")
            else:
                diagnostic=completed.stderr[:8192].decode("utf8",errors="replace")
            raise RuntimeError(
                f"Actual {executable.name} failed with exit {rc}; "
                f"original native worker stderr={diagnostic!r}")
    elif rc==0:
        raise RuntimeError(f"Actual {executable.name} wrongly accepted invalid role")
    return rc,os_evidence,evidence


def functional_acceptance(binary_dir:Path,*,platform:str) -> dict:
    binary_dir=Path(binary_dir)
    build=json.loads((binary_dir/"build-candidate.json").read_text("utf8"))
    roster=_check_roster(build["roster"])
    if roster["platform"]!=platform or len(roster["workers"])!=5:
        raise RuntimeError("Native functional verification requires one exact compiled five-role roster")
    roles={row["role"]:row for row in roster["workers"]}
    assert set(roles)==set(EXPECTED)
    for role,row in roles.items():
        exe=binary_dir/row["filename"]
        _verify_binary(exe,platform)
        if _sha(exe.read_bytes())!=row["sha256"]:
            raise RuntimeError("Reviewed compiled worker bytes changed before functional execution")
    results={}
    render_data=b""
    mix_data=b""
    with tempfile.TemporaryDirectory(prefix="nvp-w1g-native-functional-") as tmp:
        root=Path(tmp)
        for role in ("original_capture","scene_render","editorial","audio","delivery"):
            work=root/role
            work.mkdir()
            _input(work,role,render_data,mix_data)
            source_files={p.name:_sha(p.read_bytes()) for p in work.iterdir()}
            plan={"job_id":"w1g_test_"+role,
                  "project_id":"NVPFunctionalTest",
                  "role":role}
            raw=json.dumps(plan,sort_keys=True,separators=(",",":")).encode("ascii")
            (work/"plan.json").write_bytes(raw)
            _,evidence_type,kernel=_execute(binary_dir/roles[role]["filename"],work)
            result=json.loads((work/"result.json").read_text("utf8"))
            filename,operation=EXPECTED[role]
            produced=(work/filename).read_bytes()
            assert result=={
                "format":"nvp.w1g.native_worker_result.v1",
                "job_id":plan["job_id"],
                "project_id":plan["project_id"],
                "role":role,
                "plan_sha256":_sha(raw),
                "output_name":filename,
                "output_sha256":_sha(produced),
                "operation":operation,
                "output_bytes":len(produced),
                "full_film_pipeline_accepted":False,
            }, f"Unverified native worker result content: {role}"
            assert all(_sha((work/name).read_bytes())==digest
                       for name,digest in source_files.items()),"Original immutable native inputs changed"
            if role=="original_capture":
                assert f"samples={len(ORIGINAL_SAMPLES)}\n" in produced.decode("ascii")
                assert f"source_sha256={_sha(PCM)}" in produced.decode("ascii")
            elif role=="scene_render":
                assert produced.startswith(b"P6\n64 48\n255\n")
                pixels=produced[len(b"P6\n64 48\n255\n"):]
                assert len(pixels)==64*48*3 and len(set(pixels))>4
                render_data=produced
            elif role=="editorial":
                assert produced==PCM[2:8]
            elif role=="audio":
                assert struct.unpack("<6h",produced)==(
                    0,2,1000,-1000,32767,-32768)
                mix_data=produced
            elif role=="delivery":
                assert produced[:8]==b"NVPW1G01"
                l_picture,l_audio=struct.unpack("<QQ",produced[8:24])
                assert (l_picture,l_audio)==(len(render_data),len(mix_data))
                assert produced[24:]==render_data+mix_data
            results[role]={
                "compiled_worker_sha256":roles[role]["sha256"],
                "actual_operation":operation,
                "output_sha256":_sha(produced),
                "output_bytes":len(produced),
                "os_evidence":evidence_type,
                "whole_process_tree_custody_verified":
                    bool(kernel and kernel["process_tree_custody_verified"]),
                "immutable_inputs_verified":True,
            }
        # Negative case: compiled capture must reject a wrong sealed role
        # rather than publishing a fake result.
        bad=root/"mismatched"
        bad.mkdir()
        (bad/"source.pcm").write_bytes(PCM)
        wrong={"job_id":"w1g_wrongrole","project_id":"NVPFunctionalTest",
               "role":"delivery"}
        (bad/"plan.json").write_text(json.dumps(
            wrong,sort_keys=True,separators=(",",":")),encoding="ascii")
        _execute(binary_dir/roles["original_capture"]["filename"],bad,
                 expect_success=False)
        assert not (bad/"result.json").exists()
        assert (bad/"source.pcm").read_bytes()==PCM
        # Verify the EXACT tested compiled bytes survive first-party
        # private worker packaging, without ever calling this a reviewed
        # production install or requiring any user originals.
        private_bundle=root/"test_only_bundle"
        private_bundle.mkdir()
        provision_native_workers(binary_dir,private_bundle,roster)
        staged=verify_native_workers(private_bundle,expected_platform=platform)
        assert set(staged["roles"])==set(EXPECTED)
        for role,row in roles.items():
            staged_path=private_bundle/"_internal"/"nvp_workers"/row["filename"]
            assert _sha(staged_path.read_bytes())==row["sha256"]
    evidence={
        "format":"nvp.w1g.first_party_compiled_functional_slices.v1",
        "platform":platform,
        "five_native_executables_real_and_functionally_tested":True,
        "results":results,
        "role_count":5,
        "test_only_private_worker_bundle_roundtrip_verified":True,
        "exact_executable_sha256_preserved_during_staging":True,
        "full_native_filmmaking_domain_coverage_accepted":False,
        "production_reviewed_signed_redistribution":False,
        "creator_original_films_modified":False,
        "physical_efs_verified":False,
        "nsis_upgrade_authorized":False,
    }
    return evidence


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--binary-dir",type=Path,required=True)
    p.add_argument("--platform",choices=("windows-amd64","linux-amd64"),required=True)
    p.add_argument("--evidence",type=Path,required=True)
    a=p.parse_args(argv)
    if a.evidence.exists() or a.evidence.is_symlink():
        raise FileExistsError("Native functional evidence must not overwrite prior original receipt")
    result=functional_acceptance(a.binary_dir,platform=a.platform)
    a.evidence.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf8")
    print(json.dumps({"status":"FIVE_COMPILED_NATIVE_CAPABILITY_SLICES_ACCEPTED",
                      "platform":a.platform,"roles":list(result["results"]),
                      "release_approved":False},sort_keys=True))


if __name__=="__main__":
    main()
