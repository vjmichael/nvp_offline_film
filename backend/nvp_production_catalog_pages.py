"""Bounded read-only catalog navigation for the existing native production host.

Only fixed table/column names; callers authenticate the project before reading.
Catalog headers are recorded metadata, not proof of source or delivered media.
"""
import re

MAX_PAGE = 64
ID = re.compile(r'[A-Za-z0-9_-]{1,128}\Z')


def validate_page(after, limit):
    if type(limit) is not int or not 1 <= limit <= MAX_PAGE:
        raise ValueError('Bounded production catalog page required')
    if after is not None and (type(after) not in (tuple, list) or len(after) != 2
            or type(after[0]) is not str or not 1 <= len(after[0]) <= 128
            or type(after[1]) is not str or not ID.fullmatch(after[1])):
        raise ValueError('Invalid production catalog cursor')
    return tuple(after) if after is not None else None


def page(db, project_id, *, kind, after=None, limit=32, project_db=None):
    after = validate_page(after, limit)
    if kind == 'jobs':
        table, id_col = 'production_jobs', 'job_id'
        columns = 'job_id,state,task_kind,updated_at,created_at'
        scope, args = 'project_id=?', [project_id]
    elif kind == 'features':
        if type(project_db) is not str or not project_db:
            raise PermissionError('Exact protected project storage required')
        table, id_col = 'production_features', 'feature_id'
        columns = ('feature_id,state,assembly_sha256,manifest_sha256,'
                   'cancel_requested,updated_at,created_at')
        scope, args = 'project_id=? AND project_db=?', [project_id, project_db]
    else:
        raise ValueError('Unknown production catalog')
    if after is not None:
        # Do not accept a cursor from another project or store (a forged
        # valid-looking ID cannot change the authorized scope).
        if db.execute(f'SELECT 1 FROM {table} WHERE {scope} AND created_at=? AND {id_col}=?',
                      (*args, *after)).fetchone() is None:
            raise PermissionError('Production catalog cursor outside current project')
        scope += f' AND (created_at,{id_col})>(?,?)'
        args.extend(after)
    rows = db.execute(f'SELECT {columns} FROM {table} WHERE {scope} '
                      f'ORDER BY created_at,{id_col} LIMIT ?', (*args,limit+1)).fetchall()
    more = len(rows)>limit
    rows = rows[:limit]
    cursor = [rows[-1]['created_at'],rows[-1][id_col]] if more else None
    values=[]
    for row in rows:
        record=dict(row); record.pop('created_at'); values.append(record)
    return values,cursor
