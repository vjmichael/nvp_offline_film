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
                         JOIN bible_facts f ON f.entity_id=e.id AND f.project_id=e.project_id
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
    fingerprint_source = {'entities': entities, 'links': links,
                          'scope': 'whole_project' if scene_id is None else 'linked_scene',
                          'scene_id': scene_id}
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
        for fact in entity['facts']:
            line = f"{header}\n  {fact['key']} [scope={fact['scope']}]: {fact['value']}"
            if used + len(line) + 1 > MAX_BIBLE_PROMPT:
                break
            text.append(line)
            used += len(line) + 1
            included += 1
    if scene_id is not None and not links:
        text.insert(0, "[NO APPROVED BIBLE ENTITIES LINKED TO THIS SCENE; DO NOT INVENT CANON]")
    if total_facts > included:
        text.append(f"[{total_facts - included} APPROVED FACT(S) OMITTED DUE TO CONTEXT LIMIT; do not assume omitted details]")
    return {
        'digest': digest, 'scene_id': scene_id, 'entities_count': len(entities),
        'facts_total': total_facts, 'facts_included': included,
        'text': '\n'.join(text) or 'No creator-approved Story Bible facts in this scope.',
        'limitations': ('Only creator-approved facts are authoritative. Story scopes are labels, '
                        'not an inferred timeline: e.g. after_reveal does not imply which '
                        'screenplay scene follows the reveal. A scene-specific request uses '
                        'explicit manual scene links only; unlinked entities are not included.'),
    }
