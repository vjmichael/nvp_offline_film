"""Bounded project-scoped filmmaker browsing of real immutable film sources."""
from backend.nvp_film_index import _id, _sha
from backend.nvp_temporal_ledger import _int, TICKS_PER_SECOND
from backend.nvp_slate_hierarchy import SlateHierarchy, FORMAT as GROUP
from backend.nvp_slate_paged_catalog import CATALOG_FORMAT
from backend.nvp_digital_slate_branches import GRAPH_FORMAT
from backend.nvp_slate_edit_assembly import FORMAT as EDIT

FORMAT='nvp.slate.filmmaker_navigation.v1'
P1DE_LEAF='nvp.p1de.source_edit_audio.v1'
P1DE_GROUP='nvp.p1de.source_edit_manifest.v2'
KINDS={'scenes':'scene','takes':'presentation','edit':'edit'}


class SlateNavigation:
    def __init__(self,index):
        self.index=index
        self.hierarchy=SlateHierarchy(index,approve=lambda *_:False)

    def _summary(self,row,family):
        d=row['data'];fmt=d.get('format')
        if fmt==GROUP and d.get('family')==family:
            label=d['title']; view='section';count=d['item_count']
        elif family=='takes' and fmt in (CATALOG_FORMAT,GRAPH_FORMAT):
            label=d['scene_label'];view='takes';count=d['branch_count'] if fmt==CATALOG_FORMAT else len(d['nodes'])
        elif family=='edit' and fmt==EDIT and d.get('explicit_editor_commit') is True:
            label=d.get('title') or row['object_id'];view='edit';count=len(d['segments'])
        elif family=='edit' and row['kind']=='edit' and fmt in (P1DE_LEAF,P1DE_GROUP) and all(d.get(k) is False for k in ('source_modified','flattened_soundtrack','picture_rendered','master_approved')):
            label=d.get('title') or row['object_id'];view='source_sections' if fmt==P1DE_GROUP else 'source_edit';count=len(d['children'] if fmt==P1DE_GROUP else d['segments'])
        elif family=='scenes' and row['kind']=='scene' and d.get('native_schema_version') is not None:
            label=d.get('title') or d.get('name') or row['object_id'];view='scene';count=None
        else:return None
        return {'object_id':row['object_id'],'revision':row['revision'],'document_sha256':row['document_sha256'],
                'label':label,'view':view,'item_count':count,'duration_tick':str(d.get('duration_tick',0))}

    def directory(self,pid,*,family,after=None,limit=32):
        if family not in KINDS:raise ValueError('Choose Scenes, Takes, or Edits')
        raw=self.index.object_page(pid,kind=KINDS[family],after=after,limit=limit)
        items=[]
        for meta in raw['items']:
            row=self.index.read_revision(pid,meta['object_id'],meta['head_revision'])
            summary=self._summary(row,family)
            if summary is not None:items.append(summary)
        return {'format':FORMAT,'project_id':pid,'family':family,'items':items,'next_after':raw['next_after'],
                'source_modified':False}

    def page(self,pid,ident,revision,*,digest,family,first=0,limit=32):
        _id(ident,'selected film section');_sha(digest)
        start=_int(first,'page position');n=_int(limit,'page size',minimum=1,maximum=64)
        if family not in KINDS:raise ValueError('Choose Scenes, Takes, or Edits')
        row=self.index.read_revision(pid,ident,revision);d=row['data'];summary=self._summary(row,family)
        if summary is None or row['document_sha256']!=digest:raise PermissionError('Original selection changed')
        items=[]; following=None
        if summary['view']=='section':
            self.hierarchy.open(pid,ident,revision)
            rows=d['children'];total=len(rows)
            for c in rows[start:start+n]:
                child=self.index.read_revision(pid,c['object_id'],c['revision']); info=self._summary(child,family)
                if info is None or child['document_sha256']!=c['document_sha256']:raise RuntimeError('Section source changed')
                items.append({**info,'start_tick':str(c['start_tick']),'end_tick':str(c['end_tick'])})
        elif summary['view'] in ('source_sections','source_edit'):
            # Reuse the original PERF-03B native editorial read and leaf checks.
            from backend.nvp_p1de_edit_audio import P1DEConform
            verified=P1DEConform(self.index,approve_edit=lambda *_:False).read(pid,ident,revision)
            d=verified['data']
            if summary['view']=='source_sections':
                rows=d['children'];total=len(rows)
                for c in rows[start:start+n]:
                    child=self.index.read_revision(pid,c['edit_id'],c['revision']);info=self._summary(child,family)
                    if info is None or child['document_sha256']!=c['document_sha256']:raise RuntimeError('Source edit section changed')
                    items.append({**info,'start_tick':str(c['start_tick']),'end_tick':str(c['end_tick'])})
            else:
                rows=d['segments'];total=len(rows);position=0
                for i,seg in enumerate(rows[:start+n]):
                    end=position+seg['out_tick']-seg['in_tick']
                    if i>=start:items.append({'label':f'Cut {i+1}','view':'cut','take':seg['take_id'],'start_tick':str(position),'end_tick':str(end)})
                    position=end
        elif summary['view']=='takes':
            if d['format']==CATALOG_FORMAT:
                result=self.hierarchy.catalog.page(pid,ident,revision,after_index=start-1,limit=n)
                nodes=result['items'];total=result['branch_count']
            else:
                nodes=self.hierarchy.graph.open_graph(pid,ident,revision)['data']['nodes'][start:start+n];total=len(d['nodes'])
            for node in nodes:
                slate=node['slate'];items.append({'label':f"{slate['shot']} · Take {slate['take_number']}",
                    'camera':slate['camera'],'setup':slate['setup'],'view':'take','branch_id':node['branch_id'],
                    'wild':slate['wild'],'source_start_tick':str(node['source_start_tick']),'source_end_tick':str(node['source_end_tick'])})
        elif summary['view']=='edit':
            segments=self.hierarchy.verified_edit(pid,row)['data']['segments'];total=len(segments)
            for seg in segments[start:start+n]:
                items.append({'label':seg['segment_id'],'view':'cut','take':seg['source_take_id'],
                    'start_tick':str(seg['timeline_start_tick']),'end_tick':str(seg['timeline_end_tick'])})
        else:
            roles=d.get('prim_roles',{});cameras=sorted(path for path,role in roles.items() if role=='camera');total=len(cameras)
            items=[{'label':path.rsplit('/',1)[-1],'view':'camera'} for path in cameras[start:start+n]]
        if start>total or (start==total and total):raise ValueError('Page is outside selected section')
        following=start+len(items) if start+len(items)<total else None
        return {'format':FORMAT,'project_id':pid,'family':family,'selection':summary,'items':items,
                'first':start,'total':total,'next_first':following,'ticks_per_second':str(TICKS_PER_SECOND),'source_modified':False}
