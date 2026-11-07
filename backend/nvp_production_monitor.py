"""WO4-LF01 trusted native NVP UI reconnect view for production jobs.

No IPC listener and no browser-write actions here. The desktop host must
authenticate a project-specific read. Original media paths and worker tokens
are deliberately excluded from the response; the same method can be used
after NVP is unlocked/reopened while the standalone supervisor keeps running.
"""
from __future__ import annotations
from copy import deepcopy

from backend.nvp_film_index import FilmIndex
from backend.nvp_production_journal import ProductionJournal

FORMAT="nvp.wo4.production_monitor.v1"


class ProductionMonitor:
    def __init__(self, index:FilmIndex, journal:ProductionJournal,
                 *, authorize_project_read):
        if (not isinstance(index,FilmIndex) or
                not isinstance(journal,ProductionJournal) or
                not callable(authorize_project_read)):
            raise PermissionError("Trusted native project monitor required")
        self.index=index
        self.journal=journal
        self.authorize=authorize_project_read

    def _project(self, project_id):
        # Studio's native project lookup is the actual scope boundary;
        # accepting a user-supplied string alone is not authentication.
        try:
            self.index.studio.get_project(project_id)
        except (KeyError,ValueError,TypeError) as exc:
            raise PermissionError("Project production monitor access denied") from exc
        scope={"operation":"nvp.supervisor.read_project_job_status.v1",
               "project_id":project_id}
        if self.authorize(deepcopy(scope)) is not True:
            raise PermissionError("Project production monitor access denied")

    def catalog(self, project_id):
        self._project(project_id)
        jobs=[]
        for item in self.journal.list_jobs(project_id):
            snapshot=self.journal.status(item["job_id"])
            if snapshot["project_id"]!=project_id:
                raise PermissionError("Production journal changed project scope")
            jobs.append({
                "job_id":snapshot["job_id"],
                "assembly_id":snapshot["assembly_id"],
                "assembly_revision":snapshot["assembly_revision"],
                "assembly_sha256":snapshot["assembly_sha256"],
                "manifest_sha256":snapshot["manifest_sha256"],
                "task_kind":snapshot["task_kind"],
                "status":snapshot["state"],
                "verified_segments":snapshot["verified_segments"],
                "total_segments":snapshot["total_segments"],
                "cancel_requested":snapshot["cancel_requested"],
                "updated_at":snapshot["updated_at"],
                "production_dcp_accepted":False
            })
        return {"format":FORMAT,"status":"READ_ONLY",
                "project_id":project_id,"jobs":jobs,
                "source_paths_exposed":False,
                "can_cancel_job":False,
                "can_override_worker":False}

    def inspect(self, project_id, job_id):
        self._project(project_id)
        snapshot=self.journal.status(job_id)
        if snapshot["project_id"]!=project_id:
            raise PermissionError("Job does not belong to approved project")
        return {
            "format":FORMAT,
            "status":"READ_ONLY",
            "job_id":job_id,"project_id":project_id,
            "assembly_sha256":snapshot["assembly_sha256"],
            "manifest_sha256":snapshot["manifest_sha256"],
            "job_state":snapshot["state"],
            "task_kind":snapshot["task_kind"],
            "verified_segments":snapshot["verified_segments"],
            "total_segments":snapshot["total_segments"],
            "segments":[{
                "position":s["position"],
                "start_tick":s["start_tick"],
                "end_tick":s["end_tick"],
                "state":s["state"],
                "verified_bytes":s["verified_bytes"],
                "verified_sha256":s["verified_sha256"]
            } for s in snapshot["segments"]],
            "production_dcp_accepted":False,
            "can_cancel_job":False,
            "source_paths_exposed":False,
        }
