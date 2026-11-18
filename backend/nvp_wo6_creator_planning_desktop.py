"""WO6-A: source-bound planning, not worker or film-delivery permission.

The existing FilmIndex and Story Bible remain authoritative. A bounded plan
is immutable evidence of a creative intention; it cannot authorize a worker.
"""
from __future__ import annotations

from hashlib import sha256
import json
from collections import deque
import secrets

from backend.nvp_film_index import FilmIndex, _id, _require_pid, _sha
from backend.nvp_bible_context import canon_snapshot

FORMAT = "nvp.wo6.source_bound_production_plan.v2"
RECEIPT = "nvp.wo6.creator_planning_receipt.v1"
LIMIT = 32
KINDS = {
    "retake": {"take", "scene"}, "revise_scene": {"scene"},
    "revise_camera": {"scene", "camera", "temporal"},
    "revise_performance": {"scene", "actor", "performance"},
    "revise_sound": {"audio", "dialogue", "temporal"},
    "revise_edit": {"edit"}, "review_film": {"presentation", "master", "edit"},
}
ROLES = {"take": "source_take", "edit": "presentation", "master": "presentation"}
FIELDS = {"project_id", "source_id", "source_revision", "source_sha256",
          "change_kind", "intention", "screenplay_scene_id"}
BIBLE_TABLES = {"bible_entities", "bible_facts", "bible_names", "bible_scene_links",
                "timeline_edges", "timeline_scene_marks", "timeline_knowledge",
                "scene_mind_beats", "scene_mind_changes", "scene_mind_statements",
                "scene_mind_suggestion_reviews", "timeline_state", "scene_mind_state"}


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                             allow_nan=False, separators=(",", ":")).encode("ascii")).hexdigest()


def _summary(row):
    label = row["data"].get("title") or row["data"].get("name")
    return {**{k: row[k] for k in ("object_id", "revision", "kind", "document_sha256")},
            "label": label[:100] if type(label) is str and label.strip() else row["object_id"]}


def _bible(index, pid, scene_id):
    with index.studio._connection() as db:
        db.execute("BEGIN")
        project = db.execute("SELECT revision,screenplay FROM projects WHERE id=?", (pid,)).fetchone()
        if project is None:
            raise KeyError("Unknown project")
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if scene_id is not None:
            from backend.nvp_studio import parse_screenplay
            if scene_id not in {s['id'] for s in parse_screenplay(project['screenplay'])}:
                raise KeyError("Screenplay scene not found")
        info = {"screenplay_revision": project['revision'], "screenplay_sha256": digest(project['screenplay']),
                "scene_id": scene_id, "canon_sha256": None, "approved_facts": 0,
                "status": "CANON_NOT_AVAILABLE"}
        if BIBLE_TABLES <= tables:
            canon = canon_snapshot(db, pid, scene_id)
            info.update(canon_sha256=canon['digest'], approved_facts=canon['facts_total'],
                        status="APPROVED_CANON_SNAPSHOT" if canon['facts_total'] else "NO_APPROVED_FACTS")
        return info


def _walk(index, pid, selected, downstream):
    root = (selected['object_id'], selected['revision'])
    pending = deque([root]); seen = {root}; rows = []; takes = []; truncated = False
    while pending:
        oid, rev = pending.popleft()
        row = index.read_revision(pid, oid, rev)
        if downstream and row['data'].get('format') == RECEIPT:
            continue  # Planning records are not production derivatives.
        rows.append(_summary(row))
        if not downstream and row['kind'] == 'take' and row['data'].get('format') == 'nvp.digital_take.openusd_temporal.v1':
            data = row['data']
            if data.get('frozen') is not True:
                raise PermissionError('Unfrozen Take source')
            for role, prefix in (('scene', 'scene'), ('temporal', 'timeline')):
                ref = {"object_id": data.get(prefix+'_id'), "revision": data.get(prefix+'_revision'), "role": role}
                if ref not in row['dependencies']:
                    raise PermissionError('Missing immutable Take dependency')
                source = index.read_revision(pid, ref['object_id'], ref['revision'])
                if source['kind'] != role or source['document_sha256'] != data.get(prefix+'_document_sha256'):
                    raise PermissionError('Take source identity mismatch')
            takes.append(_summary(row))
        edges = index.direct_dependents(pid, oid, rev) if downstream else row['dependencies']
        for edge in edges:
            key = (edge['object_id'], edge['revision'])
            if key in seen:
                continue
            if len(seen) >= LIMIT:
                truncated = True
                break
            seen.add(key); pending.append(key)
    return rows, takes, truncated


