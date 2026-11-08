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
from queue import Queue
import time

from backend.nvp_ai_read_host import TrustedReadScope
from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_film_index import _id, _require_pid
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_wo5_desktop_bridge import TrustedDesktopWO5Bridge
from backend.nvp_wo6_impact_preview import preview_source_impact
from backend.nvp_wo6_native_take_action import NativeTakeActionHost
from backend.nvp_wo6_native_shot_action import NativeShotActionHost
from backend.nvp_wo6_native_data_action import NativeFilmDecisionHost
from backend.nvp_wo6_recovery import WO6DurableRecovery

FORMAT="nvp.wo6.director_desktop_native_consent.v1"
MAX_LIST=64
MAX_APPROVAL_TEXT=4096


class TrustedDesktopWO6Bridge(TrustedDesktopWO5Bridge):
    """First-party Desktop IPC only, not NVP FastAPI or model execute catalog."""

    def __init__(self,index,*,origin,**kwargs):
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
        self._wo6_closed=False

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

    def wo6_source_catalog(self,project_id):
        self._wo5_project(project_id)
        scenes,timelines,takes,grades=[],[],[],[]
        for kind,items in (
            ("scene",scenes),("temporal",timelines),
            ("take",takes),("style",grades)):
            for entry in self.index.list_objects(project_id,kind=kind)[:MAX_LIST]:
                r=self.index.read_revision(
                    project_id,entry["object_id"],entry["head_revision"])
                if kind=="style" and r["data"].get("format")!=(
                        "nvp.data_first.color_decision.v1"):
                    continue
                items.append({
                    "id":r["object_id"],"kind":r["kind"],
                    "revision":r["revision"],"sha256":r["document_sha256"],
                    "data":r["data"] if kind in ("take","style") else {
                        "format":r["data"].get("format"),
                        "prim_roles":r["data"].get("prim_roles") if kind=="scene" else None,
                        "duration_tick":r["data"].get("duration_tick")
                    },
                })
        return {
            "format":FORMAT,"project_id":project_id,
            "scenes":scenes,"timelines":timelines,
            "takes":takes,"grades":grades,
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
                try:
                    host.run_next(timeout_seconds=240)
                except Exception as exc:
                    # The actual host writes interrupted/failed task states
                    # durably; this is supplementary local diagnostic only.
                    with self._wo6_dispatch_lock:
                        self._wo6_dispatch_faults[trigger]=(
                            type(exc).__name__+": "+str(exc)[:240])
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
                channel=Queue()
                worker=threading.Thread(
                    target=self._wo6_worker_loop,args=(host,channel),
                    name="NVP-WO6-"+host.owner,daemon=True)
                self._wo6_dispatch_queues[host.owner]=channel
                worker.start()
            channel.put(queued["task_id"])
        return {
            "format":FORMAT,"queued_task_id":queued["task_id"],
            "state":"QUEUED","native_dispatch_requested":True,
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
        scope=self._wo6_require(request,{
            "project_id","action_kind","shot_id","take_id",
            "take_sha256","scene_id","scene_revision","scene_sha256",
            "start_tick","end_tick","changes","purpose",
            "continuity_policy","reason","preview_sha256"})
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
            expected_preview_sha256=request["preview_sha256"])
        return self._wo6_result(queued,self._wo6_shot)

    def wo6_create_decision(self,request):
        scope=self._wo6_require(request,{
            "project_id","decision_kind","decision_id","source_id",
            "source_revision","source_sha256","payload","duration_tick",
            "preview_sha256"})
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
            expected_preview_sha256=request["preview_sha256"])
        return self._wo6_result(queued,self._wo6_data)

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
        if fault is not None:
            evidence["local_dispatch_failure"]=fault
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
                queue.put(None)
        self._wo6_decisions.clear()
        self._wo6_native_grants.clear()
        super()._close()
