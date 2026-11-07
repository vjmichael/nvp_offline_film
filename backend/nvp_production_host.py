"""NVP native host adapter for the independent durable Production Supervisor.

This is the trusted Lu/NVP workspace HOST side, not a browser or HTTP API.
The UI may be closed/reopened or manually locked without stopping the native
supervisor. A packaged release must supply a protected interpreter/runtime
and an authenticated IPC implementation; this module does not invent one.
"""
from __future__ import annotations

from pathlib import Path
import os
import signal
import subprocess
import sys
import time

from backend.nvp_production_supervisor import (
    SingletonSupervisor,AnotherSupervisorRunning)
from backend.nvp_production_monitor import ProductionMonitor
from backend.nvp_wo4_feature_journal import FeatureJournal
from backend.nvp_film_index import FilmIndex

FORMAT="nvp.wo4.native_production_host.v1"

class NativeProductionHost:
    def __init__(self,state_root,*,runtime_executable=None,runtime_root=None):
        self.journal=FeatureJournal(state_root)
        self.root=self.journal.root
        self.executable=Path(runtime_executable or sys.executable)
        self.runtime_root=Path(runtime_root or Path(__file__).resolve().parents[1])
        if (not self.executable.is_absolute() or
                not self.executable.is_file() or self.executable.is_symlink() or
                not self.runtime_root.is_absolute() or
                not self.runtime_root.is_dir() or
                self.runtime_root.is_symlink()):
            raise PermissionError("Protected installed native runtime required")
        self.executable=self.executable.resolve(strict=True)
        self.runtime_root=self.runtime_root.resolve(strict=True)
        self.process=None

    def is_running(self):
        try:
            with SingletonSupervisor(self.root):
                return False
        except AnotherSupervisorRunning:
            return True

    def ensure_running(self,*,startup_seconds=10):
        if type(startup_seconds) not in (float,int) or not 1<=startup_seconds<=30:
            raise ValueError("Bounded host startup deadline required")
        if self.is_running():
            return {"format":FORMAT,"status":"ALREADY_RUNNING",
                    "supervisor_running":True,"gui_process_owns_worker":False}
        flags=0
        if sys.platform=="win32":
            # Break away rather than tie export to Lu/NVP's window Job Object.
            # If the parent job disallows breakaway, fail closed; a true
            # installed service/helper broker is still required for release.
            flags=(subprocess.CREATE_NEW_PROCESS_GROUP|0x00000008|
                   0x01000000) # DETACHED_PROCESS | CREATE_BREAKAWAY_FROM_JOB
        with open(os.devnull,"rb") as stdin, open(os.devnull,"wb") as logs:
            self.process=subprocess.Popen(
                [str(self.executable),"-m","backend.nvp_production_supervisor",
                 "serve","--state-root",str(self.root)],
                cwd=str(self.runtime_root),
                stdin=stdin,stdout=logs,stderr=logs,
                shell=False,close_fds=True,
                start_new_session=(sys.platform!="win32"),
                creationflags=flags)
        deadline=time.monotonic()+startup_seconds
        while time.monotonic()<deadline:
            if self.is_running():
                return {"format":FORMAT,"status":"RUNNING",
                        "supervisor_running":True,
                        "pid":self.process.pid,
                        "gui_process_owns_worker":False}
            if self.process.poll() is not None:
                # If a competing supervisor acquired the singleton first,
                # its process exit is harmless and still means running.
                if self.is_running():
                    return {"format":FORMAT,"status":"ALREADY_RUNNING",
                            "supervisor_running":True,
                            "gui_process_owns_worker":False}
                raise RuntimeError("Standalone native supervisor exited before admission")
            time.sleep(0.05)
        if not self.is_running():
            if self.process.poll() is None:
                self.process.terminate()
            raise TimeoutError("Native supervisor did not acquire durable singleton")
        return {"format":FORMAT,"status":"RUNNING",
                "supervisor_running":True,
                "gui_process_owns_worker":False}

    def reconnect_read_only(self,index:FilmIndex,project_id,*,authorize):
        """Read-only project-scoped snapshot, no exposure of worker controls."""
        if not isinstance(index,FilmIndex) or not callable(authorize):
            raise PermissionError("Trusted native FilmIndex and project permission")
        monitor=ProductionMonitor(index,self.journal,
                                  authorize_project_read=authorize)
        result=monitor.catalog(project_id)
        feature=[]
        with self.journal._read() as db:
            rows=[dict(x) for x in db.execute("""SELECT feature_id,project_id,
                assembly_id,assembly_revision,state,updated_at FROM
                production_features WHERE project_id=? ORDER BY created_at""",
                (project_id,))]
        for row in rows:
            feature.append({"feature_id":row["feature_id"],
                            "assembly_id":row["assembly_id"],
                            "assembly_revision":row["assembly_revision"],
                            "state":row["state"],"updated_at":row["updated_at"],
                            "can_cancel":False,
                            "production_dcp_accepted":False})
        return {**result,"features":feature,
                "supervisor_running":self.is_running(),
                "read_only":True,"no_source_paths_exposed":True}

    def request_clean_shutdown(self,*,authorize,known_pid=None):
        """Explicit host admin action, never the NVP manual window lock.

        SIGTERM only stops the supervisor service; it does not authorize
        cancellation/deletion of accepted production jobs. Jobs reconcile on
        the next launch. The installed host requires stronger PID identity
        validation before releasing this action to users.
        """
        if not callable(authorize):
            raise PermissionError("Native host administrative grant required")
        scope={"operation":"nvp.supervisor.stop_process_not_jobs.v1",
               "state_root":str(self.root)}
        if authorize(dict(scope)) is not True:
            return {"status":"DENIED"}
        if self.process is None or self.process.poll() is not None:
            raise PermissionError("Only this host's exact owned process can be shut down")
        if known_pid is not None and known_pid!=self.process.pid:
            raise PermissionError("Mismatched current process identity")
        self.process.terminate()
        self.process.wait(timeout=8)
        return {"status":"STOPPED_JOBS_DURABLE",
                "job_cancellation_requested":False}
