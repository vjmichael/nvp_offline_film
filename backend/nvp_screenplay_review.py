"""Evidence-backed, deliberately narrow screenplay-to-canon continuity reviewer.

This is NOT semantic screenplay understanding. It recognizes a documented set of
literal physical descriptions and first-person dialogue claims, preserves exact
line evidence, and emits *review suggestions*, not canon corrections. A character
can lie, misremember, or perform in nonchronological scenes. All decisions are
explicit and are invalidated by changed source evidence or creator-approved canon.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid

from backend.nvp_studio import Studio, parse_screenplay, CHARACTER_CUE, CUE_SUFFIX
from backend.nvp_story_bible import StoryBible, sha_scene, timestamp, checked_text

SUPPORTED_SLOTS = ('can_drive', 'cannot_drive', 'can_swim', 'cannot_swim', 'alive', 'eye_color')
EYE_COLORS = 'blue|brown|green|gray|grey|hazel|amber|black|violet'
BOOLEAN_TRUE = {'true', 'yes', '1'}
BOOLEAN_FALSE = {'false', 'no', '0'}
MAX_REVIEW_SUGGESTIONS = 500


def _hash(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False,
                separators=(',', ':')).encode('utf-8')).hexdigest()


def _normalize_fact(key: str, value: str) -> str | None:
    v = re.sub(r'\s+', ' ', value.casefold().strip().rstrip('.'))
    if key == 'eye_color':
        return 'gray' if v == 'grey' else v if v in EYE_COLORS.split('|') else None
    if key == 'alive':
        if v in BOOLEAN_TRUE | {'alive', 'living'}: return 'yes'
        if v in BOOLEAN_FALSE | {'dead', 'deceased'}: return 'no'
        return None
    if key in ('can_drive', 'can_swim'):
        subject = 'drive' if key == 'can_drive' else 'swim'
        if v in BOOLEAN_TRUE | {f'can {subject}', f'able to {subject}'}: return 'yes'
        if v in BOOLEAN_FALSE | {f'cannot {subject}', f"can't {subject}", f'unable to {subject}'} or f'never learned to {subject}' in v: return 'no'
        return None
    if key in ('cannot_drive', 'cannot_swim'):
        subject = 'drive' if key == 'cannot_drive' else 'swim'
        if v in BOOLEAN_TRUE | {f'cannot {subject}', f"can't {subject}", f'unable to {subject}'} or f'never learned to {subject}' in v:
            return 'no'
        if v in BOOLEAN_FALSE | {f'can {subject}', f'able to {subject}'}:
            return 'yes'
    return None


def _kind(key: str) -> str:
    return ('can_drive' if key in ('can_drive', 'cannot_drive') else
            'can_swim' if key in ('can_swim', 'cannot_swim') else key)


def _cue_actor(line: str, names: dict[str, set[str]]) -> str | None:
    cue = CUE_SUFFIX.sub('', line.strip()).casefold()
    if not CHARACTER_CUE.fullmatch(line.strip()):
        return None
    options = names.get(cue, set())
    return next(iter(options)) if len(options) == 1 else None


def _extract_claims(scene: dict, actors: list[dict]) -> list[dict]:
    """High precision patterns; never infer from general dialogue or adjectives.

    The Fountain parser is conservative. Only an exact, unambiguous known
    character cue followed by one explicit first-person utterance is interpreted
    as dialogue. Narration must name the character. Quoted speech in narration,
    speculative sentences, questions and conditional sentences are excluded.
    """
    characters = [actor for actor in actors if actor['kind'] == 'character']
    names: dict[str, set[str]] = {}
    for actor in characters:
        for name in [actor['name']] + actor['aliases']:
            names.setdefault(name.casefold(), set()).add(actor['id'])
    ordered = sorted(((name, owners) for name, owners in names.items() if len(owners) == 1),
                     key=lambda item: (-len(item[0]), item[0]))
    lines = scene['text'].splitlines()
    utterances: dict[int, tuple[str, int]] = {}
    for index, line in enumerate(lines):
        actor_id = _cue_actor(line, names)
        if not actor_id:
            continue
        # A dialogue line must be the next nonempty line; do not treat a later
        # unrelated action or actor cue as that person's statement.
        target = index + 1
        while target < len(lines) and not lines[target].strip():
            target += 1
        if target < len(lines) and target - index <= 2 and lines[target].strip() and not CHARACTER_CUE.fullmatch(lines[target].strip()):
            utterances[target] = (actor_id, index + 1)
    claims = []

    def record(actor_id: str, slot: str, value: str, line_number: int,
               kind: str, quote: str, matched: str, cue_line: int | None = None):
        claims.append({'character_id': actor_id, 'slot': slot,
            'observed_value': value, 'source_kind': kind,
            'scene_id': scene['id'], 'scene_heading': scene['heading'],
            'scene_line': line_number, 'screenplay_line': scene['start_line'] + line_number - 1,
            'quote': quote, 'matched_phrase': matched, 'cue_scene_line': cue_line})

    for index, line in enumerate(lines):
        body = line.strip()
        if not body or body.endswith('?') or body.lower().startswith(('if ', 'maybe ', 'perhaps ')):
            continue
        if index in utterances:
            character_id, cue_line = utterances[index]
            # Require an explicit *literal* first-person claim near sentence start.
            for pattern, slot, value in (
                (r'^I (?:can not|cannot|can\'t|could never) drive\b', 'can_drive', 'no'),
                (r'^I can drive\b', 'can_drive', 'yes'),
                (r'^I (?:cannot|can\'t) swim\b', 'can_swim', 'no'),
                (r'^I can swim\b', 'can_swim', 'yes'),
                (rf'^My eyes are ({EYE_COLORS})\b', 'eye_color', None),
            ):
                match = re.search(pattern, body, re.I)
                if match:
                    observed = (match.group(1).casefold().replace('grey', 'gray') if slot == 'eye_color' else value)
                    record(character_id, slot, observed, index + 1,
                           'dialogue', line, match.group(), cue_line)
                    break
            continue
        # Don't reclassify recognized character cues as narration.
        if _cue_actor(line, names):
            continue
        # Avoid quoted phrases (including double quotes, single-quoted lines,
        # and screenplay inline quotes). Speech must remain a claim, not canon.
        if '"' in line or '“' in line or '”' in line:
            continue
        for name, actor_ids in ordered:
            actor_id = next(iter(actor_ids))
            escaped = re.escape(name)
            prefix = rf'(?<![\w]){escaped}(?![\w])'
            checks = (
                (prefix + r'\s+(?:cannot|can\'t|does not know how to|doesn\'t know how to) drive\b', 'can_drive', 'no'),
                (prefix + r'\s+drives\s+(?:a |the |her |his )?(?:car|truck|van|bus|vehicle|sedan|jeep|taxi)\b', 'can_drive', 'yes'),
                (prefix + r'\s+(?:cannot|can\'t) swim\b', 'can_swim', 'no'),
                (prefix + r'\s+swims\s+(?:across|through|in)\b', 'can_swim', 'yes'),
                (prefix + r'\s+is\s+alive\b', 'alive', 'yes'),
                (prefix + r'\s+is\s+dead\b', 'alive', 'no'),
                (prefix + rf"['’]s\s+eyes\s+are\s+({EYE_COLORS})\b", 'eye_color', None),
                (prefix + rf'\s+has\s+({EYE_COLORS})\s+eyes\b', 'eye_color', None),
            )
            for pattern, slot, value in checks:
                match = re.search(pattern, body, re.I)
                if match:
                    # Skip common hypothetical/negated constructions preceding the match.
                    before = body[:match.start()].casefold()
                    if re.search(r'\b(?:if|whether|imagine|suppose|pretends?|says?|claims?)\b', before):
                        continue
                    observed = (match.group(1).casefold().replace('grey', 'gray') if slot == 'eye_color' else value)
                    record(actor_id, slot, observed, index + 1, 'narration', line, match.group())
                    break
    # Screenplay is bounded to 1 MB by Studio; explicit cap keeps response safe.
    return claims[:1000]


class ScreenplayContinuityReview:
    def __init__(self, studio: Studio):
        self.studio = studio
        StoryBible(studio)
        with self.studio._connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS screenplay_review_state (
                    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
                    revision INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS screenplay_review_decisions (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    scene_id TEXT NOT NULL, decision TEXT NOT NULL CHECK(decision IN ('accept','reject')),
                    resolution TEXT NOT NULL, note TEXT NOT NULL, evidence_json TEXT NOT NULL,
                    screenplay_revision INTEGER NOT NULL, decided_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS screenplay_review_decisions_by_project
                    ON screenplay_review_decisions(project_id, scene_id);
            ''')

    @staticmethod
    def _version(db, project_id: str) -> int:
        row = db.execute('SELECT revision FROM screenplay_review_state WHERE project_id=?',
                         (project_id,)).fetchone()
        return row['revision'] if row else 0

    @staticmethod
    def _data(db, project_id: str, scene_id: str) -> tuple[dict, int, list[dict]]:
        row = db.execute('SELECT screenplay,revision FROM projects WHERE id=?', (project_id,)).fetchone()
        if row is None:
            raise KeyError('Film project not found')
        scenes = parse_screenplay(row['screenplay'])
        scene = next((s for s in scenes if s['id'] == scene_id), None)
        if scene is None:
            raise KeyError('Scene no longer belongs to this film')
        actors = [dict(x) for x in db.execute('SELECT id,kind,name FROM bible_entities '
                   'WHERE project_id=? AND kind=\'character\' ORDER BY id', (project_id,))]
        for a in actors:
            a['aliases'] = [r['display_name'] for r in db.execute(
                    'SELECT display_name FROM bible_names WHERE project_id=? AND entity_id=? '
                    'AND is_primary=0 ORDER BY normalized_name', (project_id,a['id']))]
        return scene, row['revision'], actors

    @staticmethod
    def _approved(db, project_id: str) -> dict[tuple[str, str], dict]:
        result = {}
        for row in db.execute('''SELECT id,entity_id,fact_key,fact_value,story_scope
                               FROM bible_facts WHERE project_id=? AND status='accepted' ''',
                              (project_id,)):
            entry = dict(row)
            if entry['story_scope'] != 'global':
                continue  # Never infer where a relative story scope applies.
            slot = _kind(entry['fact_key'])
            value = _normalize_fact(entry['fact_key'], entry['fact_value'])
            if slot in {'can_drive','can_swim','alive','eye_color'} and value is not None:
                result[(entry['entity_id'], slot)] = {**entry, 'normalized_value': value}
        return result

    @staticmethod
    def _contextual_statement(db, project_id: str, scene_id: str,
                               character_id: str, fact_id: str) -> dict | None:
        # An already-reviewed declaration of deceptive intent is *context*,
        # not a guarantee that the text refers to precisely that statement.
        try:
            row = db.execute('''SELECT s.id,s.intent,s.claimed_value FROM scene_mind_statements s
                JOIN scene_mind_beats b ON b.id=s.beat_id WHERE s.project_id=?
                AND b.scene_id=? AND s.speaker_id=? AND s.fact_id=? AND s.status='accepted'
                ORDER BY b.line_number LIMIT 1''', (project_id,scene_id,character_id,fact_id)).fetchone()
            return dict(row) if row else None
        except Exception as exc:
            # The standalone review can be run without the scene-mind module,
            # but absence of a table is the only supported graceful fallback.
            import sqlite3
            if isinstance(exc, sqlite3.OperationalError) and 'no such table' in str(exc):
                return None
            raise

    @classmethod
    def _candidates(cls, db, project_id: str, scene_id: str) -> tuple[list[dict], int, str]:
        scene, revision, actors = cls._data(db, project_id, scene_id)
        canon = cls._approved(db, project_id)
        facts = _extract_claims(scene, actors)
        results = []
        scene_hash = sha_scene(scene)

        def append(kind: str, title: str, evidence: list[dict],
                   fact: dict | None = None, explanation: str = '') -> None:
            source = {'kind': kind, 'project_id': project_id, 'scene_id': scene_id, 'scene_sha': scene_hash,
                      'evidence': evidence,
                      'canon_fact_id': fact['id'] if fact else None,
                      'canon_value': fact['fact_value'] if fact else None}
            digest = _hash(source)
            results.append({'id': digest, 'kind': kind, 'scene_id': scene_id,
                            'title': title, 'evidence': evidence,
                            'canon': fact, 'explanation': explanation,
                            'suggested_action': ('Review dialogue intent or character belief' if
                                  kind.startswith('dialogue') else 'Review the intended scene description'),
                            'confidence': 'pattern_match_only',
                            'status': 'proposed', 'resolution': '', 'review_note': ''})

        narration = {}
        for claim in facts:
            if claim['source_kind'] == 'narration':
                narration.setdefault((claim['character_id'], claim['slot']), []).append(claim)
            truth = canon.get((claim['character_id'], claim['slot']))
            if truth is None or truth['normalized_value'] == claim['observed_value']:
                continue
            contextual = None
            if claim['source_kind'] == 'dialogue':
                contextual = cls._contextual_statement(db, project_id, scene_id,
                                    claim['character_id'], truth['id'])
            evidence = [claim]
            if claim['source_kind'] == 'dialogue':
                append('dialogue_canon_tension',
                       'A character says something different from approved canon', evidence,
                       truth, ('A related approved scene-mind statement exists: '
                               + contextual['intent'] + '. This could be deception or error.'
                               if contextual else 'Dialogue can be a lie, bluff, or mistaken belief; do not treat it as objective truth.'))
            else:
                append('narration_canon_mismatch',
                       'Scene narration conflicts with an approved global fact', evidence,
                       truth, 'The wording is an explicit pattern match, not semantic proof. Check scope and context.')

        for (character_id, slot), claims in narration.items():
            seen = {}
            for claim in claims:
                for old_value, previous in seen.items():
                    if old_value != claim['observed_value']:
                        append('narration_internal_tension',
                               'Two descriptions in one scene appear inconsistent',
                               [previous, claim], None,
                               'Flashbacks, dreams or transformations within the scene may explain the difference.')
                seen.setdefault(claim['observed_value'], claim)

        return sorted(results, key=lambda r: (r['evidence'][0]['scene_line'],r['kind'],r['id']))[:MAX_REVIEW_SUGGESTIONS], revision, scene_hash

    @classmethod
    def _report(cls, db, project_id: str, scene_id: str) -> dict:
        suggestions, screenplay_revision, scene_hash = cls._candidates(db,project_id,scene_id)
        reviews = {r['id']: dict(r) for r in db.execute('SELECT * FROM screenplay_review_decisions '
                                                  'WHERE project_id=? AND scene_id=?', (project_id,scene_id))}
        for suggestion in suggestions:
            review = reviews.get(suggestion['id'])
            if review:
                suggestion['status'] = review['decision']
                suggestion['resolution'] = review['resolution']
                suggestion['review_note'] = review['note']
        return {'scene_id': scene_id,'scene_sha':scene_hash,
                'screenplay_revision':screenplay_revision,
                'review_revision':cls._version(db,project_id),
                'suggestions': suggestions,
                'counts': {'candidate_count':len(suggestions),
                          'unreviewed':sum(s['status']=='proposed' for s in suggestions)},
                'limitations': ('Only exact supported phrase templates and approved global fact values '
                               'are reviewed. This is NOT open-ended semantic contradiction detection. '
                               'Dialogue and narration are separated; relative story scopes, event '
                               'ordering, subtext and intent are not inferred.')}

    def report(self, project_id: str, scene_id: str) -> dict:
        with self.studio._connection() as db:
            return self._report(db,project_id,scene_id)

    def history(self, project_id: str, scene_id: str | None = None, limit: int = 100) -> dict:
        """All reviewed suggestions remain auditable after script/canon revisions."""
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError('Review history page size must be between 1 and 200')
        with self.studio._connection() as db:
            project = db.execute('SELECT screenplay FROM projects WHERE id=?', (project_id,)).fetchone()
            if project is None:
                raise KeyError('Film project not found')
            args = (project_id, scene_id, limit) if scene_id is not None else (project_id, limit)
            sql = ('SELECT * FROM screenplay_review_decisions WHERE project_id=? '
                   + ('AND scene_id=? ' if scene_id is not None else '')
                   + 'ORDER BY decided_at DESC,id DESC LIMIT ?')
            records = [dict(row) for row in db.execute(sql, args)]
            by_scene = {s['id'] for s in parse_screenplay(project['screenplay'])}
            current_ids: dict[str, set[str]] = {}
            for record in records:
                if record['scene_id'] not in current_ids:
                    if record['scene_id'] not in by_scene:
                        current_ids[record['scene_id']] = set()
                    else:
                        current_ids[record['scene_id']] = {s['id'] for s in
                              self._candidates(db, project_id, record['scene_id'])[0]}
                record['is_current_evidence'] = record['id'] in current_ids[record['scene_id']]
                record['evidence'] = json.loads(record.pop('evidence_json'))
            return {'project_id': project_id, 'history': records,
                    'limit': limit, 'truncated_possible': len(records) == limit,
                    'limitations': 'Old reviews are immutable audit history, not approvals of revised evidence.'}

    def decide(self, project_id: str, scene_id: str, suggestion_id: str,
               decision: str, expected_review_revision: int,
               expected_screenplay_revision: int,
               resolution: str = '', note: str = '') -> dict:
        if decision not in {'accept','reject'}:
            raise ValueError('Decision must be accept or reject')
        if decision == 'accept' and resolution not in {'intentional','fix_later'}:
            raise ValueError('Accepted review requires intentional or fix_later resolution')
        if decision == 'reject' and resolution != '':
            raise ValueError('Rejected review must not include a resolution')
        note = checked_text(note, 1200, 'review note', required=False)
        if not isinstance(expected_review_revision, int) or isinstance(expected_review_revision, bool):
            raise ValueError('Review revision must be an integer')
        if not isinstance(expected_screenplay_revision, int) or isinstance(expected_screenplay_revision, bool):
            raise ValueError('Screenplay revision must be an integer')
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            suggestions, screenplay_revision, _ = self._candidates(db,project_id,scene_id)
            if screenplay_revision != expected_screenplay_revision:
                raise RuntimeError('Screenplay changed; refresh the evidence and review it again')
            if self._version(db, project_id) != expected_review_revision:
                raise RuntimeError('Review changed; refresh before deciding')
            selected = next((r for r in suggestions if r['id']==suggestion_id), None)
            if selected is None:
                raise RuntimeError('Evidence or approved canon changed; refresh the suggestion')
            if db.execute('SELECT 1 FROM screenplay_review_decisions WHERE id=?',
                          (suggestion_id,)).fetchone():
                raise RuntimeError('Suggestion already reviewed')
            db.execute('INSERT INTO screenplay_review_decisions VALUES (?,?,?,?,?,?,?,?,?)',
                       (suggestion_id,project_id,scene_id,decision,resolution,note,
                        json.dumps(selected,ensure_ascii=False),screenplay_revision,timestamp()))
            db.execute('INSERT OR IGNORE INTO screenplay_review_state VALUES (?,0)', (project_id,))
            db.execute('UPDATE screenplay_review_state SET revision=revision+1 WHERE project_id=?',
                       (project_id,))
        return self.report(project_id,scene_id)