def preview_source_impact(index, request):
    if not isinstance(index, FilmIndex) or type(request) is not dict or set(request) != FIELDS:
        raise ValueError('Exact planning fields required')
    pid = _require_pid(request['project_id']); oid = _id(request['source_id'], 'source'); rev = request['source_revision']
    if type(rev) is not int or rev < 1:
        raise ValueError('Exact positive revision required')
    expected = _sha(request['source_sha256']); change = request['change_kind']; note = request['intention']
    if type(change) is not str or change not in KINDS:
        raise ValueError('Unknown planning operation')
    if type(note) is not str or not note.strip() or len(note) > 800 or any(ord(c) < 32 and c not in '\n\t' for c in note):
        raise ValueError('Bounded plain-text creative intention required')
    scene = request['screenplay_scene_id']
    if scene is not None:
        _id(scene, 'screenplay scene')
    source = index.read_revision(pid, oid, rev)
    if source['kind'] not in KINDS[change] or source['data'].get('format') == RECEIPT or source['document_sha256'] != expected:
        raise PermissionError('Selected source or operation does not match')
    def current():
        return any(r['object_id'] == oid and r['head_revision'] == rev
                   for r in index.list_objects(pid, kind=source['kind']))
    active = current(); bible = _bible(index, pid, scene)
    upstream, takes, up_partial = _walk(index, pid, source, False)
    downstream, _, down_partial = _walk(index, pid, source, True)
    if current() != active or _bible(index, pid, scene) != bible:
        raise RuntimeError('Source or approved story context changed during planning')
    result = {"format": FORMAT, "project_id": pid, "request": dict(request),
              "source": _summary(source), "source_current_and_available": active,
              "indexed_source_lineage": upstream, "verified_take_metadata": takes,
              "indexed_downstream": downstream[1:], "graph_truncated": up_partial or down_partial,
              "story_context": bible, "all_downstream_outputs_proven": False,
              "feature_journal_outputs_reconciled": False, "native_media_reopened": False,
              "creator_approved": False, "worker_authorized": False,
              "worker_executed": False, "film_approved": False,
              "planning_approval_available": active and not (up_partial or down_partial)}
    result['preview_sha256'] = digest(result)
    return result


