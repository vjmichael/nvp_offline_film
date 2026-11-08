"""WO6 creator-facing desktop operations over NVP's EXISTING trusted WebView2.

Every mutation starts from an exact typed source impact preview and requires
TWO separate, current OS confirmation dialogs: the director's creative
decision and first-party native worker execution. Browser/model data never
issues an authorization token, filesystem path, executable name or task
owner; the native host supplies all of those. On restart prior ephemeral
grants are lost, and queued actions cannot auto-run.
"""
from __future__ import annotations

import getpass
from hashlib import sha256
import json
from pathlib import Path
import os
import secrets
import threading
from queue import Queue, Empty, Full
import time

from backend.nvp_ai_read_host import TrustedReadScope
from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_film_index import _id, _require_pid
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_wo5_desktop_bridge import TrustedDesktopWO5Bridge
from backend.nvp_wo6_impact_preview import preview_source_impact
from backend.nvp_wo6_native_take_action import NativeTakeActionHost
from backend.nvp_wo6_native_shot_action import NativeShotActionHost, ACTION_KINDS
from backend.nvp_wo6_scene_context import assemble_film_crew_context
from backend.nvp_wo6_native_data_action import NativeFilmDecisionHost
from backend.nvp_wo6_recovery import WO6DurableRecovery
from backend.nvp_wo6_director_model_proposal import (
    director_model_suggestion, MAX_CREATIVE_CHARS)
from backend.nvp_model_service import discover_models
from backend.nvp_wo6_verified_local_model import verified_writer_for

FORMAT="nvp.wo6.director_desktop_native_consent.v1"
MAX_LIST=64
MAX_APPROVAL_TEXT=4096
MAX_DISPATCH_QUEUE=64
MAX_MODEL_PROPOSALS=4  # Not native workers or persistent approvals.


