"""Bounded metadata traversal for legacy finished review catalog.

Returns explicit continuation; no whole-library list or media loading. A
filtered page can have no matching review objects but still have a cursor.
"""
def object_window(index, project_id, kind, *, after=None, limit=64):
    if type(limit) is not int or not 1<=limit<=256:
        raise ValueError('Bounded review window required')
    left=limit; items=[]; cursor=after
    while left:
        result=index.object_page(project_id,kind=kind,after=cursor,limit=min(left,64))
        rows=result['items']; next_after=result['next_after']
        if len(rows)>min(left,64) or (next_after is not None and (not rows or next_after==cursor)):
            raise RuntimeError('FilmIndex pagination contract violated')
        items.extend(rows);left-=len(rows);cursor=next_after
        if cursor is None:break
    return items,cursor
