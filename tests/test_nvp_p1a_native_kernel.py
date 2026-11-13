"""P1-A original OS kernel acceptance; no fake cgroup/Job/PID receipts.

These tests require real native Windows or a writable systemd-delegated Linux
cgroup-v2 scope. An unprovisioned native Linux runner is a BLOCKED gate, not
a passing/skipped SEC-06 receipt. Each test uses the exact production launcher.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from backend.nvp_worker_containment import launch_contained

FIXTURE=Path(__file__).resolve().parents[1]/"tools"/"nvp_p1a_native_custody_fixture.py"


def spool(tmp_path):
    result=tmp_path/"nvp-live-original-11223344aabbccdd"
    result.mkdir()
    return result


def wait_ready(path,proc=None,seconds=12):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if path.exists():
            return
        if proc is not None and proc.poll() is not None:
            logs=path.parent/"native.log"
            original=logs.read_text(errors="replace") if logs.is_file() else "<no native log>"
            raise AssertionError("Kernel-contained worker exited before descendant ready; "
                                 +original[-8000:])
        time.sleep(.05)
    raise AssertionError("Native detached descendant did not become ready")


def host_crash(path):
    env=os.environ.copy()
    root=str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"]=root+os.pathsep+env.get("PYTHONPATH","")
    outer=subprocess.run(
        [sys.executable,str(FIXTURE),"crash-host",str(path)],
        cwd=root,env=env,capture_output=True,timeout=35)
    assert outer.returncode==79, (
        f"Original host-crash fixture refused admission: {outer.returncode}\n"
        +outer.stdout.decode(errors="replace")+outer.stderr.decode(errors="replace")
        +(path/"host.log").read_text(errors="replace") if (path/"host.log").exists()
        else f"Original host-crash fixture returned {outer.returncode} without log")


def verify_restarted_host_has_only_unapproved_original(path):
    from backend.nvp_capture_recovery import OriginalCaptureJournal
    receipt=OriginalCaptureJournal(path.parent).catalog("P1NativeRecovery")
    assert receipt["status"]=="READ_ONLY_RECOVERY_EVIDENCE"
    assert receipt["auto_freeze"] is False
    assert receipt["auto_delete"] is False
    assert len(receipt["items"])==1
    row=receipt["items"][0]
    assert row["take_id"]=="InterruptedOriginalTake"
    assert row["phase"]=="CAPTURING"
    assert row["source_verified_for_freeze"] is False
    assert row["take_approved"] is False
    assert row["requires_native_owner_reconciliation"] is True
    assert not (path/"take.approved").exists()


def process_terminated_windows(pid):
    import win32api,win32con,win32event
    import pywintypes
    try:
        handle=win32api.OpenProcess(0x00101400,False,pid)  # SYNCHRONIZE
    except pywintypes.error as exc:
        if exc.winerror==87:  # ERROR_INVALID_PARAMETER: process no longer exists
            return True
        raise
    try:
        return win32event.WaitForSingleObject(handle,0)==win32event.WAIT_OBJECT_0
    finally:
        handle.Close()


@pytest.mark.skipif(os.name!="nt",reason="Real Windows kernel only")
def test_native_windows_job_cancel_detached_descendant(tmp_path):
    import win32api,win32job,win32event
    path=spool(tmp_path)
    with (path/"native.log").open("wb") as out:
        p=launch_contained(
            [sys.executable,str(FIXTURE),"worker",str(path)],
            cwd=path,stdout=out,stderr=out,memory_mb=512)
        handle=None
        try:
            wait_ready(path/"descendant.ready",p)
            pid=int((path/"descendant.pid").read_text())
            handle=win32api.OpenProcess(0x00101400,False,pid)
            assert win32job.IsProcessInJob(handle,p._job), "Detached descendant escaped Windows Job"
            assert win32event.WaitForSingleObject(handle,0)==win32event.WAIT_TIMEOUT
            p.terminate_tree()
            assert win32event.WaitForSingleObject(handle,5000)==win32event.WAIT_OBJECT_0
            info=win32job.QueryInformationJobObject(
                p._job,win32job.JobObjectBasicAccountingInformation)
            assert info["ActiveProcesses"]==0, "Job Object contains surviving descendant"
        finally:
            if p._job is not None:
                p.close()
            if handle is not None:
                handle.Close()


@pytest.mark.skipif(os.name!="nt",reason="Real Windows kernel only")
def test_native_windows_hard_host_exit_kills_detached_descendant(tmp_path):
    path=spool(tmp_path)
    host_crash(path)
    wait_ready(path/"descendant.ready")
    pid=int((path/"descendant.pid").read_text())
    end=time.monotonic()+10
    while time.monotonic()<end:
        if process_terminated_windows(pid):
            verify_restarted_host_has_only_unapproved_original(path)
            return
        time.sleep(.05)
    pytest.fail("Windows host crash left actual detached Job descendant active")


def native_linux_delegation():
    from backend.nvp_worker_linux_cgroup import current_delegated_parent
    try:
        return current_delegated_parent()
    except (OSError,RuntimeError) as exc:
        if os.environ.get("NVP_REQUIRE_DELEGATED_CGROUP")=="1":
            pytest.fail("BLOCKED: no real systemd delegated cgroup: "+str(exc))
        pytest.skip("No real delegated cgroup, not acceptance: "+str(exc))


def await_empty_leaf(path,seconds=20):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if not path.exists():
            return
        try:
            events=(path/"cgroup.events").read_text("ascii")
            if "populated 0" in events:
                return
        except FileNotFoundError:
            return
        time.sleep(.05)
    pytest.fail("Real Linux cgroup still populated after custody shutdown")


@pytest.mark.skipif(sys.platform!="linux",reason="Real Linux kernel only")
def test_linux_cgroup_descendant_and_ancestor_migration_denied(tmp_path):
    native_linux_delegation()
    path=spool(tmp_path)
    with (path/"native.log").open("wb") as out:
        p=launch_contained([sys.executable,str(FIXTURE),"worker",str(path)],
            cwd=path,stdout=out,stderr=out,memory_mb=512,
            linux_cgroup_tree_required=True,linux_write_spool=path)
        leaf=p.cgroup
        try:
            wait_ready(path/"descendant.ready",p)
            wait_ready(path/"ancestor-migration.json",p)
            verdict=json.loads((path/"ancestor-migration.json").read_text())
            assert verdict["attempt"]=="DENIED", (
                "SECURITY FAILURE: actual descendant migrated to ancestor cgroup")
            assert verdict["after"]==verdict["before"], (
                "SECURITY FAILURE: descendant left owned cgroup")
            assert str(leaf).endswith(verdict["before"])
            assert "populated 1" in (leaf/"cgroup.events").read_text()
            p.terminate_tree()
        finally:
            try:p.close()
            except Exception:
                # Do not hide a guardian or kernel cleanup fault.
                raise
        await_empty_leaf(leaf)
        assert not leaf.exists(), "Guardian did not remove owned cgroup leaf"


@pytest.mark.skipif(sys.platform!="linux",reason="Real Linux kernel only")
def test_linux_guardian_loss_fails_closed_and_kills_tree(tmp_path):
    native_linux_delegation()
    path=spool(tmp_path)
    with (path/"native.log").open("wb") as out:
        p=launch_contained([sys.executable,str(FIXTURE),"worker",str(path)],
            cwd=path,stdout=out,stderr=out,memory_mb=512,
            linux_cgroup_tree_required=True,linux_write_spool=path)
        leaf=p.cgroup
        wait_ready(path/"descendant.ready",p)
        p._guardian.kill()
        p._guardian.wait(timeout=5)
        with pytest.raises(RuntimeError,match="guardian died"):
            p.poll()
        # Guardian death must never be mistaken for an accepted complete
        # process-custody receipt; force cleanup with the real cgroup.kill.
        try:
            p.close()
        except RuntimeError as exc:
            assert "guardian failed" in str(exc)
        (leaf/"cgroup.kill").write_text("1","ascii")
        await_empty_leaf(leaf)
        leaf.rmdir()


@pytest.mark.skipif(sys.platform!="linux",reason="Real Linux kernel only")
def test_linux_hard_host_exit_guardian_reconciles_descendants(tmp_path):
    native_linux_delegation()
    path=spool(tmp_path)
    host_crash(path)
    wait_ready(path/"descendant.ready")
    leaf=Path((path/"leaf.path").read_text("utf8"))
    await_empty_leaf(leaf)
    # This is an OS observation by a *different* host after original death;
    # it does not fabricate a reconstructed one-use kill authorization.
    end=time.monotonic()+10
    while leaf.exists() and time.monotonic()<end:
        time.sleep(.05)
    assert not leaf.exists(), "Independent kernel guardian failed restart cleanup"
    verify_restarted_host_has_only_unapproved_original(path)


@pytest.mark.skipif(sys.platform!="linux",reason="Real Linux kernel only")
def test_linux_without_delegation_has_no_uncontained_fallback(tmp_path):
    with (tmp_path/"out").open("wb") as out:
        from unittest.mock import patch
        with patch("backend.nvp_worker_linux_cgroup.current_delegated_parent",
                   side_effect=RuntimeError("No real delegated root")):
            with pytest.raises(RuntimeError,match="No real delegated root"):
                launch_contained([sys.executable,str(FIXTURE),"worker",str(tmp_path)],
                    cwd=tmp_path,stdout=out,stderr=out,memory_mb=512,
                    linux_cgroup_tree_required=True,linux_write_spool=None)
