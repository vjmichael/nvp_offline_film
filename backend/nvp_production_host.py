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
from backend import nvp_audio_recovery as audio_recovery
from backend import nvp_feature_sections as feature_sections
from backend import nvp_feature_delivery_groups as feature_groups
from backend.nvp_wo4_longfilm_audio import (master_partitioned_pcm24,
    verify_partitioned_pcm24,reopen_prepared_pcm24)
from backend.nvp_temporal_ledger import TICKS_PER_SECOND
from backend.nvp_production_catalog_pages import page as catalog_page
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

    def submit_verification_pages(self,pid,*,creator_event,assembly_id,assembly_revision,
                                  assembly_sha256,page_factory):
        """Trusted host only: finite original media verification, not rendering."""
        return self.journal.submit_paged(self._project(pid),pid,assembly_id=assembly_id,
            assembly_revision=assembly_revision,assembly_sha256=assembly_sha256,
            page_factory=page_factory,approve=self._approval(creator_event,pid))

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

    def attach_partitioned_delivery(self,pid,job_id,*,creator_event,partitioned_receipt,
                                    reel_index,output_root,title,cancelled=lambda:False):
        """Native host only: reuse the original delivery transaction and consent."""
        index=self._project(pid)
        self.journal.status_page(job_id,limit=1,expected_project_id=pid)
        return self.journal.attach_delivery(index,job_id,sound_candidate=None,
            partitioned_receipt=partitioned_receipt,partitioned_reel_index=reel_index,
            output_root=output_root,title=title,approve=self._approval(creator_event,pid),
            cancelled=cancelled)

    def master_audio_set(self,pid,*,creator_event,source_take_id,source_take_revision,
                         source_path,source_sha256,cinema_frames,channel_layout,output_root,
                         max_reel_frames=7200,gain_numerator=1,gain_denominator=1,
                         cancelled=lambda:False):
        """Trusted host only. Original singleton lease, explicit audio approval."""
        with self.service_session():
            index=self._project(pid)
            take=index.read_revision(pid,source_take_id,source_take_revision)
            if take["kind"]!="take" or take["data"].get("frozen") is not True:
                raise PermissionError("Exact frozen source Take required")
            if type(cinema_frames) is not int or cinema_frames<=0 or cinema_frames*(TICKS_PER_SECOND//24)>take["data"]["duration_tick"]:
                raise PermissionError("Audio clock exceeds source Take")
            creator_approve=self._approval(creator_event,pid)
            def approve(scope):
                if index.read_revision(pid,source_take_id,source_take_revision)["document_sha256"]!=take["document_sha256"]:
                    raise PermissionError("Frozen Take changed")
                return creator_approve({**scope,"source_take_id":source_take_id,
                                        "source_take_revision":source_take_revision})
            return audio_recovery.run(self.journal,pid,str(Path(index.studio.db_path).resolve(strict=True)),
                approve=approve,produce=master_partitioned_pcm24,verify=verify_partitioned_pcm24,source_ref={"source_take_id":source_take_id,"source_take_revision":source_take_revision},
                source_path=source_path,source_sha256=source_sha256,original_take_sha256=take["document_sha256"],
                cinema_frames=cinema_frames,channel_layout=channel_layout,output_root=output_root,
                max_reel_frames=max_reel_frames,gain_numerator=gain_numerator,gain_denominator=gain_denominator,
                cancelled=cancelled)

    def adopt_audio_set(self,pid,audio_id,*,creator_event,cancelled=lambda:False):
        """No automatic replay; only a separately approved prepared publication."""
        with self.service_session():
            index=self._project(pid)
            return audio_recovery.adopt(self.journal,audio_id,pid,
                str(Path(index.studio.db_path).resolve(strict=True)),approve=self._approval(creator_event,pid),
                reopen=lambda plan,sha,**kw:self._reopen_audio_plan(index,pid,plan,sha,**kw),
                verify=verify_partitioned_pcm24,cancelled=cancelled)

    @staticmethod
    def _reopen_audio_plan(index,pid,plan,sha,**kw):
        take=index.read_revision(pid,plan["source_take_id"],plan["source_take_revision"])
        if (take["kind"]!="take" or take["data"].get("frozen") is not True or
                take["document_sha256"]!=plan["original_take_sha256"]):
            raise PermissionError("Original audio Take changed")
        return reopen_prepared_pcm24(plan,sha,**kw)

    def audio_recovery_page(self,pid,*,creator_event,after=None,limit=32):
        index=self._project(pid)
        if not self._approval(creator_event,pid)({"operation":"nvp.wo4.read_audio_recovery.v1"}):
            raise PermissionError("Audio recovery view denied")
        result=audio_recovery.page(self.journal,pid,str(Path(index.studio.db_path).resolve(strict=True)),after=after,limit=limit)
        self._project(pid)
        return result

    def attach_registered_audio(self,pid,job_id,audio_id,*,creator_event,reel_index,output_root,title,cancelled=lambda:False):
        index=self._project(pid)
        candidate=audio_recovery.verified_receipt(self.journal,audio_id,pid,
            str(Path(index.studio.db_path).resolve(strict=True)),verify=verify_partitioned_pcm24,cancelled=cancelled)
        return self.attach_partitioned_delivery(pid,job_id,creator_event=creator_event,
            partitioned_receipt=candidate,reel_index=reel_index,output_root=output_root,title=title,cancelled=cancelled)

    def register_feature_delivery_group(self,pid,object_id,source,selections,*,creator_event):
        """Record ordered verified native section packages, not a single new DCP."""
        from backend.nvp_wo5_original_feature import inspect_indexed_feature
        with self.service_session():
            index=self._project(pid)
            def leaf(feature_id,source_ref):
                f=self.journal.feature(feature_id)
                if (f["project_id"]!=pid or f["assembly_id"]!=source_ref["object_id"] or
                        f["assembly_revision"]!=source_ref["revision"] or f["assembly_sha256"]!=source_ref["sha256"]):
                    raise PermissionError("Native section is outside approved source group")
                verified=inspect_indexed_feature(index,self.journal,pid,feature_id)
                again=self.journal.feature(feature_id)
                if again!=f or verified["filmindex_feature_receipt_sha256"]!=f["filmindex_sha256"]:
                    raise PermissionError("Indexed native section changed")
                return {"feature_id":feature_id,"source_ref":source_ref,"frame_count":verified["frame_count"],
                    "profile":f["profile"],"manifest_sha256":f["manifest_sha256"],
                    "receipt_ref":{"object_id":"WO4FEATURE_"+verified["cpl_uuid"].replace("-",""),
                        "revision":1,"sha256":f["filmindex_sha256"]},"production_dcp_accepted":False}
            return feature_groups.register(index,pid,object_id,source,selections,frame_ticks=TICKS_PER_SECOND//24,
                verify_leaf=leaf,approve=self._approval(creator_event,pid))

    def register_feature_sections(self,pid,object_id,children,*,creator_event):
        return feature_sections.register(self._project(pid),pid,object_id,children,
            frame_ticks=TICKS_PER_SECOND//24,approve=self._approval(creator_event,pid))

    def register_feature_export_assembly(self,pid,assembly_id,source,*,creator_event,profile,cancelled=lambda:False):
        """Explicit source composition only; original submit_feature still requires delivery approval."""
        from backend.nvp_film_index import MAX_DEPENDENCIES
        from backend.nvp_wo4_resource_budget import MAX_REELS
        with self.service_session():
            index=self._project(pid)
            return feature_sections.register_finite_export(index,pid,assembly_id,source,
                frame_ticks=TICKS_PER_SECOND//24,profile=profile,reel_budget=min(MAX_REELS,MAX_DEPENDENCIES-1),
                read_reel=lambda uid:feature_sections.native_reel_metadata(self.journal,pid,uid),
                approve=self._approval(creator_event,pid),cancelled=cancelled)

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
        result=self.reconnect_read_only_page(pid,creator_event=creator_event,limit=64)
        if result["jobs_next_cursor"] is not None or result["features_next_cursor"] is not None:
            raise ValueError("Production catalog requires paged reconnect")
        return result

    def reconnect_read_only_page(self,pid,*,creator_event,jobs_after=None,
                                 features_after=None,limit=32):
        """Separate bounded cursors. No media loads or service ownership."""
        index=self._project(pid)
        approve=self._approval(creator_event,pid)
        result=ProductionMonitor(index,self.journal,authorize_project_read=approve).catalog_page(
            pid,after=jobs_after,limit=limit)
        with self.journal._read() as db:
            if not db.in_transaction:db.execute("BEGIN")
            features,cursor=catalog_page(db,pid,kind="features",after=features_after,
                limit=limit,project_db=str(Path(index.studio.db_path).resolve(strict=True)))
        self._project(pid)
        result["features"]=features
        result["features_next_cursor"]=cursor
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
            audio_recovery.reconcile(self.journal)
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
