"""Deterministic, bounded approved-Story-Bible context for offline writing.

All data is read from the caller's already-open SQLite transaction. A digest
covers *all* selected canon (including omitted prompt text); the writer cannot
silently accept a draft after any relevant accepted fact, name, or link changes.
"""
from __future__ import annotations

import hashlib
import json

from backend.nvp_studio import parse_screenplay
from backend.nvp_story_bible import sha_scene
from backend.nvp_story_timeline import timeline_snapshot
from backend.nvp_scene_mind import scene_mind_snapshot

MAX_BIBLE_PROMPT = 8500


def canon_snapshot(db, project_id: str, scene_id: str | None = None) -> dict:
    project = db.execute("SELECT screenplay FROM projects WHERE id=?", (project_id,)).fetchone()
    if project is None:
        raise KeyError("Film project not found")
    if scene_id is not None and not isinstance(scene_id, str):
        raise ValueError("Invalid selected screenplay scene")
    if scene_id is not None:
        scene = next((s for s in parse_screenplay(project['screenplay']) if s['id'] == scene_id), None)
        if scene is None:
            raise KeyError("Selected scene is not in the current screenplay")
    else:
        scene = None
    rows = db.execute("""SELECT e.id, e.kind, e.name, n.display_name AS alias,
                              f.id AS fact_id, f.fact_key, f.fact_value, f.story_scope
                         FROM bible_entities e
                         LEFT JOIN bible_facts f ON f.entity_id=e.id AND f.project_id=e.project_id
                              AND f.status='accepted'
                         LEFT JOIN bible_names n ON n.entity_id=e.id AND n.is_primary=0
                        WHERE e.project_id=? ORDER BY e.kind,e.id,f.id,n.normalized_name""",
                      (project_id,)).fetchall()
    grouped = {}
    for r in rows:
        row = dict(r)
        entry = grouped.setdefault(row['id'], {
            'id': row['id'], 'kind': row['kind'], 'name': row['name'],
            'aliases': set(), 'facts': {}
        })
        if row['alias'] is not None:
            entry['aliases'].add(row['alias'])
        if row['fact_id'] is not None:
            entry['facts'][row['fact_id']] = {
                'id': row['fact_id'], 'key': row['fact_key'],
                'value': row['fact_value'], 'scope': row['story_scope'],
            }
    links = []
    if scene is not None:
        links = [dict(row) for row in db.execute(
            """SELECT entity_id,scene_id,scene_sha,note FROM bible_scene_links
                WHERE project_id=? AND scene_id=? ORDER BY entity_id""",
            (project_id, scene_id)).fetchall()]
        # A stale explicit link must be reaffirmed rather than silently reused.
        if any(link['scene_sha'] != sha_scene(scene) for link in links):
            raise RuntimeError("Linked Story Bible scene changed; refresh its references before generating")
        allowed = {row['entity_id'] for row in links}
        grouped = {key: entity for key, entity in grouped.items() if key in allowed}
    entities = []
    for entry in sorted(grouped.values(), key=lambda e: (e['kind'], e['name'].casefold(), e['id'])):
        entities.append({
            'id': entry['id'], 'kind': entry['kind'], 'name': entry['name'],
            'aliases': sorted(entry['aliases']),
            'facts': sorted(entry['facts'].values(), key=lambda f: (f['key'], f['scope'], f['id'])),
        })
    # The hash includes facts beyond the prompt budget, and exact selected
    # link identity. Unapproved/rejected/superseded facts never enter it.
    temporal = timeline_snapshot(db, project_id, scene_id, relevant_entity_ids=set(grouped))
    mind = scene_mind_snapshot(db, project_id, scene_id)
    fingerprint_source = {'entities': entities, 'links': links,
                          'scope': 'whole_project' if scene_id is None else 'linked_scene',
                          'scene_id': scene_id}
    if temporal['digest_payload'] is not None:
        fingerprint_source['timeline'] = temporal['digest_payload']
    if mind['digest_payload'] is not None:
        fingerprint_source['scene_mind'] = mind['digest_payload']
    digest = hashlib.sha256(json.dumps(fingerprint_source, sort_keys=True,
                                        ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    text = []
    used = 0
    total_facts = sum(len(entity['facts']) for entity in entities)
    included = 0
    for entity in entities:
        header = f"[{entity['kind'].upper()}] {entity['name']} (ID {entity['id']})"
        if entity['aliases']:
            header += " | aliases: " + ', '.join(entity['aliases'])
        for fact in entity['facts'] or [None]:
            line = (f"{header}\n  {fact['key']} [scope={fact['scope']}]: {fact['value']}"
                    if fact is not None else header + "\n  [no approved facts yet]")
            if used + len(line) + 1 > MAX_BIBLE_PROMPT:
                break
            text.append(line)
            used += len(line) + 1
            if fact is not None:
                included += 1
    if scene_id is not None and not links:
        text.insert(0, "[NO APPROVED BIBLE ENTITIES LINKED TO THIS SCENE; DO NOT INVENT CANON]")
    if total_facts > included:
        text.append(f"[{total_facts - included} APPROVED FACT(S) OMITTED DUE TO CONTEXT LIMIT; do not assume omitted details]")
    # Keep chronological knowledge separate from objective canon. A fact can
    # be true while a specific character has not learned it yet.
    knowledge_lines = []
    # An event graph is a partial order. Only direct author-approved edges
    # are provided, never assumed chronology based on scene display order.
    names = {event['id']: event['name'] for event in temporal['events']}
    used_order = 0
    for edge in temporal['edges']:
        line = (f"[APPROVED STORY ORDER] {names.get(edge['before_id'], '?')} "
                f"BEFORE {names.get(edge['after_id'], '?')}")
        if used_order + len(line) + 1 > 2400:
            knowledge_lines.append('[ADDITIONAL STORY ORDER EDGES OMITTED; do not assume missing order]')
            break
        knowledge_lines.append(line)
        used_order += len(line) + 1
    marker = temporal['scene_marker']
    if scene_id is not None:
        if marker:
            knowledge_lines.append(
                f"[EXPLICIT SCENE POINT] {marker['phase'].upper()} event {marker['anchor_event_id']}")
        else:
            knowledge_lines.append("[NO AUTHOR-APPROVED SCENE TIME ANCHOR: knowledge timing is unverified]")
    for entry in temporal['knowledge']:
        # Never present a superseded truth as current canon, even as a quoted
        # character-knowledge item. Expose only an auditable stale reference.
        if entry['state'] == 'source_fact_changed':
            line = (f"[KNOWLEDGE: SOURCE_FACT_CHANGED] {entry['character_name']} "
                    f"(knowledge ID {entry['id']}); source fact is no longer approved. "
                    "Review and create a new knowledge approval.")
        else:
            line = (f"[KNOWLEDGE: {entry['state'].upper()}] {entry['character_name']} — "
                    f"{entry['fact_key']}: {entry['fact_value']} "
                    f"(learned at {entry['learned_at_name'] or 'story start'}; "
                    f"scope={entry['story_scope']})")
        if len('\n'.join(knowledge_lines)) + len(line) > 3200:
            knowledge_lines.append('[ADDITIONAL KNOWLEDGE OMITTED: cannot infer character awareness]')
            break
        knowledge_lines.append(line)
    timeline_text = '\n'.join(knowledge_lines) if knowledge_lines else 'No approved character-knowledge timing assertions.'
    # Film-specific epistemic snapshots: statements and subjective beliefs are
    # not objective truth. Only creator-accepted records can reach the model.
    names_by_id = {r['id']: r['name'] for r in db.execute(
        "SELECT id,name FROM bible_entities WHERE project_id=?", (project_id,))}
    beat_by_id = {b['id']: b for b in mind['beats']}
    stale_beats = set(mind['stale_beat_ids'])
    mind_lines = []
    for record in mind['changes']:
        if record['status'] != 'accepted':
            continue
        if record['beat_id'] in stale_beats:
            continue
        owner = names_by_id.get(record['character_id'], '[missing character]')
        beat = beat_by_id[record['beat_id']]
        if record['source_state'] != 'current':
            mind_lines.append(f"[BELIEF: SOURCE_FACT_CHANGED] {owner} at {beat['label']}; "
                              'previous fact is no longer approved; review before reuse')
            continue
        if record['mode'] == 'learn_truth':
            state = 'KNOWS_TRUE'
            value = record['world_value']
        elif record['mode'] == 'believe':
            state = ('BELIEVES_TRUE' if record['belief_value'] == record['world_value']
                     else 'BELIEVES_FALSE')
            value = record['belief_value']
        elif record['mode'] == 'doubt':
            state, value = 'DOUBTS', '[uncertain]'
        else:
            state, value = 'DOES_NOT_RECALL', '[not recalled]'
        mind_lines.append(f"[BELIEF: {state}] {owner} at beat {beat['label']} "
                          f"(scene line {beat['line_number']}) — {record['fact_key']} "
                          f"believed/known as {value}; distinct from world canon")
    for record in mind['statements']:
        if record['status'] != 'accepted' or record['beat_id'] in stale_beats:
            continue
        beat = beat_by_id[record['beat_id']]
        speaker = names_by_id.get(record['speaker_id'], '[missing speaker]')
        audience = names_by_id.get(record['audience_id'], '[missing listener]')
        if record['source_state'] != 'current':
            mind_lines.append(f"[STATEMENT: SOURCE_FACT_CHANGED] {speaker} to {audience} "
                              f"at {beat['label']}; review superseded canon")
            continue
        mind_lines.append(f"[STATEMENT: {record['intent'].upper()}] {speaker} to {audience} "
                          f"at beat {beat['label']} (scene line {beat['line_number']}): "
                          f"claims {record['fact_key']} = {record['claimed_value']}; "
                          'listener belief is NOT implied')
    if stale_beats:
        mind_lines.append('[STALE SCENE BEATS OMITTED: re-anchor them to updated screenplay]')
    for review in mind['reviews']:
        if review['decision'] != 'accept':
            continue  # rejection is a dismissal, never an instruction to model
        note = review['review_note'] or '[no explanation supplied]'
        mind_lines.append(f"[CREATOR CONTINUITY REVIEW: {review['resolution'].upper()}] "
                          f"{note}; this review does not change world canon or screenplay")
    full_mind_lines = '\n'.join(mind_lines)
    # Bound the presentation and disclose truncation. Digest above covers all
    # the accepted records even when they do not fit this smaller budget.
    if len(full_mind_lines) > 3500:
        full_mind_lines = full_mind_lines[:3500] +             '\n[ADDITIONAL REVIEWED MIND RECORDS OMITTED; do not invent knowledge]'
    mind_text = full_mind_lines or 'No creator-approved within-scene belief or disclosure changes.'
    return {
        'scene_mind': {'text': mind_text, 'limitations': mind['limitations'],
                       'states': mind['states'], 'reviews': mind['reviews'],
                       'stale_beat_ids': mind['stale_beat_ids']},
        'timeline': {'scene_marker': marker, 'events': temporal['events'],
                     'edges': temporal['edges'], 'knowledge': temporal['knowledge'],
                     'text': timeline_text, 'limitations': temporal['limitations']},
        'digest': digest, 'scene_id': scene_id, 'entities_count': len(entities),
        'facts_total': total_facts, 'facts_included': included,
        'text': '\n'.join(text) or 'No creator-approved Story Bible facts in this scope.',
        'limitations': ('Only creator-approved facts are authoritative. Story scopes are labels, '
                        'not an inferred timeline: e.g. after_reveal does not imply which '
                        'screenplay scene follows the reveal. A scene-specific request uses '
                        'explicit manual scene links only; unlinked entities are not included. '
                        'A separate event graph governs character knowledge timing; never infer event order from screenplay position.'),
    }
