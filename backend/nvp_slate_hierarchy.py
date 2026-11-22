"""Immutable scene/catalog and editorial section hierarchy for trusted hosts.

Groups organize existing source revisions, never join unrelated Take ancestry.
All writes require explicit creator consent; page navigation is read-only.
"""
from copy import deepcopy
from backend.nvp_film_index import FilmIndex, _id, _sha, _require_pid, _deps
from backend.nvp_temporal_ledger import _int, MAX_TICK
from backend.nvp_slate_paged_catalog import SlatePagedCatalog, PagedSlateAssemblyAdapter, CATALOG_FORMAT, _sha as document_hash
from backend.nvp_digital_slate_branches import DigitalSlateBranches, GRAPH_FORMAT
from backend.nvp_slate_edit_assembly import SlateSequenceAssembly, FORMAT as EDIT_FORMAT

FORMAT = 'nvp.slate.hierarchy.v1'
MAX_CHILDREN = 64
MAX_DEPTH = 3
PAGE_SIZE = 64


def _title(value):
    if type(value) is not str or not 1 <= len(value.strip()) <= 120 or len(value) > 120 or any(ord(c) < 32 for c in value):
        raise ValueError('A short section name is required')
    return value.strip()


class SlateHierarchy:
    def __init__(self, index, *, approve, live_guard=None):
        if not isinstance(index, FilmIndex) or not callable(approve):
            raise TypeError('Trusted film index and approval required')
        if live_guard is not None and not callable(live_guard):raise TypeError("Trusted live guard required")
        self.live_guard=live_guard
        self.index = index
        self.approve = approve
        self.catalog = SlatePagedCatalog(index, verify_catalog_action=lambda *_: False)
        self.graph = DigitalSlateBranches(index, verify_editor_action=lambda *_: False)

    def _leaf(self, pid, row, family):
        d = row['data']; ident = row['object_id']; rev = row['revision']
        if family == 'takes' and row['kind'] == 'presentation':
            if d.get('format') == CATALOG_FORMAT:
                self.catalog.open_catalog(pid, ident, rev)
                # Existing catalog root validation; selected page reopens pinned rows.
                return d['branch_count'], 0
            if d.get('format') == GRAPH_FORMAT:
                return len(d['nodes']), 0
        if family == 'edit' and row['kind'] == 'edit' and d.get('format') == EDIT_FORMAT and d.get('explicit_editor_commit') is True:
            return len(d['segments']), _int(d['duration_tick'], 'edit duration', minimum=1)
        raise ValueError('Choose an original catalog or committed edit of this type')

    def _describe(self, pid, row, family):
        d = row['data']
        if d.get('format') != FORMAT:
            n, duration = self._leaf(pid, row, family)
            return n, duration, 0
        if (row['kind'] != ('presentation' if family == 'takes' else 'edit') or
                d.get('family') != family or d.get('render_approved') is not False or
                d.get('source_modified') is not False):
            raise RuntimeError('Invalid original section type')
        return (_int(d['item_count'], 'section count', minimum=1),
                _int(d['duration_tick'], 'section duration'),
                _int(d['depth'], 'section depth', minimum=1, maximum=MAX_DEPTH))

    def _compose(self, pid, ident, family, title, children):
        if family not in ('takes', 'edit') or type(children) is not list or not 1 <= len(children) <= MAX_CHILDREN:
            raise ValueError('Choose 1 to 64 source sections of one type')
        entries=[]; deps=[]; seen=set(); count=duration=depth=0
        for child in children:
            if type(child) is not dict or set(child) != {'object_id','revision','document_sha256'}:
                raise ValueError('Exact child revision required')
            oid=_id(child['object_id'], 'section child'); rev=_int(child['revision'], 'child revision', minimum=1)
            sha=_sha(child['document_sha256'])
            if oid == ident or (oid, rev) in seen:
                raise ValueError('Duplicate or self-referential section')
            seen.add((oid,rev))
            row=self.index.read_revision(pid,oid,rev)
            if row['document_sha256'] != sha:
                raise RuntimeError('Original section revision changed')
            n,t,d=self._describe(pid,row,family)
            if duration+t > MAX_TICK or count+n > MAX_TICK or d+1 > MAX_DEPTH:
                raise ValueError('Section exceeds exact source clock or hierarchy bounds')
            entries.append({**child,'first_index':count,'item_count':n,'start_tick':duration,'end_tick':duration+t,'depth':d})
            count+=n;duration+=t;depth=max(depth,d+1)
            deps.append({'object_id':oid,'revision':rev,'role':'presentation' if family=='takes' else 'timeline'})
        return {'format':FORMAT,'family':family,'title':_title(title),'children':entries,'item_count':count,
                'duration_tick':duration,'depth':depth,'source_modified':False,'render_approved':False}, _deps(deps,ident)

    def publish(self,pid,ident,*,family,title,children,creator_event,expected_revision=0):
        if self.live_guard:self.live_guard()
        _require_pid(pid);_id(ident,'section');_int(expected_revision,'expected section revision')
        frozen=deepcopy(children)
        doc,deps=self._compose(pid,ident,family,title,frozen)
        # Publication checks original leaf trust contracts. Group descendants
        # stay individually pinned and are verified when they are traversed.
        for child in frozen:
            row=self.index.read_revision(pid,child['object_id'],child['revision'])
            fmt=row['data'].get('format')
            if fmt==FORMAT:
                self.open(pid,row['object_id'],row['revision'])
            elif fmt==GRAPH_FORMAT:
                self.graph.open_graph(pid,row['object_id'],row['revision'])
            elif fmt==CATALOG_FORMAT:
                self.catalog.all_nodes(pid,row['object_id'],row['revision'])
            elif fmt==EDIT_FORMAT:
                self.verified_edit(pid,row)
        scope={'operation':'nvp.slate.publish_hierarchy.v1','project_id':pid,'section_id':ident,
               'expected_revision':expected_revision,'section_sha256':document_hash(doc),'render_approved':False}
        if self.approve(creator_event,deepcopy(scope)) is not True:
            raise PermissionError('Creator refused the exact section arrangement')
        if self._compose(pid,ident,family,title,frozen)!=(doc,deps):
            raise RuntimeError('Section changed during consent')
        def guard(db):
            if self.live_guard:self.live_guard()
            for child in frozen:
                row=self.index._read_revision(db,pid,child['object_id'],child['revision'])
                if row is None or row['document_sha']!=child['document_sha256']:
                    raise RuntimeError('Section changed before publication')
        return self.index.register_revision(pid,ident,'presentation' if family=='takes' else 'edit',
            doc,expected_revision=expected_revision,dependencies=deps,precommit_guard=guard)

    def open(self,pid,ident,revision):
        row=self.index.read_revision(pid,ident,revision);d=row['data']
        if d.get('format') != FORMAT:
            raise ValueError('Not an original section hierarchy')
        refs=[{k:c[k] for k in ('object_id','revision','document_sha256')} for c in d['children']]
        expected,deps=self._compose(pid,ident,d['family'],d['title'],refs)
        if expected!=d or deps!=row['dependencies'] or row['kind']!=('presentation' if d['family']=='takes' else 'edit'):
            raise RuntimeError('Section changed relative to approved original references')
        return row

    def verified_edit(self,pid,row):
        d=row['data'];g=self.index.read_revision(pid,d['graph_id'],d['graph_revision'])
        engine=SlateSequenceAssembly(PagedSlateAssemblyAdapter(self.catalog) if g['data'].get('format')==CATALOG_FORMAT else self.graph,
                                     verify_editor_action=lambda *_:False)
        return engine.open_edit(pid,row['object_id'],row['revision'])
