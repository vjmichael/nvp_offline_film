"""WO4 native production host adapter.

For a trusted, already admitted native service only. Neither this module nor
the journal opens IPC, accepts user-supplied commands, or launches a detached
supervisor. Existing installed host/SCM must supply the project resolver,
reviewed codec factory and creator authority. Closing a UI read view does not
request cancellation. Releasing a service lease at a checkpoint is not a
worker-termination or installed-service acceptance claim.
"""
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
from backend.nvp_film_index import FilmIndex
from backend.nvp_production_journal import SingletonSupervisor
from backend.nvp_production_supervisor import ProductionSupervisor
from backend.nvp_production_monitor import ProductionMonitor
from backend.nvp_wo4_feature_journal import FeatureJournal
from backend.nvp_wo5_review_storage import ReadOnlyProductionStorage
from backend.nvp_wo4_pcm_stream import _protected_path
from backend.nvp_w1g_release_gate import inspect_original_process_journals


class ProductionReviewJournal(ReadOnlyProductionStorage, FeatureJournal):
    """Existing EFS journal view; no constructor migrations or service lease."""
    def __init__(self, state_root):
        ReadOnlyProductionStorage.__init__(self,state_root,verify_path=_protected_path)


class NativeProductionHost:
    @staticmethod
    def open_review_journal(state_root, index):
        if not isinstance(index,FilmIndex):
            raise PermissionError("Trusted native FilmIndex required")
        _protected_path(Path(index.studio.db_path))
        return ProductionReviewJournal(state_root)

    def __init__(self,state_root,*,resolve_project,codec_factory,verify_creator_action):
        if not all(callable(x) for x in (resolve_project,codec_factory,verify_creator_action)):
            raise PermissionError("Trusted native service project and creator authority required")
        self.journal=FeatureJournal(state_root)
        self.resolve_project=resolve_project
        self.codec_factory=codec_factory
        self.verify_creator_action=verify_creator_action

    def _project(self,pid):
        index=self.resolve_project(pid)
        if not isinstance(index,FilmIndex):
            raise PermissionError("Project is not admitted by native host")
        index.studio.get_project(pid)
        _protected_path(Path(index.studio.db_path))
        return index

    def _approval(self,event,pid):
        if event is None:
            raise PermissionError("Actual creator action required")
        def approve(scope):
            if scope.get("project_id",pid)!=pid:
                raise PermissionError("Creator action project scope differs")
            return self.verify_creator_action(event,{**deepcopy(scope),"project_id":pid}) is True
        return approve

    def submit_reel(self,pid,*,creator_event,mastering_decision_id,frame_sources):
        index=self._project(pid)
        codecs=self.codec_factory(pid,lambda:False)
        if type(codecs) not in (tuple,list) or len(codecs)!=3:
            raise PermissionError("Trusted reviewed codec roster required")
        return self.journal.submit_reel(index,pid,mastering_decision_id=mastering_decision_id,
            frame_sources=frame_sources,openjpeg=codecs[0],wrapper=codecs[1],info=codecs[2],
            approve=self._approval(creator_event,pid))

    def attach_delivery(self,pid,job_id,*,creator_event,sound_candidate,output_root,title):
        index=self._project(pid)
        if self.journal.status(job_id)["project_id"]!=pid:
            raise PermissionError("Delivery outside admitted project")
        return self.journal.attach_delivery(index,job_id,sound_candidate=sound_candidate,
            output_root=output_root,title=title,approve=self._approval(creator_event,pid))

    def submit_feature(self,pid,*,creator_event,assembly_id,assembly_revision,ordered_job_ids,title,profile,output_root):
        return self.journal.submit_feature(self._project(pid),pid,assembly_id=assembly_id,
            assembly_revision=assembly_revision,ordered_job_ids=ordered_job_ids,title=title,
            profile=profile,output_root=output_root,approve=self._approval(creator_event,pid))

    def request_delivery_cancel(self,pid,job_id,*,creator_event):
        self._project(pid)
        if self.journal.status(job_id)["project_id"]!=pid:
            raise PermissionError("Cancellation outside admitted project")
        return self.journal.request_delivery_cancel(job_id,self._approval(creator_event,pid))

    def request_reel_cancel(self,pid,job_id,*,creator_event):
        self._project(pid)
        if self.journal.status(job_id)["project_id"]!=pid:
            raise PermissionError("Cancellation outside admitted project")
        return self.journal.request_cancel(job_id,self._approval(creator_event,pid))

    def request_feature_cancel(self,pid,feature_id,*,creator_event):
        self._project(pid)
        if self.journal.feature(feature_id)["project_id"]!=pid:
            raise PermissionError("Cancellation outside admitted project")
        return self.journal.request_feature_cancel(feature_id,self._approval(creator_event,pid))

    def reconnect_read_only(self,pid,*,creator_event):
        index=self._project(pid)
        approve=self._approval(creator_event,pid)
        result=ProductionMonitor(index,self.journal,authorize_project_read=approve).catalog(pid)
        # This is an authorized read-only view, not service ownership.
        with self.journal._read() as db:
            rows=db.execute("""SELECT feature_id,state,assembly_sha256,manifest_sha256,
               cancel_requested,updated_at FROM production_features WHERE project_id=?
               ORDER BY created_at,feature_id""",(pid,)).fetchall()
        result["features"]=[dict(row) for row in rows]
        result["read_only"]=True
        result["installed_service_verified"]=False
        return result

    @contextmanager
    def service_session(self):
        # Single lease for recovery and ALL work. Must never recover over an
        # unresolved native process tree, even after the supervisor dies.
        with SingletonSupervisor(self.journal.root):
            inspect_original_process_journals()
            self.journal.reconcile_after_restart()
            self.journal.cinema_reconcile()
            self.journal.delivery_reconcile()
            self.journal.reconcile_features()
            runner=ProductionSupervisor(self.journal,resolve_project=self._project,
                                        codec_factory=self.codec_factory)
            try:
                yield runner
            finally:
                inspect_original_process_journals()

    def adopt_orphan_delivery(self,pid,job_id,*,creator_event):
        self._project(pid)
        if self.journal.status(job_id)["project_id"]!=pid:
            raise PermissionError("Recovery outside admitted project")
        with self.service_session():
            return self.journal.approve_orphan_dcp_adoption(job_id,self._approval(creator_event,pid))

    def adopt_orphan_feature(self,pid,feature_id,*,creator_event):
        self._project(pid)
        if self.journal.feature(feature_id)["project_id"]!=pid:
            raise PermissionError("Recovery outside admitted project")
        with self.service_session():
            return self.journal.approve_orphan_feature_adoption(feature_id,self._approval(creator_event,pid))
