"""PLAN-03 native OS process-tree custody for actual filming journal adapter.

Runs under delegated systemd cgroup-v2 on Linux and real Windows Job Objects.
A detached grandchild changes a physical heartbeat file; the adapter must
stop it before the original filming journal is marked INTERRUPTED. No OS
approval is synthesized by this test: test consent is fixture-only.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_filming_publication_journal import FilmingPublicationJournal
from backend.nvp_filming_native_supervisor import NativeFilmingTreeWorker, sha_file

REPORT="nvp.plan03.actual_filming_journal_tree_custody.v1"


def wait_for_file(path: Path, limit=15):
    until=time.monotonic()+limit
    while time.monotonic()<until:
        if path.is_file() and path.stat().st_size>0:
            return
        time.sleep(.05)
    raise RuntimeError("Detached worker failed to demonstrate actual heartbeat")


def run(report_path):
    report_path=Path(report_path)
    if not report_path.is_absolute() or report_path.exists() or report_path.is_symlink():
        raise ValueError("New absolute native witness path required")
    if sys.platform=="linux":
        from backend.nvp_worker_linux_cgroup import current_delegated_parent
        current_delegated_parent()  # no pretend cgroup files
    elif os.name!="nt":
        raise RuntimeError("Unsupported OS containment test host")

    with tempfile.TemporaryDirectory(prefix="nvp-plan03-kernel-") as scratch:
        root=Path(scratch)
        studio=Studio(root/"nvp_studio.sqlite3")
        p=studio.create_project("Tree custody test","A real original Take must never be invented")["id"]
        idx=FilmIndex(studio)
        journal=FilmingPublicationJournal(idx)
        journal.begin(p,"filming_take","filming_events",["filming_pcm"])
        original=journal.unresolved(p)
        if len(original)!=1 or original[0]["state"]!="PREPARING":
            raise RuntimeError("No real PREPARING filming publication recorded")
        write=root/"worker"
        write.mkdir()
        grandchild=write/"grandchild.py"
        grandchild.write_text(
            "import os,sys,time\n"
            "from pathlib import Path\n"
            "p=Path(sys.argv[1])\n"
            "for _ in range(10000):\n"
            " with p.open('ab') as f:\n"
            "  f.write(b'x');f.flush();os.fsync(f.fileno())\n"
            " time.sleep(.05)\n",encoding="utf8")
        parent=write/"parent.py"
        parent.write_text(
            "import os,sys,subprocess,time\n"
            "from pathlib import Path\n"
            "p=Path(sys.argv[1]);g=Path(sys.argv[2])\n"
            "flags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0\n"
            "child=subprocess.Popen([sys.executable,str(g),str(p)],"
            "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,"
            "stderr=subprocess.DEVNULL,close_fds=True,"
            "start_new_session=os.name!='nt',creationflags=flags)\n"
            "time.sleep(60)\n",encoding="utf8")
        approved=[]
        def approval(scope):
            approved.append(scope)
            return True # strictly TEST-ONLY stand-in, not OS human evidence
        host=NativeFilmingTreeWorker(
            journal=journal,workspace=write,ask_native=approval,
            memory_mb=1024)
        admission=host.launch(
            p,"filming_take",executable=Path(sys.executable),
            executable_sha256=sha_file(Path(sys.executable)),
            args=(str(parent),str(write/"heartbeat"),str(grandchild)))
        heartbeat=write/"heartbeat"
        wait_for_file(heartbeat)
        before=heartbeat.stat().st_size
        if before<1:
            raise RuntimeError("Real OS worker never produced test data")
        receipt=host.stop_and_interrupt()
        if receipt["state"]!="INTERRUPTED" or not receipt["worker_process_tree_custody_verified"]:
            raise RuntimeError("Journal was not interrupted after real kernel containment")
        after=heartbeat.read_bytes()
        time.sleep(.75)
        if heartbeat.read_bytes()!=after:
            raise RuntimeError("Detached grandchild survived filming worker tree custody")
        if journal.unresolved(p)[0]["state"]!="INTERRUPTED":
            raise RuntimeError("Original filming publication journal not durably interrupted")
        try:
            idx.read_revision(p,"filming_take",1)
        except KeyError:
            pass
        else:
            raise RuntimeError("Interrupted worker invented immutable original Take")
        reloaded=NativeFilmingTreeWorker(
            journal=FilmingPublicationJournal(FilmIndex(Studio(root/"nvp_studio.sqlite3"))),
            workspace=write,ask_native=lambda scope: False,memory_mb=1024)
        recovery=reloaded.inventory_after_restart(p)
        if recovery["automatic_replay_authorized"] or recovery["original_take_published"]:
            raise RuntimeError("Restart should not authorize silent publication/replay")

    report={
        "format": REPORT,
        "status": "ACTUAL_NATIVE_FILMING_JOURNAL_TREE_STOP_AND_RESTART_PASS",
        "kernel": sys.platform,
        "scope": receipt["scope"],
        "detached_grandchild_heartbeat_stopped_sha256": hashlib.sha256(after).hexdigest(),
        "journal_transition": receipt["state"],
        "original_source_modified": False,
        "automatic_replay": False,
        "human_approval_physically_witnessed": False,
        "fixture_only_review": len(approved)==1,
        "actual_microphone_recorded": False,
        "publication_authorized": False
    }
    report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(report,indent=2,sort_keys=True),encoding="utf8")
    print("NVP_PLAN03_FILMING_NATIVE_TREE_CUSTODY_PASS="+sys.platform,flush=True)
    return report


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--report",required=True)
    args=parser.parse_args()
    run(args.report)
