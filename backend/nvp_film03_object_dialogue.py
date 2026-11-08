"""FILM03-01: revision-linked original script, object-actor dialogue and Take selection.

Existing Studio screenplay revisions are canonical, not a competing script DB.
Existing StoryBible characters/scene links are authoritative production-canon
references. FilmIndex source revisions, frozen OpenUSD Takes, and temporal
events stay immutable. Script changes may propose *new* dialogue selections;
they NEVER rewrite audio, a scene layer, an approved Take or an old selection.

Each script line receives a stable ID across exact matches and unambiguous
one-for-one rewrites. Ambiguous multi-line edits are flagged for director
reconciliation, NOT automatically assigned to old recordings.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from hashlib import sha256
import json
from pathlib import Path

from backend.nvp_film_index import FilmIndex, _id, _sha, _require_pid
from backend.nvp_studio import Studio, parse_screenplay
from backend.nvp_story_bible import StoryBible
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture, FORMAT as TAKE_FORMAT
from backend.nvp_data_av_source import RecordedSoundSources, SAMPLE_RATE
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND, _int

SCRIPT_FORMAT = "nvp.film03.script_dialogue_snapshot.v1"
PERFORMANCE_FORMAT = "nvp.film03.object_actor_dialogue_performance.v1"
SELECTION_FORMAT = "nvp.film03.scene_dialogue_selection.v1"
MAX_LINES = 512
MAX_SCENES = 128
MAX_TEXT = 3000
MAX_SELECTED_LINES = 32
MAX_ORIGINAL_EVENTS = 400


def _canonical(item):
    return json.dumps(item, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _digest(item):
    return sha256(_canonical(item)).hexdigest()


def _line_id(script_id, scene_id, script_rev, ordinal):
    return "Dlg_" + sha256(
        f"{script_id}|{scene_id}|{script_rev}|{ordinal}".encode("utf8")
    ).hexdigest()[:26]


def _lines_by_id(snapshot):
    return {line["line_id"]: (scene, line)
            for scene in snapshot["scenes"] for line in scene["lines"]}


def _script_scenes(script, script_id, revision, old=None):
    parsed = parse_screenplay(script)
    if len(parsed) > MAX_SCENES:
        raise ValueError("Too many screenplay scenes for bounded line review")
    prior_scenes = {scene["scene_id"]: scene for scene in old["scenes"]} if old else {}
    new_scenes = []
    changes = []
    count = 0
    for parsed_scene in parsed:
        scene_id = parsed_scene["id"]
        raw = parsed_scene["dialogue"]
        if not isinstance(raw, list) or len(raw) > MAX_LINES:
            raise ValueError("Screenplay scene has too many dialogue cues")
        source = []
        for index, entry in enumerate(raw):
            speaker, text = entry["speaker"], entry["line"]
            if (type(speaker) is not str or not speaker or
                    type(text) is not str or not text.strip() or
                    len(text) > MAX_TEXT):
                raise ValueError("Unbounded or ambiguous screenplay dialogue text")
            source.append({"speaker": speaker, "text": text,
                           "ordinal": index, "text_sha256": sha256(text.encode("utf8")).hexdigest()})
        old_lines = prior_scenes.get(scene_id, {}).get("lines", [])
        identities = {}
        relation = {}
        if old_lines:
            old_tokens = [(r["speaker"], r["text"]) for r in old_lines]
            new_tokens = [(r["speaker"], r["text"]) for r in source]
            matcher = SequenceMatcher(None, old_tokens, new_tokens, autojunk=False)
            for tag, i0, i1, j0, j1 in matcher.get_opcodes():
                if tag == "equal":
                    for old_index, new_index in zip(range(i0, i1), range(j0, j1)):
                        identities[new_index] = old_lines[old_index]["line_id"]
                        relation[new_index] = "unchanged"
                elif tag == "replace" and i1-i0 == 1 and j1-j0 == 1 and (
                        old_lines[i0]["speaker"] == source[j0]["speaker"]):
                    identities[j0] = old_lines[i0]["line_id"]
                    relation[j0] = "revised"
                elif tag == "replace":
                    for new_index in range(j0, j1):
                        relation[new_index] = "requires_director_reconciliation"
        scene_lines = []
        for n, entry in enumerate(source):
            count += 1
            if count > MAX_LINES:
                raise ValueError("Snapshot exceeds 512 bounded dialogue lines")
            line_id = identities.get(n) or _line_id(script_id, scene_id, revision, n)
            if line_id in {r["line_id"] for r in scene_lines}:
                raise RuntimeError("Script line lineage collided")
            status = relation.get(n, "added")
            scene_lines.append({**entry, "line_id": line_id, "lineage_status": status})
            if status != "unchanged":
                old_line = next((r for r in old_lines if r["line_id"] == line_id), None)
                changes.append({
                    "kind": status, "scene_id": scene_id, "line_id": line_id,
                    "speaker": entry["speaker"], "new_text": entry["text"],
                    "old_text": old_line["text"] if old_line else None,
                })
        new_scenes.append({
            "scene_id": scene_id, "heading": parsed_scene["heading"],
            "scene_text_sha256": sha256(parsed_scene["text"].encode("utf8")).hexdigest(),
            "lines": scene_lines,
        })
        retained = {r["line_id"] for r in scene_lines}
        for previous in old_lines:
            if previous["line_id"] not in retained:
                changes.append({
                    "kind": "removed_or_unmatched", "scene_id": scene_id,
                    "line_id": previous["line_id"], "speaker": previous["speaker"],
                    "old_text": previous["text"], "new_text": None,
                })
    new_scene_ids = {s["scene_id"] for s in new_scenes}
    for old_scene in prior_scenes.values():
        if old_scene["scene_id"] not in new_scene_ids:
            for previous in old_scene["lines"]:
                changes.append({
                    "kind": "scene_removed_or_renamed",
                    "scene_id": old_scene["scene_id"], "line_id": previous["line_id"],
                    "speaker": previous["speaker"], "old_text": previous["text"],
                    "new_text": None,
                })
    return new_scenes, changes


class ObjectActorDialogue:
    def __init__(self, index: FilmIndex, *, verify_creator_action):
        if not isinstance(index, FilmIndex) or not callable(verify_creator_action):
            raise TypeError("Existing FilmIndex and trusted creator authorization are required")
        self.index = index
        self.studio = index.studio
        self.bible = StoryBible(index.studio)
        self._approve = verify_creator_action

    def _auth(self, action, scope, creator_event):
        if not self._approve(creator_event, {"operation": action, **scope}):
            raise PermissionError("Creator did not authorize dialogue production action")

    def _current_script(self, pid):
        _require_pid(pid)
        with self.studio._connection() as db:
            row = db.execute(
                "SELECT screenplay,revision FROM projects WHERE id=?", (pid,)
            ).fetchone()
        if row is None:
            raise KeyError("No active film project")
        return row["screenplay"], row["revision"]

    def _snapshot_data(self, pid, script_id, *, expected_screenplay_revision,
                       previous_revision):
        _id(script_id, "script dialogue manifest")
        script, source_revision = self._current_script(pid)
        if (type(expected_screenplay_revision) is not int or
                expected_screenplay_revision != source_revision):
            raise RuntimeError("Screenplay changed: reload exact source before linking dialogue")
        if not script.strip():
            raise ValueError("Unscripted performance needs a separate explicitly recorded source")
        prior = None
        if previous_revision:
            source = self.index.read_revision(pid, script_id, previous_revision)
            if source["kind"] != "dialogue" or source["data"].get("format") != SCRIPT_FORMAT:
                raise PermissionError("Prior script source was not a FILM03 dialogue snapshot")
            prior = source["data"]
            if prior["screenplay_revision"] >= source_revision:
                raise RuntimeError("Screenplay version did not advance")
        scenes, changes = _script_scenes(script, script_id, source_revision, prior)
        if not scenes or not any(scene["lines"] for scene in scenes):
            raise ValueError("Screenplay has no bounded dialogue to link")
        return {
            "format": SCRIPT_FORMAT,
            "source": "existing_studio_screenplay_and_story_bible",
            "screenplay_revision": source_revision,
            "screenplay_sha256": sha256(script.encode("utf8")).hexdigest(),
            "previous_screenplay_revision": (
                prior["screenplay_revision"] if prior else None),
            "scenes": scenes, "changes_from_previous_snapshot": changes,
            "lineage_ambiguous": any(x["kind"] in (
                "requires_director_reconciliation", "removed_or_unmatched",
                "scene_removed_or_renamed") for x in changes),
            "frozen_digital_takes_mutated": False,
            "recorded_dialogue_mutated": False,
            "actor_recast_automatically": False,
        }

    def preview_script_changes(self, pid, script_id):
        """Read-only pending changes, affected historical recordings and Bible warnings."""
        _require_pid(pid)
        _id(script_id, "script dialogue manifest")
        try:
            previous = self.index.read_revision(pid, script_id)
            if previous["data"].get("format") != SCRIPT_FORMAT:
                raise PermissionError("Not a FILM03 screenplay source manifest")
            rev = previous["revision"]
        except KeyError:
            previous = None
            rev = 0
        _, source_revision = self._current_script(pid)
        data = self._snapshot_data(pid, script_id,
                                   expected_screenplay_revision=source_revision,
                                   previous_revision=rev)
        current = _lines_by_id(data)
        changed_old_ids = {
            line["line_id"] for line in data["changes_from_previous_snapshot"]
            if line["kind"] != "added"}
        impacted = []
        for ref in self.index.list_objects(pid, kind="performance"):
            record = self.index.read_revision(pid, ref["object_id"], ref["head_revision"])
            perf = record["data"]
            if (perf.get("format") != PERFORMANCE_FORMAT or
                    perf.get("script_id") != script_id):
                continue
            line_id = perf["script_line_id"]
            current_line = current.get(line_id)
            unchanged = bool(current_line and
                             current_line[1]["text_sha256"] ==
                             perf["script_line_text_sha256"] and
                             current_line[1]["speaker"] == perf["screenplay_speaker"])
            if not unchanged:
                impacted.append({
                    "performance_id": ref["object_id"],
                    "old_script_revision": perf["script_revision"],
                    "script_line_id": line_id,
                    "old_original_performance_preserved": True,
                    "line_still_exists": current_line is not None,
                    "current_text": current_line[1]["text"] if current_line else None,
                    "required_action": "director_review_retake_or_retain",
                })
        return {
            "format": "nvp.film03.readonly_script_dialogue_impact.v1",
            "screenplay_revision": source_revision,
            "last_published_script_snapshot_revision": rev,
            "new_or_changed_script_lines": data["changes_from_previous_snapshot"],
            "impacted_historical_performances": impacted,
            "production_bible": self.bible.report(pid),
            "requires_manual_lineage_review": data["lineage_ambiguous"],
            "retakes_performed_automatically": False,
            "old_audio_takes_modified": False,
            "edit_selection_changed": False,
        }

    def publish_script_snapshot(self, pid, script_id, *,
                                expected_screenplay_revision,
                                expected_manifest_revision,
                                creator_event):
        _require_pid(pid)
        _id(script_id, "script dialogue manifest")
        if type(expected_manifest_revision) is not int or expected_manifest_revision < 0:
            raise ValueError("Exact expected script manifest revision required")
        data = self._snapshot_data(
            pid, script_id,
            expected_screenplay_revision=expected_screenplay_revision,
            previous_revision=expected_manifest_revision)
        self._auth("film03_publish_script_dialogue", {
            "project_id": pid, "script_object_id": script_id,
            "screenplay_revision": expected_screenplay_revision,
            "screenplay_sha256": data["screenplay_sha256"],
            "expected_manifest_revision": expected_manifest_revision,
            "changed_line_count": len(data["changes_from_previous_snapshot"]),
        }, creator_event)

        def guard(db):
            row = db.execute("SELECT screenplay,revision FROM projects WHERE id=?",
                             (pid,)).fetchone()
            if (row is None or row["revision"] != expected_screenplay_revision or
                    sha256(row["screenplay"].encode("utf8")).hexdigest() !=
                    data["screenplay_sha256"]):
                raise RuntimeError("Screenplay changed during approved dialogue commit")
        return self.index.register_revision(
            pid, script_id, "dialogue", data,
            expected_revision=expected_manifest_revision, precommit_guard=guard)

    def _script_line(self, pid, script_id, revision, line_id):
        rec = self.index.read_revision(pid, script_id, revision)
        if rec["kind"] != "dialogue" or rec["data"].get("format") != SCRIPT_FORMAT:
            raise PermissionError("Dialogue script source is not a frozen screenplay revision")
        line = _lines_by_id(rec["data"]).get(line_id)
        if line is None:
            raise KeyError("Screenplay line identity was not in selected revision")
        return rec, line[0], line[1]

    def record_performance(self, pid, performance_id, *,
                           script_id, script_revision, script_line_id,
                           bible_entity_id, actor_prim_path,
                           source_take_id, source_take_sha256,
                           first_tick, end_tick, delivery_intent,
                           voice_source_id=None, voice_source_revision=None,
                           creator_event):
        """Record an immutable actor line binding. No generated voice is implied."""
        _require_pid(pid)
        for oid in (performance_id, script_id, script_line_id,
                    source_take_id):
            _id(oid, "dialogue performance identity")
        _sha(source_take_sha256)
        _int(first_tick, "dialogue start")
        _int(end_tick, "dialogue end", minimum=1)
        if (end_tick <= first_tick or type(delivery_intent) is not str or
                not delivery_intent.strip() or len(delivery_intent) > 512 or
                type(actor_prim_path) is not str or
                not actor_prim_path.startswith("/World/") or
                len(actor_prim_path) > 240):
            raise ValueError("Typed bounded actor dialogue performance required")
        script, scene, line = self._script_line(
            pid, script_id, script_revision, script_line_id)
        if line["lineage_status"] == "requires_director_reconciliation":
            raise PermissionError("Ambiguous screenplay line requires manual linkage before performance")
        bible = self.bible.get_entity(pid, bible_entity_id)
        if bible["kind"] != "character" or line["speaker"].casefold() not in {
                bible["name"].casefold(), *(a.casefold() for a in bible["aliases"])}:
            raise PermissionError("Screenplay speaker is not approved production-bible character")
        linked = next((item for item in bible["scene_links"]
                       if item["scene_id"] == scene["scene_id"] and
                       item["scene_sha"] == scene["scene_text_sha256"] and
                       item["screenplay_revision"] == script["data"]["screenplay_revision"]),
                      None)
        if linked is None:
            raise PermissionError("Production bible has no exact-screenplay-revision scene/actor link")
        take = self.index.read_revision(pid, source_take_id, 1)
        if (take["kind"] != "take" or
                take["data"].get("format") != TAKE_FORMAT or
                take["data"].get("frozen") is not True or
                take["document_sha256"] != source_take_sha256 or
                end_tick > take["data"]["duration_tick"]):
            raise PermissionError("Dialogue performance does not use actual frozen source Take")
        scene_source, _ = OpenUSDSceneBridge(self.index).open(
            pid, take["data"]["scene_id"], take["data"]["scene_revision"])
        if (scene_source["document_sha256"] !=
                take["data"]["scene_document_sha256"] or
                scene_source["data"]["prim_roles"].get(actor_prim_path) != "actor"):
            raise PermissionError("Source Take has no authentic OpenUSD actor at requested path")
        verify = OpenUSDTakeCapture(
            self.index, verify_creator_action=lambda *_:False
        ).verify_take(pid, source_take_id)
        if verify["take_document_sha256"] != source_take_sha256:
            raise RuntimeError("Frozen Take's authored source was modified")
        source_audio = None
        if (voice_source_id is None) != (voice_source_revision is None):
            raise ValueError("Recorded voice source ID and revision must be paired")
        if voice_source_id is not None:
            item = RecordedSoundSources(self.index).describe(
                pid, voice_source_id, voice_source_revision)
            if (item["data"]["sample_count"] * TICKS_PER_SECOND <
                    (end_tick-first_tick) * SAMPLE_RATE):
                raise ValueError("Original recorded voice is shorter than the proposed line")
            source_audio = {
                "audio_id": voice_source_id, "audio_revision": voice_source_revision,
                "audio_sha256": item["document_sha256"], "recorded_pcm_verified": True,
            }
        accepted = sorted([
            {"key": f["fact_key"], "scope": f["story_scope"],
             "value": f["fact_value"], "id": f["id"]}
            for f in bible["facts"] if f["status"] == "accepted"
        ], key=lambda x:(x["key"],x["scope"],x["id"]))[:32]
        bible_stamp = {
            "entity_id": bible_entity_id, "name": bible["name"],
            "entity_revision": bible["revision"], "linked_scene_id": scene["scene_id"],
            "linked_scene_sha256": linked["scene_sha"],
            "screenplay_revision": linked["screenplay_revision"],
            "accepted_canon_fact_digest": _digest(accepted),
        }
        manifest = {
            "format": PERFORMANCE_FORMAT,
            "script_id": script_id, "script_revision": script_revision,
            "script_document_sha256": script["document_sha256"],
            "screenplay_revision": script["data"]["screenplay_revision"],
            "script_line_id": script_line_id,
            "script_line_text": line["text"],
            "script_line_text_sha256": line["text_sha256"],
            "screenplay_speaker": line["speaker"],
            "screenplay_scene_id": scene["scene_id"],
            "source_take_id": source_take_id,
            "source_take_sha256": source_take_sha256,
            "openusd_actor_prim_path": actor_prim_path,
            "production_bible": bible_stamp,
            "first_tick": first_tick, "end_tick": end_tick,
            "delivery_intent": delivery_intent.strip(),
            "recorded_voice_source": source_audio,
            "recorded_dialogue_present": source_audio is not None,
            "voice_synthesized": False,
            "prior_script_work_destroyed": False,
            "frozen_source_take_changed": False,
            "creator_performance_authorized": True,
        }
        self._auth("film03_record_object_actor_dialogue", {
            "project_id": pid, "performance_id": performance_id,
            "script_document_sha256": script["document_sha256"],
            "script_line_id": script_line_id, "source_take_sha256": source_take_sha256,
            "openusd_actor_prim_path": actor_prim_path,
            "production_bible_entity_id": bible_entity_id,
            "first_tick": first_tick, "end_tick": end_tick,
            "recorded_voice_source": source_audio,
        }, creator_event)
        dependencies = [
            {"object_id": script_id, "revision": script_revision, "role": "dialogue"},
            {"object_id": source_take_id, "revision": 1, "role": "source_take"},
        ]
        if source_audio:
            dependencies.append({
                "object_id": voice_source_id, "revision": voice_source_revision,
                "role": "audio",
            })
        return self.index.register_revision(
            pid, performance_id, "performance", manifest, expected_revision=0,
            dependencies=dependencies)

    def publish_scene_dialogue(self, pid, *, selection_id, overlay_timeline_id,
                               source_take_id, source_take_sha256,
                               script_id, script_revision, performance_ids,
                               expected_selection_revision=0,
                               expected_timeline_revision=0,
                               preserve_prior_script_performances=False,
                               preservation_reason="", creator_event):
        """Create NEW derived dialogue source/selection; never mutate frozen Take."""
        _require_pid(pid)
        for value in (selection_id, overlay_timeline_id, source_take_id, script_id):
            _id(value, "authored scene dialogue ID")
        _sha(source_take_sha256)
        if (type(performance_ids) is not list or not
                1 <= len(performance_ids) <= MAX_SELECTED_LINES or
                len(set(performance_ids)) != len(performance_ids) or
                any(type(x) is not str for x in performance_ids) or
                type(preserve_prior_script_performances) is not bool or
                type(preservation_reason) is not str or
                len(preservation_reason) > 1000):
            raise ValueError("Explicit, bounded unique approved actor dialogue selection required")
        script = self.index.read_revision(pid, script_id, script_revision)
        if script["kind"] != "dialogue" or script["data"].get("format") != SCRIPT_FORMAT:
            raise PermissionError("Selection must refer to exact script manifest")
        take = self.index.read_revision(pid, source_take_id, 1)
        if (take["kind"] != "take" or
                take["document_sha256"] != source_take_sha256 or
                take["data"].get("frozen") is not True):
            raise PermissionError("Cannot rebind a frozen scene to an unapproved Take")
        base_timeline = TemporalLedger(self.index)
        base_doc = take["data"]
        original = base_timeline._revision(
            pid, base_doc["timeline_id"], base_doc["timeline_revision"])
        if original["document_sha256"] != base_doc["timeline_document_sha256"]:
            raise PermissionError("Frozen Take's original authored sound/actions changed")
        base_timeline.verify(pid, base_doc["timeline_id"], base_doc["timeline_revision"])
        events_raw = base_timeline.events_in(
            pid, base_doc["timeline_id"], base_doc["timeline_revision"],
            start_tick=0, end_tick=base_doc["duration_tick"],
            limit=MAX_ORIGINAL_EVENTS+1)
        if (events_raw["next_cursor"] is not None or
                len(events_raw["events"]) != original["data"]["event_count"] or
                len(events_raw["events"]) > MAX_ORIGINAL_EVENTS):
            raise RuntimeError("Cannot safely preserve all original Take events")
        events = [
            {k: event[k] for k in (
                "event_id", "event_kind", "subject_id", "start_tick",
                "end_tick", "source_id", "source_revision", "payload")}
            for event in events_raw["events"]]
        line_map = _lines_by_id(script["data"])
        selected = []
        retained_old = []
        seen_lines = set()
        for oid in performance_ids:
            _id(oid, "recorded line")
            perf = self.index.read_revision(pid, oid, 1)
            doc = perf["data"]
            if (perf["kind"] != "performance" or
                    doc.get("format") != PERFORMANCE_FORMAT or
                    doc["source_take_id"] != source_take_id or
                    doc["source_take_sha256"] != source_take_sha256):
                raise PermissionError("Selection contains a foreign/mutated actor performance")
            current = line_map.get(doc["script_line_id"])
            compatible = bool(current and
                              current[1]["text_sha256"] == doc["script_line_text_sha256"] and
                              current[1]["speaker"] == doc["screenplay_speaker"] and
                              current[1]["lineage_status"] !=
                              "requires_director_reconciliation")
            if not compatible:
                retained_old.append(oid)
                if not preserve_prior_script_performances or not preservation_reason.strip():
                    raise PermissionError("Changed script requires a new Take or explicit director decision to retain old dialogue")
            if doc["script_line_id"] in seen_lines:
                raise ValueError("A script line cannot have two concurrently selected performances")
            seen_lines.add(doc["script_line_id"])
            entity = self.bible.get_entity(pid, doc["production_bible"]["entity_id"])
            snapshot = doc["production_bible"]
            if entity["kind"] != "character":
                raise RuntimeError("Production bible actor identity no longer resolves to a character")
            canonical = sorted([
                {"key": f["fact_key"], "scope": f["story_scope"],
                 "value": f["fact_value"], "id": f["id"]}
                for f in entity["facts"] if f["status"] == "accepted"
            ], key=lambda x:(x["key"],x["scope"],x["id"]))[:32]
            if (_digest(canonical) != snapshot["accepted_canon_fact_digest"] or
                    entity["revision"] != snapshot["entity_revision"]):
                retained_old.append(oid)
                if not preserve_prior_script_performances or not preservation_reason.strip():
                    raise PermissionError("Production bible changed: explicitly review old character performance")
            start, stop = doc["first_tick"], doc["end_tick"]
            actor_id = doc["openusd_actor_prim_path"].rsplit("/", 1)[-1]
            _id(actor_id, "OpenUSD actor subject")
            events.append({
                "event_id": "D_" + oid,
                "event_kind": "dialogue",
                "subject_id": actor_id,
                "start_tick": start,
                "end_tick": stop,
                "source_id": oid,
                "source_revision": 1,
                "payload": {
                    "script_id": doc["script_id"],
                    "script_revision": doc["script_revision"],
                    "script_line_id": doc["script_line_id"],
                    "script_line_sha256": doc["script_line_text_sha256"],
                    "actor_prim_path": doc["openusd_actor_prim_path"],
                    "production_bible_entity_id": snapshot["entity_id"],
                    "performance_id": oid,
                    "voice_source_recorded": doc["recorded_dialogue_present"],
                    "metadata_dialogue_not_assumed_playable": True,
                },
            })
            if doc["recorded_voice_source"]:
                snd = doc["recorded_voice_source"]
                events.append({
                    "event_id": "Voice_" + oid,
                    "event_kind": "sound",
                    "subject_id": actor_id,
                    "start_tick": start,
                    "end_tick": stop,
                    "source_id": snd["audio_id"],
                    "source_revision": snd["audio_revision"],
                    "payload": {
                        "source_first_sample": 0,
                        "gain": 1.0,
                        "performance_id": oid,
                        "production_bible_entity_id": snapshot["entity_id"],
                        "recorded_dialogue_not_final_mix": True,
                    },
                })
            selected.append({
                "performance_id": oid, "source_performance_sha256": perf["document_sha256"],
                "script_line_id": doc["script_line_id"],
                "script_line_sha256": doc["script_line_text_sha256"],
                "production_bible_entity_id": snapshot["entity_id"],
                "actor_prim_path": doc["openusd_actor_prim_path"],
                "recorded_voice": doc["recorded_dialogue_present"],
                "matches_selected_script_text": compatible,
            })
        if len({x["event_id"] for x in events}) != len(events):
            raise RuntimeError("Derived dialogue event collides with original preserved event")
        prior = None
        if expected_selection_revision:
            prior = self.index.read_revision(
                pid, selection_id, expected_selection_revision)
            if (prior["kind"] != "presentation" or
                    prior["data"].get("format") != SELECTION_FORMAT or
                    prior["data"]["source_take_sha256"] != source_take_sha256 or
                    prior["data"]["overlay_timeline_id"] != overlay_timeline_id):
                raise PermissionError("Cannot change the original scene/timeline identity")
        if (type(expected_selection_revision) is not int or
                type(expected_timeline_revision) is not int or
                expected_selection_revision < 0 or expected_timeline_revision < 0 or
                expected_selection_revision != expected_timeline_revision):
            raise ValueError("One-to-one scene dialogue selection/temporal revision required")
        ordered = sorted(selected, key=lambda d: (
            self.index.read_revision(pid, d["performance_id"], 1)["data"]["first_tick"],
            d["performance_id"]))
        self._auth("film03_publish_scene_dialogue_selection", {
            "project_id": pid, "selection_id": selection_id,
            "source_take_sha256": source_take_sha256,
            "script_sha256": script["document_sha256"],
            "selected_performances": [x["performance_id"] for x in ordered],
            "old_performances_kept_by_director": sorted(set(retained_old)),
            "preservation_reason": preservation_reason,
            "previous_selection_revision": expected_selection_revision,
        }, creator_event)
        # Two durable append-only records. An interrupted second write can
        # leave an unreferenced *new* timeline, NEVER modify an old Take.
        derived = base_timeline.publish(
            pid, overlay_timeline_id, events,
            duration_tick=base_doc["duration_tick"],
            expected_revision=expected_timeline_revision)
        result = {
            "format": SELECTION_FORMAT, "source_take_id": source_take_id,
            "source_take_sha256": source_take_sha256,
            "source_take_timeline_sha256": original["document_sha256"],
            "script_id": script_id, "script_revision": script_revision,
            "script_document_sha256": script["document_sha256"],
            "overlay_timeline_id": overlay_timeline_id,
            "overlay_timeline_revision": derived["revision"],
            "overlay_timeline_sha256": derived["document_sha256"],
            "selected": ordered,
            "retained_earlier_performances": sorted(set(retained_old)),
            "explicit_director_retention_reason": preservation_reason,
            "all_original_take_events_preserved": True,
            "original_take_scene_and_sound_unchanged": True,
            "older_scene_dialogue_revision_retained": True,
            "recorded_audio_mixed_or_mastered": False,
            "final_visual_render_approved": False,
        }
        dependencies = [
            {"object_id": source_take_id, "revision": 1, "role": "source_take"},
            {"object_id": script_id, "revision": script_revision, "role": "dialogue"},
            {"object_id": overlay_timeline_id, "revision": derived["revision"],
             "role": "temporal"},
            *[{"object_id": x["performance_id"], "revision": 1, "role": "performance"}
              for x in ordered],
        ]
        return self.index.register_revision(
            pid, selection_id, "presentation", result,
            expected_revision=expected_selection_revision, dependencies=dependencies)
