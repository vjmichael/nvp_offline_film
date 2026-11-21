"""Bounded read-only finished-review catalog windows and continuations."""
from backend.nvp_production_catalog_pages import validate_page

PAGE=32

def feature_window(db,pid,project_db,after=None,limit=PAGE):
    after=validate_page(after,limit)
    scope='project_id=? AND project_db=?';args=[pid,project_db]
    if after is not None:
        if db.execute('SELECT 1 FROM production_features WHERE '+scope+' AND created_at=? AND feature_id=?',(*args,*after)).fetchone() is None:
            raise PermissionError('Finished film cursor outside movie')
        scope+=' AND (created_at,feature_id)<(?,?)';args.extend(after)
    rows=[dict(r) for r in db.execute('''SELECT feature_id,assembly_id,assembly_revision,assembly_sha256,
                    project_id,state,updated_at,created_at FROM production_features WHERE '''+scope+
                    ' ORDER BY created_at DESC,feature_id DESC LIMIT ?',(*args,limit+1))]
    items=rows[:limit];next_after=[items[-1]['created_at'],items[-1]['feature_id']] if len(rows)>limit else None
    for r in items:r.pop('created_at')
    return items,next_after


def cursors(value):
    if value is None:return {'edit':None,'presentation':None,'features':None}
    if type(value) is not dict or set(value)!={'edit','presentation','features'}:
        raise ValueError('Invalid review navigation cursor')
    for k in ('edit','presentation'):
        v=value[k]
        if v is not None and (type(v) is not str or not 1<=len(v)<=128):raise ValueError('Invalid object cursor')
    validate_page(value['features'],PAGE)
    return dict(value)