class CreatorPlanningActions:
    """Mounted only on the actual native desktop authority and its narrow proxy."""
    def wo6_plan_catalog(self, project_id):
        pid = self._wo5_project(project_id)
        kinds = set().union(*KINDS.values()); choices = []; plans = []
        rows = [r for r in self.index.list_objects(pid) if r['kind'] in kinds]
        for entry in rows[:128]:
            r = self.index.read_revision(pid, entry['object_id'], entry['head_revision'])
            if r['data'].get('format') == RECEIPT:
                if len(plans)<64:
                    plans.append(_summary(r))
            elif len(choices)<64:
                choices.append({**_summary(r), 'changes': sorted(k for k,v in KINDS.items() if r['kind'] in v)})
        self._wo5_project(pid)
        return {'project_id': pid, 'sources': choices, 'saved_plans': plans, 'catalog_truncated': len(rows)>64,
                'worker_authorized': False}

    def wo6_plan_preview(self, request):
        if type(request) is not dict or set(request) != FIELDS:
            raise ValueError('Exact planning fields required')
        self._wo5_project(request['project_id'])
        result = preview_source_impact(self.index, request)
        self._wo5_project(request['project_id'])
        return result

    def wo6_plan_save(self, request):
        if type(request) is not dict or set(request) != {'proposal', 'preview_sha256'}:
            raise ValueError('Exact preview required; browser approval is not authority')
        if type(request['proposal']) is not dict:
            raise ValueError('Typed planning proposal required')
        proposal = dict(request['proposal']); expected = _sha(request['preview_sha256'])
        with self._lock:
            if getattr(self, '_wo6_plan_pending', False):
                raise PermissionError('Another planning confirmation is pending')
            self._wo6_plan_pending = True
        try:
            plan = self.wo6_plan_preview(proposal)
            if plan['preview_sha256'] != expected or not plan['planning_approval_available']:
                raise PermissionError('Stale, retired or incomplete planning preview')
            pid = plan['project_id']; source = plan['source']; oid = source['object_id']
            message = ('Save this CREATIVE PLAN ONLY?\nSource: '+oid+' revision '+str(source['revision'])+
                       '\nSource SHA: '+source['document_sha256']+'\nPreview SHA: '+expected+
                       '\nStory context: '+str(plan['story_context']['canon_sha256'])+
                       '\nChange: '+proposal['change_kind']+'\nIntention: '+proposal['intention']+
                       '\nNo worker, source edit, render or film delivery is authorized.')
            if self._native_window().create_confirmation_dialog('NVP — Approve creative plan', message) is not True:
                return {'status': 'DENIED', 'worker_authorized': False}
            def guard(_db):
                fresh = self.wo6_plan_preview(proposal)
                if fresh['preview_sha256'] != expected or not fresh['planning_approval_available']:
                    raise PermissionError('Source-bound plan changed after creator confirmation')
            guard(None)
            # FilmIndex checks retired dependencies and the fresh preview under its write lease.
            receipt = {'format': RECEIPT, 'plan': plan, 'creator_confirmed_planning_only': True,
                       'worker_authorized': False, 'worker_executed': False, 'film_approved': False}
            with self._lock:
                guard(None)
                committed = self.index.register_revision(pid, 'Plan'+secrets.token_hex(16), 'presentation', receipt,
                    expected_revision=0, dependencies=[{'object_id': oid, 'revision': source['revision'],
                    'role': ROLES.get(source['kind'], source['kind'])}], precommit_guard=guard)
            return {'status': 'PLAN_SAVED_NOT_EXECUTION_AUTHORITY', 'record': committed, 'worker_authorized': False}
        finally:
            with self._lock:
                self._wo6_plan_pending = False

    def wo6_plan_read(self, project_id, plan_id):
        pid = self._wo5_project(project_id)
        row = self.index.read_revision(pid, _id(plan_id, 'plan'), 1)
        if row['kind'] != 'presentation' or row['data'].get('format') != RECEIPT:
            raise PermissionError('Not a saved creator plan')
        data = row['data']; plan = dict(data['plan']); claimed = plan.pop('preview_sha256')
        if data.get('creator_confirmed_planning_only') is not True or data.get('worker_authorized') is not False or digest(plan) != claimed or plan['project_id'] != pid:
            raise PermissionError('Invalid saved plan receipt')
        self._wo5_project(pid)
        return {'record': _summary(row), 'data': data, 'worker_authorized': False}



    def wo6_retake_execute(self, request):
        """Native creator action on an exact saved plan; no browser grant."""
        if type(request) is not dict or set(request)!={"project_id","plan_id","plan_sha256"}:
            raise ValueError("Exact saved plan identity required")
        pid=self._wo5_project(request["project_id"])
        with self._lock:
            if getattr(self,"_wo6_execute_pending",False):
                raise PermissionError("Another Take operation is pending")
            self._wo6_execute_pending=True
        try:
            from backend.nvp_resource_ledger import TaskLedger
            from backend.nvp_wo6_native_take_action import execute_saved_retake
            plan_id=_id(request["plan_id"],"saved plan")
            plan_sha=_sha(request["plan_sha256"])
            output="Take"+secrets.token_hex(16)
            def live(doc):
                return self._wo5_project(pid)==pid and doc["project_id"]==pid
            def confirm(doc,spec_sha):
                scope=doc["scope"]
                return self._native_window().create_confirmation_dialog(
                    "NVP — Create new Take",
                    "Create a separate frozen Take from the unchanged original scene and timing?\n"+
                    "Saved plan: "+plan_id+"\nOriginal Take: "+scope["original_take_id"]+
                    "\nNew Take: "+output+"\nSource scene: "+scope["scene_sha256"]+
                    "\nSource timing: "+scope["timeline_sha256"]+
                    "\nAuthorized operation: "+spec_sha+
                    "\nThis does not apply the written creative changes or render a movie.") is True
            return execute_saved_retake(self.index,TaskLedger(),project_id=pid,
                plan_id=plan_id,plan_sha256=plan_sha,new_take_id=output,
                confirm_native=confirm,live_gate=live)
        finally:
            with self._lock:
                self._wo6_execute_pending=False
