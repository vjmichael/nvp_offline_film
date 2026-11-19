"""Compact active revision over exact immutable editorial sections.

The existing G07 edit head and revision table remain authoritative. A paged
revision is deliberately not a finite EDL and grants no media/worker authority.
"""
import hashlib
import json
import re
import sqlite3
from backend.nvp_g06_filming import _json, _sha, HEX
from backend.nvp_temporal_ledger import MAX_TICK

FORMAT = 'nvp.g07.paged_active_edit.v1'
MAX_IDENTITY_BYTES = 16 * 1024 * 1024
SHA = re.compile(r'[a-f0-9]{64}\Z')


def check(document):
    if (type(document) is not dict or set(document) != {'format','section_id','section_digest','title','notes','master_gain','clip_count','duration_tick','ordered_cuts_sha256'} or
            document['format'] != FORMAT or not isinstance(document['section_id'],str) or not HEX.fullmatch(document['section_id']) or
            any(not isinstance(document[k],str) or not SHA.fullmatch(document[k]) for k in ('section_digest','ordered_cuts_sha256')) or
            type(document['clip_count']) is not int or not 1 <= document['clip_count'] <= 64**3*250 or
            type(document['duration_tick']) is not int or not 1 <= document['duration_tick'] <= MAX_TICK or
            not isinstance(document['title'],str) or not 1 <= len(document['title']) <= 120 or
            not isinstance(document['notes'],str) or len(document['notes']) > 2000 or
            type(document['master_gain']) not in (int,float) or not 0 <= document['master_gain'] <= 4):
        raise RuntimeError('Saved section timeline identity changed')
    return document


def build(service, db, pid, root, sha):
    """Stream all leaf cuts before approval. No complete clip list or media read.

    Duplicate-ID rejection uses a private, strictly capped in-memory SQLite
    index. It never spills plaintext IDs to disk. Exhaustion fails closed.
    """
    digest=hashlib.sha256(); count=0; end=0; settings=None
    index=sqlite3.connect(':memory:')
    try:
        index.execute('PRAGMA temp_store=MEMORY')
        index.execute('PRAGMA page_size=4096')
        index.execute(f'PRAGMA max_page_count={MAX_IDENTITY_BYTES//4096}')
        index.execute('CREATE TABLE seen(id TEXT PRIMARY KEY) WITHOUT ROWID')
        for source, segment in service._walk_cuts(db,pid,root,0,root['clip_count']):
            if service.access_guard: service.access_guard()
            pair=(source['master_gain'],source['notes'])
            if settings is None: settings=pair
            elif pair!=settings: raise ValueError('Reconcile film notes and master sound before grouping')
            try: index.execute('INSERT INTO seen VALUES(?)',(segment['clip_id'],))
            except sqlite3.IntegrityError as exc: raise ValueError('Sections reuse a clip identity; choose non-overlapping sections') from exc
            except sqlite3.OperationalError as exc: raise ValueError('This arrangement exceeds the safe review capacity') from exc
            # Each record includes original digest, exact global clock, trims and
            # presentation decisions. Newlines delimit canonical JSON records.
            if segment['index']!=count or segment['start_tick']!=end-segment['transition']['duration_tick'] or segment['end_tick']<=end:
                raise RuntimeError('Grouped cut clock changed')
            digest.update(_json(segment).encode('utf8')+b'\n');count+=1;end=segment['end_tick']
    finally:index.close()
    if settings is None or count!=root['clip_count'] or end!=root['duration_tick']:
        raise RuntimeError('Grouped cut coverage changed')
    return check({'format':FORMAT,'section_id':root['section_id'],'section_digest':sha,'title':root['title'],'notes':settings[1],
                  'master_gain':settings[0],'clip_count':count,'duration_tick':end,'ordered_cuts_sha256':digest.hexdigest()})