class TrustedDesktopWO6Bridge(TrustedDesktopWO5Bridge):
    """First-party Desktop IPC only, not NVP FastAPI or model execute catalog."""

    def __init__(self,index,*,origin,director_writer_factory=None,**kwargs):
        super().__init__(index,origin=origin,**kwargs)
        home=Path(os.environ.get("NVP_HOME",str(
            Path(index.studio.db_path).parent)))
        if not home.is_absolute() or home.is_symlink():
            raise PermissionError("WO6 runtime must be rooted in the native home")
        self._wo6_root=home.resolve()/".creator-native-actions"
        if self._wo6_root.is_symlink():
            raise PermissionError("Native creator action runtime is a symlink")
        self._wo6_root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self._wo6_actor="local_"+sha256(getpass.getuser().encode(
            "utf8","replace")).hexdigest()[:32]
        self._wo6_decisions={}
        self._wo6_native_grants={}
        self._wo6_ledger=None
        self._wo6_take=None
        self._wo6_shot=None
        self._wo6_data=None
        self._wo6_recovery=None
        self._wo6_dispatch_lock=threading.RLock()
        self._wo6_dispatch_queues={}
        self._wo6_dispatch_faults={}
        self._wo6_dispatch_deferrals={}
        self._wo6_closed=False
        # Optional host-owned test injection; browser/LLM JSON never
        # receives or supplies the provider, tool path, URL or callback.
        if director_writer_factory is not None and not callable(director_writer_factory):
            raise TypeError("Native model factory must be host-injected")
        self._wo6_director_writer_factory=director_writer_factory or verified_writer_for
        self._wo6_model_lock=threading.RLock()
        self._wo6_model_proposals={}

    def _wo6_host(self):
        self._native_window()
        if self._wo6_ledger is None:
            ledger=TaskLedger(self._wo6_root/"ledger")
            self._wo6_ledger=ledger
            self._wo6_recovery=WO6DurableRecovery(ledger)
            self._wo6_take=NativeTakeActionHost(
                self.index,ledger,self._wo6_root/"take",
                confirm_creator=self._wo6_confirm_creative,
                authorize_native=self._wo6_confirm_native)
            self._wo6_shot=NativeShotActionHost(
                self.index,ledger,self._wo6_root/"shot",
                confirm_creator=self._wo6_confirm_creative,
                authorize_native=self._wo6_confirm_native)
            self._wo6_data=NativeFilmDecisionHost(
                self.index,ledger,self._wo6_root/"data",
                confirm_creator=self._wo6_confirm_creative,
                authorize_native=self._wo6_confirm_native)
        return self._wo6_ledger

    def _wo6_scope(self, pid):
        self._wo5_project(pid)
        return TrustedReadScope(
            self._wo6_actor,pid,"desktop_wo6_"+secrets.token_hex(12))

    def _wo6_confirm_creative(self, decision_id, creative):
        self._native_window()
        if type(creative) is not dict or type(decision_id) is not str:
            return False
        raw=canonical_bytes(creative)
        if len(raw)>MAX_APPROVAL_TEXT:
            return False
        digest=sha256(raw).hexdigest()
        key=(decision_id,digest)
        now=time.time()
        if self._wo6_decisions.get(key,0)>now:
            return True
        approved=self._native_window().create_confirmation_dialog(
            "NVP — Director approval required",
            "Review the exact native SOURCE-DATA operation:\n"+
            json.dumps(creative,sort_keys=True,indent=2)+
            "\n\nThis does NOT deliver or approve a finished film.\n"
            "Approve this specific source revision/change?")
        if approved is True:
            self._wo6_decisions[key]=now+1200
            return True
        return False

    def _wo6_confirm_native(self, scope, spec_sha, doc):
        self._native_window()
        if (not isinstance(scope,TrustedReadScope) or
                scope.actor_id!=self._wo6_actor or
                doc.get("project_id")!=scope.project_id or
                type(spec_sha) is not str or len(spec_sha)!=64):
            return False
        now=time.time()
        if self._wo6_native_grants.get(spec_sha,0)>now:
            return True
        approved=self._native_window().create_confirmation_dialog(
            "NVP — Separate native worker permission",
            "This is a SECOND confirmation for native first-party tool execution.\n"
            "No arbitrary executable, network operation or original Take overwrite.\n"
            "Project: "+scope.project_id+"\n"
            "Operation: "+str(doc.get("operation"))+"\n"
            "Exact sealed job SHA256: "+spec_sha+"\n"
            "Release and cinematic approval: NOT GRANTED.\n"
            "Allow this exact contained native operation?")
        if approved is True:
            self._wo6_native_grants[spec_sha]=now+1200
            return True
        return False

    def wo6_local_models(self,project_id):
        """Explicit user discovery of an existing loopback-only model service."""
        self._wo5_project(project_id)
        result=discover_models()
        return {**result, "model_execute_authorized":False,
                "native_source_write_authorized":False,
                "remote_model_endpoint_supported":False}

    def _wo6_run_director_model(self,request_id,request):
        try:
            provider=self._wo6_director_writer_factory(request["model_id"])
            proposal=director_model_suggestion(
                self.index,request["project_id"],
                request["take_id"],request["take_sha256"],
                request["film_tick"],request["direction"],
                request["model_id"],provider)
        except Exception:
            # Avoid leaking provider IP/paths, prompts and private NVP
            # source descriptions to the browser on model failure.
            with self._wo6_model_lock:
                slot=self._wo6_model_proposals.get(request_id)
                if slot is not None and not self._wo6_closed:
                    slot.update(state="FAILED",reason="Local model or verified source unavailable")
            return
        with self._wo6_model_lock:
            slot=self._wo6_model_proposals.get(request_id)
            if slot is not None and not self._wo6_closed:
                slot.update(state="READY_FOR_HUMAN_REVIEW",proposal=proposal)

    def wo6_suggest_from_local_model(self,request):
        """Nonblocking read-only AI proposal, not a WO6 worker admission."""
        self._wo6_require(request,{
            "project_id","take_id","take_sha256",
            "film_tick","direction","model_id"})
        if (type(request["direction"]) is not str or
                not 1<=len(request["direction"].strip())<=MAX_CREATIVE_CHARS or
                type(request["film_tick"]) is not str or
                len(request["film_tick"])>16 or
                type(request["model_id"]) is not str or
                not 1<=len(request["model_id"])<=256 or
                type(request["take_id"]) is not str or
                len(request["take_id"])>80):
            raise ValueError("Invalid bounded director suggestion request")
        # Check immutable source identity before creating the local generation.
        original=self.index.read_revision(
            request["project_id"],request["take_id"],1)
        if (original["kind"]!="take" or original["data"].get("frozen") is not True or
                original["document_sha256"]!=request["take_sha256"]):
            raise PermissionError("Proposals require a current original Take identity")
        with self._wo6_model_lock:
            if self._wo6_closed:
                raise PermissionError("Native director session is closed")
            # Refuse accumulation instead of dropping an active source-bound
            # model completion in a different thread behind the user's back.
            active=sum(x["state"]=="GENERATING" for x in
                       self._wo6_model_proposals.values())
            if active>=1:
                raise RuntimeError("Previous local model generation has not finished")
            while len(self._wo6_model_proposals)>=MAX_MODEL_PROPOSALS:
                # Bounded retention of only completed review drafts. The
                # oldest result is evicted; no persistent source, approval
                # or model instruction is recovered or auto-applied.
                oldest=next(iter(self._wo6_model_proposals))
                if self._wo6_model_proposals[oldest]["state"]=="GENERATING":
                    raise RuntimeError("No safe completed model result to evict")
                del self._wo6_model_proposals[oldest]
            proposal_id="wo6proposal_"+secrets.token_hex(12)
            self._wo6_model_proposals[proposal_id]={
                "state":"GENERATING","project_id":request["project_id"],
                "actor_id":self._wo6_actor}
            threading.Thread(
                target=self._wo6_run_director_model,
                args=(proposal_id,dict(request)),
                name="NVP-WO6-read-only-model-suggestion",
                daemon=True).start()
        return {"format":FORMAT,"proposal_id":proposal_id,
                "state":"GENERATING","native_worker_authorized":False,
                "creative_approval_granted":False,
                "film_delivered":False}

    def wo6_model_proposal_status(self,project_id,proposal_id):
        self._wo5_project(project_id)
        if type(proposal_id) is not str or not (
                proposal_id.startswith("wo6proposal_") and
                len(proposal_id)==36):
            raise ValueError("Exact native proposal identity required")
        with self._wo6_model_lock:
            if self._wo6_closed:
                raise PermissionError("Native director model session closed")
            slot=self._wo6_model_proposals.get(proposal_id)
            if slot is None or slot["project_id"]!=project_id or (
                    slot["actor_id"]!=self._wo6_actor):
                raise PermissionError("Unknown actor or project model suggestion")
            return {"format":FORMAT, "proposal_id":proposal_id,
                    "state":slot["state"],
                    "proposal":slot.get("proposal"),
                    "failure_category":slot.get("reason"),
                    "native_worker_authorized":False,
                    "creative_approval_granted":False,
                    "film_delivered":False}

    def _wo6_verified_ai_reference(self,project_id,proposal_id,take_id,
                                   take_sha256,action_kind):
        """Reopen the exact original verified context, not model-supplied fields."""
        self._wo5_project(project_id)
        if (type(proposal_id) is not str or
                not proposal_id.startswith("wo6proposal_") or
                len(proposal_id)!=36 or
                any(c not in "0123456789abcdef" for c in proposal_id[12:]) or
                type(action_kind) is not str or
                action_kind not in (*ACTION_KINDS,"sound_cue","editorial_cut")):
            raise ValueError("Exact review proposal and supported shot kind required")
        with self._wo6_model_lock:
            if self._wo6_closed:
                raise PermissionError("Native director session already closed")
            slot=self._wo6_model_proposals.get(proposal_id)
            if (slot is None or slot["project_id"]!=project_id or
                    slot["actor_id"]!=self._wo6_actor or
                    slot["state"]!="READY_FOR_HUMAN_REVIEW"):
                raise PermissionError("No completed actor-owned model advice")
            proposal=dict(slot["proposal"])
        if (proposal.get("take_id")!=take_id or
                proposal.get("take_sha256")!=take_sha256 or
                proposal.get("project_id")!=project_id or
                proposal.get("model_text_is_untrusted") is not True or
                proposal.get("creative_approval_granted") is not False or
                proposal.get("native_worker_authorized") is not False or
                type(proposal.get("model_text_sha256")) is not str or
                len(proposal["model_text_sha256"])!=64):
            raise PermissionError("Model advice source or permission evidence changed")
        original=self.index.read_revision(project_id,take_id,1)
        if (original["kind"]!="take" or
                original["document_sha256"]!=take_sha256 or
                original["data"].get("frozen") is not True):
            raise PermissionError("Reviewed advice is not bound to original frozen Take")
        packet=assemble_film_crew_context(
            self.index,project_id,take_id,1,
            int(proposal["film_time_tick"]),max_prims=16,max_events=12)
        if (packet["context_sha256"]!=proposal["verified_source_context_sha256"]
                or packet["historical_take_not_current_scene"] or
                any(not head["is_current_head"] for head in packet["source_heads"])):
            raise PermissionError("AI consultation refers to stale source context")
        return {
            "proposal_id":proposal_id,
            "take_sha256":take_sha256,
            "model_text_sha256":proposal["model_text_sha256"],
            "verified_source_context_sha256":packet["context_sha256"],
            "film_time_tick":str(proposal["film_time_tick"]),
            "director_selected_action_kind":action_kind,
        }, original["data"]

    def wo6_review_model_proposal(self,request):
        """Explicit human-selected *consultation*, never an execution approval."""
        self._wo6_require(request,{
            "project_id","proposal_id","take_id","take_sha256",
            "model_text_sha256","verified_source_context_sha256",
            "action_kind"})
        context,take=self._wo6_verified_ai_reference(
            request["project_id"],request["proposal_id"],
            request["take_id"],request["take_sha256"],request["action_kind"])
        if (request["model_text_sha256"]!=context["model_text_sha256"] or
                request["verified_source_context_sha256"]!=
                    context["verified_source_context_sha256"]):
            raise PermissionError("Director must review exact displayed model suggestion")
        with self._wo6_model_lock:
            slot=self._wo6_model_proposals.get(request["proposal_id"])
            previous=slot.get("review") if slot else None
            if (self._wo6_closed or slot is None or
                    slot["state"]!="READY_FOR_HUMAN_REVIEW" or
                    (previous is not None and
                     (previous["in_flight"] or
                      previous["consumed_task_id"] is not None))):
                raise PermissionError("AI consultation no longer available for review")
            slot["review"]={
                "context":dict(context),"in_flight":False,
                "consumed_task_id":None,
            }
        return {
            "format":FORMAT,
            "status":"HUMAN_SELECTED_AI_CONSULTATION_NO_GRANT",
            "proposal_id":context["proposal_id"],
            "take_id":request["take_id"],
            "take_sha256":context["take_sha256"],
            "model_text_sha256":context["model_text_sha256"],
            "verified_source_context_sha256":
                context["verified_source_context_sha256"],
            "action_kind":request["action_kind"],
            "scene_id":take["scene_id"],
            "scene_revision":take["scene_revision"],
            "scene_sha256":take["scene_document_sha256"],
            "model_proposed_shot_parameters":False,
            "director_must_type_values":True,
            "creative_approval_granted":False,
            "native_worker_authorized":False,
            "source_modified":False,
            "film_delivered":False,
        }

    def wo6_source_catalog(self,project_id):
        self._wo5_project(project_id)
        scenes,timelines,takes,grades,audio_sources,slate_graphs=[],[],[],[],[],[]
        for kind,items in (
            ("scene",scenes),("temporal",timelines),
            ("take",takes),("style",grades),
            ("audio",audio_sources),("presentation",slate_graphs)):
            for entry in self.index.list_objects(project_id,kind=kind)[:MAX_LIST]:
                r=self.index.read_revision(
                    project_id,entry["object_id"],entry["head_revision"])
                if kind=="style" and r["data"].get("format")!=(
                        "nvp.data_first.color_decision.v1"):
                    continue
                if kind=="audio" and r["data"].get("format")!=(
                        "nvp.data_av.recorded_pcm.v1"):
                    continue
                if kind=="presentation" and r["data"].get("format")!=(
                        "nvp.slate.branch_graph.v1"):
                    continue
                items.append({
                    "id":r["object_id"],"kind":r["kind"],
                    "revision":r["revision"],"sha256":r["document_sha256"],
                    "data":r["data"] if kind in ("take","style","presentation") else {
                        "format":r["data"].get("format"),
                        "prim_roles":r["data"].get("prim_roles") if kind=="scene" else None,
                        "duration_tick":r["data"].get("duration_tick"),
                        "sample_count":r["data"].get("sample_count") if kind=="audio" else None,
                    },
                })
        return {
            "format":FORMAT,"project_id":project_id,
            "scenes":scenes,"timelines":timelines,
            "takes":takes,"grades":grades,
            "audio_sources":audio_sources,"slate_graphs":slate_graphs,
            "source_facts_from_real_filminindex":True,
            "approvals_preissued":False,
            "director_gui_present":True,"model_execute_enabled":False,
            "finished_film_accepted":False,
        }

    def wo6_source_impact(self,request):
        if type(request) is not dict or set(request)!={
                "project_id","source_id","source_revision",
                "source_sha256","change_kind"}:
            raise ValueError("Exact source/operation fields required")
        self._wo5_project(request["project_id"])
        return preview_source_impact(
            self.index,request["project_id"],
            request["source_id"],request["source_revision"],
            request["source_sha256"],request["change_kind"],
            max_nodes=32)

    def _wo6_require(self,request,expected):
        if type(request) is not dict or set(request)!=expected:
            raise ValueError("Unknown director operation fields")
        return self._wo6_scope(request["project_id"])

    def _wo6_decision(self):
        return "native_director_"+secrets.token_hex(16)


    def _wo6_worker_loop(self, host, queue):
        """One native host-owned dispatcher per operation family.

        Queueing a sealed approved task is never a successful native write.
        This worker drains requests without blocking the pywebview/creator
        console; the existing TaskLedger decides which task is admitted.
        """
        while True:
            trigger=queue.get()
            try:
                if trigger is None:
                    return
                # Restart/close clears ephemeral native permission. An
                # already-running worker keeps its own durable recovery
                # contract, but unstarted triggers must not auto-execute.
                with self._wo6_dispatch_lock:
                    if self._wo6_closed:
                        continue
                try:
                    outcome=host.run_next(
                        timeout_seconds=240,expected_task_id=trigger)
                    if type(outcome) is dict and outcome.get("admitted") is False:
                        # Native source and resource ledger still own state.
                        # This notice was consumed without worker launch.
                        state=outcome.get("state")
                        category=("NOTICE_NOT_CLAIMED" if state=="NOT_CLAIMED"
                                  else "RESOURCE_QUEUED" if state=="QUEUED"
                                  else "NOT_ADMITTED")
                        with self._wo6_dispatch_lock:
                            self._wo6_dispatch_deferrals[trigger]=category
                            if len(self._wo6_dispatch_deferrals)>MAX_DISPATCH_QUEUE*4:
                                self._wo6_dispatch_deferrals.pop(
                                    next(iter(self._wo6_dispatch_deferrals)))
                except Exception as exc:
                    # The actual host writes interrupted/failed task states
                    # durably; this is supplementary local diagnostic only.
                    with self._wo6_dispatch_lock:
                        # The native durable ledger is the source of truth.
                        # Do not expose subprocess paths or secrets in IPC.
                        self._wo6_dispatch_faults[trigger]=type(exc).__name__
            finally:
                queue.task_done()

    def _wo6_result(self, queued, host):
        # Native approvals were checked by queue_*. Execution is handed
        # off to a first-party serialized dispatcher, not to the browser.
        with self._wo6_dispatch_lock:
            if self._wo6_closed:
                raise RuntimeError("Director's native session is closing")
            channel=self._wo6_dispatch_queues.get(host.owner)
            if channel is None:
                channel=Queue(maxsize=MAX_DISPATCH_QUEUE)
                worker=threading.Thread(
                    target=self._wo6_worker_loop,args=(host,channel),
                    name="NVP-WO6-"+host.owner,daemon=True)
                self._wo6_dispatch_queues[host.owner]=channel
                worker.start()
            try:
                channel.put_nowait(queued["task_id"])
                dispatched=True
            except Full:
                # Approved QUEUED task is still safe in the durable ledger,
                # but must not be represented as a scheduled native worker.
                dispatched=False
        return {
            "format":FORMAT,"queued_task_id":queued["task_id"],
            "state":"QUEUED" if dispatched else "QUEUED_NOT_DISPATCHED",
            "native_dispatch_requested":dispatched,
            "native_worker_success_verified":False,
            "durable_status_must_be_polled":True,
            "finished_film_approved":False,
        }

    def wo6_create_take(self,request):
        scope=self._wo6_require(request,{
            "project_id","scene_id","scene_revision","scene_sha256",
            "timeline_id","timeline_revision","timeline_sha256",
            "new_take_id","sample_ticks","preview_sha256"})
        self._wo6_host()
        queued=self._wo6_take.queue_new_take(
            scope,creator_decision_id=self._wo6_decision(),
            scene_id=request["scene_id"],
            scene_revision=request["scene_revision"],
            scene_sha256=request["scene_sha256"],
            timeline_id=request["timeline_id"],
            timeline_revision=request["timeline_revision"],
            timeline_sha256=request["timeline_sha256"],
            new_take_id=request["new_take_id"],
            sample_ticks=request["sample_ticks"],
            expected_preview_sha256=request["preview_sha256"])
        return self._wo6_result(queued,self._wo6_take)

    def wo6_create_shot(self,request):
        required={
            "project_id","action_kind","shot_id","take_id",
            "take_sha256","scene_id","scene_revision","scene_sha256",
            "start_tick","end_tick","changes","purpose",
            "continuity_policy","reason","preview_sha256"}
        has_review=(type(request) is dict and
                    "reviewed_proposal_id" in request)
        scope=self._wo6_require(
            request,required | ({"reviewed_proposal_id"} if has_review else set()))
        context=None
        proposal_id=request.get("reviewed_proposal_id") if has_review else None
        if has_review:
            # An AI reply never supplies a worker parameter. Only an
            # explicit preceding review click plus the human's fresh
            # impact and typed operation may continue to native consent.
            context,take=self._wo6_verified_ai_reference(
                request["project_id"],proposal_id,
                request["take_id"],request["take_sha256"],
                request["action_kind"])
            if (take["scene_id"]!=request["scene_id"] or
                    take["scene_revision"]!=request["scene_revision"] or
                    take["scene_document_sha256"]!=request["scene_sha256"] or
                    type(request["reason"]) is not str or
                    not 12<=len(request["reason"].strip())<=512):
                raise PermissionError(
                    "Director must enter independent bounded reasons for exact original source")
            with self._wo6_model_lock:
                slot=self._wo6_model_proposals.get(proposal_id)
                review=slot.get("review") if slot else None
                if (review is None or review["context"]!=context or
                        review["in_flight"] or review["consumed_task_id"] is not None or
                        self._wo6_closed):
                    raise PermissionError("AI review has not been selected or was already consumed")
                review["in_flight"]=True
        try:
            self._wo6_host()
            queued=self._wo6_shot.queue_shot(
                scope,creator_decision_id=self._wo6_decision(),
                action_kind=request["action_kind"],
                shot_id=request["shot_id"],take_id=request["take_id"],
                take_sha256=request["take_sha256"],
                scene_id=request["scene_id"],
                scene_revision=request["scene_revision"],
                scene_sha256=request["scene_sha256"],
                start_tick=request["start_tick"],end_tick=request["end_tick"],
                changes=request["changes"],purpose=request["purpose"],
                continuity_policy=request["continuity_policy"],
                reason=request["reason"],
                expected_preview_sha256=request["preview_sha256"],
                ai_review_context=context)
        except BaseException:
            if has_review:
                with self._wo6_model_lock:
                    slot=self._wo6_model_proposals.get(proposal_id)
                    if slot and slot.get("review"):
                        slot["review"]["in_flight"]=False
            raise
        if has_review:
            with self._wo6_model_lock:
                slot=self._wo6_model_proposals.get(proposal_id)
                if slot and slot.get("review"):
                    slot["review"].update(
                        in_flight=False,consumed_task_id=queued["task_id"])
        result=self._wo6_result(queued,self._wo6_shot)
        if has_review:
            result.update(
                reviewed_ai_proposal_id=proposal_id,
                reviewed_model_text_sha256=context["model_text_sha256"],
                human_shot_parameters_separately_authorized=True)
        return result

    def wo6_create_decision(self,request):
        required={
            "project_id","decision_kind","decision_id","source_id",
            "source_revision","source_sha256","payload","duration_tick",
            "preview_sha256"}
        has_review=(type(request) is dict and
                    "reviewed_proposal_id" in request)
        scope=self._wo6_require(
            request,required|({"reviewed_proposal_id"} if has_review else set()))
        context=None
        take_id=None
        proposal_id=request.get("reviewed_proposal_id") if has_review else None
        if has_review:
            if request["decision_kind"] not in ("sound_cue","editorial_cut"):
                raise PermissionError(
                    "Only native sound and slate editorial edits accept this reviewed AI handoff")
            with self._wo6_model_lock:
                slot=self._wo6_model_proposals.get(proposal_id)
                proposal=dict(slot.get("proposal") or {}) if slot else {}
                take_id=proposal.get("take_id")
                take_sha=proposal.get("take_sha256")
            context,take=self._wo6_verified_ai_reference(
                request["project_id"],proposal_id,
                take_id,take_sha,request["decision_kind"])
            if request["decision_kind"]=="sound_cue":
                if (take.get("timeline_id")!=request["source_id"] or
                        take.get("timeline_revision")!=request["source_revision"] or
                        take.get("timeline_document_sha256")!=request["source_sha256"]):
                    raise PermissionError("The sound edit must originate in the reviewed Take's original timeline")
            else:
                from backend.nvp_digital_slate_branches import DigitalSlateBranches
                graph=DigitalSlateBranches(self.index,
                    verify_editor_action=lambda *_:False).open_graph(
                        request["project_id"],request["source_id"],
                        request["source_revision"])
                if (graph["document_sha256"]!=request["source_sha256"] or
                        not any(n["take_id"]==take_id and
                                n["take_document_sha256"]==take_sha
                                for n in graph["data"]["nodes"])):
                    raise PermissionError("The new editorial cut must include the exact reviewed Take")
            with self._wo6_model_lock:
                slot=self._wo6_model_proposals.get(proposal_id)
                review=slot.get("review") if slot else None
                if (review is None or review["context"]!=context or
                        review["in_flight"] or review["consumed_task_id"] is not None or
                        self._wo6_closed):
                    raise PermissionError("Completed AI advice was never selected for this specific sound/edit action")
                review["in_flight"]=True
        try:
            self._wo6_host()
            queued=self._wo6_data.queue_decision(
                scope,creator_decision_id=self._wo6_decision(),
                decision_kind=request["decision_kind"],
                decision_id=request["decision_id"],
                source_id=request["source_id"],
                source_revision=request["source_revision"],
                source_sha256=request["source_sha256"],
                payload=request["payload"],
                duration_tick=request["duration_tick"],
                expected_preview_sha256=request["preview_sha256"],
                ai_review_context=context,
                reviewed_original_take_id=take_id)
        except BaseException:
            if has_review:
                with self._wo6_model_lock:
                    slot=self._wo6_model_proposals.get(proposal_id)
                    if slot and slot.get("review"):
                        slot["review"]["in_flight"]=False
            raise
        if has_review:
            with self._wo6_model_lock:
                slot=self._wo6_model_proposals.get(proposal_id)
                if slot and slot.get("review"):
                    slot["review"].update(
                        in_flight=False,consumed_task_id=queued["task_id"])
        result=self._wo6_result(queued,self._wo6_data)
        if has_review:
            result.update(
                reviewed_ai_proposal_id=proposal_id,
                reviewed_model_text_sha256=context["model_text_sha256"],
                human_sound_or_editorial_parameters_separately_authorized=True)
        return result

    def wo6_task_status(self,project_id,task_id):
        self._wo5_project(project_id)
        self._wo6_host()
        owner,spec=self._wo6_recovery._approved_spec(task_id)
        if (spec["project_id"]!=project_id or
                spec["actor_id"]!=self._wo6_actor):
            raise PermissionError("Native job belongs to a different director")
        evidence=self._wo6_recovery.status(task_id,owner_key=owner["owner_key"])
        with self._wo6_dispatch_lock:
            fault=self._wo6_dispatch_faults.get(task_id)
            deferral=self._wo6_dispatch_deferrals.get(task_id)
        if fault is not None:
            evidence["local_dispatch_failure"]=fault
        if deferral is not None and evidence.get("state")=="QUEUED":
            evidence["local_notice_not_admitted"]=deferral
        return evidence

    def wo6_cancel_native_task(self,project_id,task_id):
        scope=self._wo6_scope(project_id)
        self._wo6_host()
        return self._wo6_recovery.request_cancel(
            scope,task_id,
            authorize_cancel=lambda caller,name,doc: (
                caller.actor_id==self._wo6_actor and
                self._native_window().create_confirmation_dialog(
                    "NVP — Cancel native creator job",
                    "Request a durable cancellation for "+name+
                    "?\nAn already committed immutable source cannot be undone."
                ) is True),
            reason="Creator cancelled via native WebView2 console")

    def _close(self):
        with self._wo6_dispatch_lock:
            self._wo6_closed=True
            for queue in self._wo6_dispatch_queues.values():
                # Drop unstarted in-memory dispatch notices. Durable tasks
                # remain QUEUED and require fresh user approval on restart.
                while True:
                    try:
                        queue.get_nowait()
                    except Empty:
                        break
                    else:
                        queue.task_done()
                queue.put_nowait(None)
        with self._wo6_model_lock:
            # An outstanding HTTP completion cannot be forcibly terminated
            # through this read-only interface. Its result is discarded.
            self._wo6_model_proposals.clear()
        self._wo6_decisions.clear()
        self._wo6_native_grants.clear()
        super()._close()
