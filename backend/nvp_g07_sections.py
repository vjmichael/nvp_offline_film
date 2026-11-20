"""PERF-03G: protected, immutable editorial sections over original G07 revisions.

The existing encrypted live-store transaction is the only protected persistence
boundary. Sections never store media or start workers. Activation uses G07's
existing head, not an alternate timeline; finite G07 limits remain enforced.
"""
import copy
import json
import re

from backend import nvp_g03_payloads as protected_payloads
from backend.nvp_g07_edit import G07Editor, _project, _blank, MAX_EDL_CLIPS, MAX_PROJECT_SECONDS, FORMAT as FINITE_FORMAT
from backend.nvp_g06_filming import _json, _sha, HEX
from backend.nvp_temporal_ledger import TICKS_PER_SECOND, MAX_TICK
from backend.nvp_g04_preproduction import SCENE_ID
from backend.nvp_g05_scene_authoring import FORMAT as SCENE_FORMAT
from backend import nvp_g07_section_pages as pages
from backend import nvp_g07_paged_active as paged

FORMAT = 'nvp.g07.sections.v1'
LIMIT = 32
FANOUT = 64
DEPTH = 3
DIGEST = re.compile(r'[a-f0-9]{64}\Z')


def _number(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Invalid section position or revision')
    return value


def _digest(value):
    return _sha(_json(value).encode('utf8'))


def _check_sha(value):
    if type(value) is not str or not DIGEST.fullmatch(value):
        raise ValueError('Choose an exact saved source')
    return value


def _name(value):
    if type(value) is not str or not 1 <= len(value.strip()) <= 120 or len(value)>120 or any(ord(c)<32 for c in value):
        raise ValueError('Name this section')
    return value.strip()


def _schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS g07_sections(
        project_id TEXT NOT NULL, section_id TEXT NOT NULL,
        document_json TEXT NOT NULL, document_sha256 TEXT NOT NULL,
        PRIMARY KEY(project_id,section_id))''')
    db.execute('''CREATE TABLE IF NOT EXISTS g07_section_activations(
        project_id TEXT NOT NULL, revision INTEGER NOT NULL,
        section_id TEXT NOT NULL, section_digest TEXT NOT NULL,
        prior_revision INTEGER NOT NULL, edit_digest TEXT NOT NULL,
        approval_digest TEXT NOT NULL, PRIMARY KEY(project_id,revision))''')
    db.execute('''CREATE INDEX IF NOT EXISTS g07_section_take_page
        ON g06_frozen_takes(project_id,take_id)''')
    db.execute('''CREATE INDEX IF NOT EXISTS g07_section_scene_take_page
        ON g06_frozen_takes(project_id,scene_id,take_id)''')


class EditorialSections:
    def __init__(self, editor, *, access_guard=None):
        if not isinstance(editor,G07Editor):
            raise TypeError('Trusted original film editor required')
        if access_guard is not None and not callable(access_guard):raise TypeError("Trusted access guard required")
        self.editor=editor;self.access_guard=access_guard

    def _run(self,pid,fn,*,write=False):
        def action(db,movie):
            if self.access_guard:self.access_guard()
            self.editor.filming.g05._schema(db)
            _schema(db)
            # A single SQLite read snapshot protects selection and source
            # checks against concurrently published ordinary project edits.
            if not write and not db.in_transaction:db.execute('BEGIN')
            result=fn(db,movie)
            if self.access_guard:self.access_guard()
            host=self.editor.filming.g05.g04
            if host.live is not None:host.live._session(pid,host.token)
            return result
        return self.editor._execute(pid,action,mutate=write)

    def _edit(self,db,pid,revision,digest=None):
        _number(revision,1,15000)
        row=db.execute('''SELECT document_json,document_sha256 FROM g07_edit_versions
            WHERE project_id=? AND revision=?''',(pid,revision)).fetchone()
        if row is None:raise KeyError('Saved edit not found')
        if digest is not None and _check_sha(digest)!=row['document_sha256']:
            raise RuntimeError('Saved edit source changed')
        doc=protected_payloads.resolve_edit(db,pid,revision,row['document_json'],row['document_sha256'])
        ticks,segments=self.editor._validate(db,pid,doc)
        return doc,row['document_sha256'],ticks,segments

    def _page_context(self,pid):
        host=self.editor.filming.g05.g04
        if host.live is None:return {}
        return {"folder":host.live._folder(pid),"pid":pid,"key":host.live._session(pid,host.token)}

    def _section(self,db,pid,ident,digest=None):
        if type(ident) is not str or not HEX.fullmatch(ident):raise ValueError('Choose a saved section')
        row=db.execute('''SELECT document_json,document_sha256 FROM g07_sections
            WHERE project_id=? AND section_id=?''',(pid,ident)).fetchone()
        if row is None:raise KeyError('Section not found')
        raw=pages.resolve(row['document_json'],row['document_sha256'],**self._page_context(pid))
        doc=json.loads(raw)
        if (_digest(doc)!=row['document_sha256'] or (digest is not None and _check_sha(digest)!=row['document_sha256']) or
            set(doc)!={'format','project_id','section_id','title','children','duration_tick','clip_count','depth'} or
            doc['format']!=FORMAT or doc['project_id']!=pid or doc['section_id']!=ident):
            raise RuntimeError('Saved section identity changed')
        _name(doc['title']);_number(doc['depth'],1,DEPTH);_number(doc['clip_count'],1,FANOUT**DEPTH*MAX_EDL_CLIPS);_number(doc['duration_tick'],1,MAX_TICK)
        if type(doc['children']) is not list or not 1<=len(doc['children'])<=FANOUT:raise RuntimeError('Invalid section children')
        return doc,row['document_sha256']

    def _reference(self,db,pid,ref):
        if type(ref) is not dict:raise ValueError('Choose a source section')
        if set(ref)=={'kind','revision','digest','first','count'} and ref['kind']=='edit':
            doc,sha,_,segments=self._edit(db,pid,ref['revision'],ref['digest'])
            first=_number(ref['first'],0,len(segments)-1);count=_number(ref['count'],1,len(segments)-first)
            clips=doc['clips'][first:first+count]
            # A boundary with a dissolve would silently alter an approved cut.
            if clips[0]['transition']['duration_tick']!=0 or (first+count<len(segments) and doc['clips'][first+count]['transition']['duration_tick']!=0):
                raise ValueError('Choose section boundaries at straight cuts')
            return len(clips),segments[first+count-1]['end_tick']-segments[first]['start_tick'],0,doc['title'] or f"Edit {ref['revision']}"
        if set(ref)=={'kind','section_id','digest'} and ref['kind']=='section':
            doc,_=self._section(db,pid,ref['section_id'],ref['digest'])
            return doc['clip_count'],doc['duration_tick'],doc['depth'],doc['title']
        raise ValueError('Only exact saved edit sections can be grouped')

    def _compose(self,db,pid,title,refs):
        if type(refs) is not list or not 1<=len(refs)<=FANOUT:raise ValueError('Choose 1 to 64 sections')
        seen=set();children=[];count=ticks=depth=0
        for ref in refs:
            key=_json(ref)
            if key in seen:raise ValueError('A section was selected twice')
            seen.add(key)
            n,t,d,label=self._reference(db,pid,ref)
            if d+1>DEPTH or ticks+t>MAX_TICK or count+n>FANOUT**DEPTH*MAX_EDL_CLIPS:raise ValueError('Section exceeds supported hierarchy bounds')
            children.append({'source':copy.deepcopy(ref),'label':label,'clip_count':n,'start_tick':ticks,'end_tick':ticks+t})
            count+=n;ticks+=t;depth=max(depth,d+1)
        return {'title':_name(title),'children':children,'clip_count':count,'duration_tick':ticks,'depth':depth}

    def _verified(self,db,pid,ident,digest=None):
        doc,sha=self._section(db,pid,ident,digest)
        expected=self._compose(db,pid,doc['title'],[c['source'] for c in doc['children']])
        if any(doc[k]!=v for k,v in expected.items()):raise RuntimeError('Section no longer matches its original sources')
        return doc,sha

    @staticmethod
    def _summary(doc,sha):
        return {'kind':'section','section_id':doc['section_id'],'digest':sha,'label':doc['title'],'clip_count':doc['clip_count'],'duration_tick':str(doc['duration_tick'])}

    def _scene(self,db,pid,ident,revision):
        if type(ident) is not str or not SCENE_ID.fullmatch(ident):raise ValueError('Choose a saved scene')
        _number(revision,1,15000)
        row=db.execute("""SELECT source_sha256,plan_json,usd_sha256,length(usd_layer) AS usd_size
            FROM g05_scene_versions WHERE project_id=? AND scene_id=? AND revision=?""",(pid,ident,revision)).fetchone()
        if row is None:raise KeyError('Saved scene not found')
        if len(row['plan_json'].encode('utf8'))>2*1024*1024:raise ValueError('Scene metadata exceeds safe bounds')
        plan=json.loads(row['plan_json']);source=plan.get('source',{})
        if (plan.get('format')!=SCENE_FORMAT or source.get('project_id')!=pid or source.get('scene_id')!=ident or
            source.get('scene_sha256')!=row['source_sha256'] or not row['usd_size']):raise RuntimeError('Saved scene identity changed')
        _check_sha(row['source_sha256']);_check_sha(row['usd_sha256'])
        digest=_digest({'project_id':pid,'scene_id':ident,'revision':revision,'source_sha256':row['source_sha256'],'usd_sha256':row['usd_sha256'],'plan':plan})
        label=plan.get('scene_name')
        if type(label) is not str or not label.strip():raise RuntimeError('Saved scene has no name')
        return {'kind':'scene','scene_id':ident,'revision':revision,'digest':digest,'label':label[:160]}

    def _take_page(self,db,pid,n,after=None,scene=None):
        if after is not None and (type(after) is not str or not HEX.fullmatch(after)):raise ValueError('Invalid Take cursor')
        if scene:
            rows=list(db.execute('SELECT take_id FROM g06_frozen_takes WHERE project_id=? AND scene_id=? AND take_id>? ORDER BY take_id LIMIT ?',(pid,scene,after or '',n+1)))
        else:rows=list(db.execute('SELECT take_id FROM g06_frozen_takes WHERE project_id=? AND take_id>? ORDER BY take_id LIMIT ?',(pid,after or '',n+1)))
        items=[]
        for row in rows[:n]:
            source,doc,_=self.editor.filming._take_metadata(db,pid,row[0]);items.append({'kind':'take','take_id':row[0],'digest':source['take_sha256'],'label':f"Take · {row[0][-8:]}",'scene_id':source['scene_id'],'duration_tick':str(doc['duration_tick'])})
        return items,rows[n-1][0] if len(rows)>n else None

    def directory(self,pid,family,after=None,limit=LIMIT):
        n=_number(limit,1,64)
        def read(db,movie):
            items=[]
            if family=='sections':
                if after is not None and (type(after) is not str or not HEX.fullmatch(after)):raise ValueError('Invalid section cursor')
                rows=list(db.execute('SELECT section_id FROM g07_sections WHERE project_id=? AND section_id>? ORDER BY section_id LIMIT ?',(pid,after or '',n+1)))
                for row in rows[:n]:
                    doc,sha=self._section(db,pid,row[0]);items.append(self._summary(doc,sha))
                cursor=rows[n-1][0] if len(rows)>n else None
            elif family=='edits':
                last=0 if after is None else _number(after,1,15000)
                rows=list(db.execute('SELECT revision FROM g07_edit_versions WHERE project_id=? AND revision>? ORDER BY revision LIMIT ?',(pid,last,n+1)))
                for row in rows[:n]:
                    raw=db.execute('SELECT document_json,document_sha256 FROM g07_edit_versions WHERE project_id=? AND revision=?',(pid,row[0])).fetchone()
                    doc=protected_payloads.resolve_edit(db,pid,row[0],raw['document_json'],raw['document_sha256'])
                    if doc.get('format')==paged.FORMAT:
                        section,sha=self._paged_root(db,pid,row[0],doc)
                        items.append({**self._summary(section,sha),'label':section['title']})
                    else:
                        doc,sha,ticks,segments=self._edit(db,pid,row[0]);items.append({'kind':'edit','revision':row[0],'digest':sha,'label':f"Edit {row[0]} — {doc['title']}",'clip_count':len(segments),'duration_tick':str(ticks)})
                cursor=rows[n-1][0] if len(rows)>n else None
            elif family=='takes':
                items,cursor=self._take_page(db,pid,n,after)
            elif family=='scenes':
                if after is not None and (type(after) is not str or not SCENE_ID.fullmatch(after)):raise ValueError('Invalid scene cursor')
                rows=list(db.execute('SELECT scene_id,revision FROM g05_scene_heads WHERE project_id=? AND scene_id>? ORDER BY scene_id LIMIT ?',(pid,after or '',n+1)))
                items=[self._scene(db,pid,row['scene_id'],row['revision']) for row in rows[:n]]
                cursor=rows[n-1]['scene_id'] if len(rows)>n else None
            else:raise ValueError('Choose Scenes, Takes, Saved edits, or Sections')
            rev,active=_project(db,pid,allow_paged=True)
            active_section=None
            receipt=db.execute('SELECT section_id,section_digest,edit_digest,prior_revision,approval_digest FROM g07_section_activations WHERE project_id=? AND revision=?',(pid,rev)).fetchone()
            if active.get('format')==paged.FORMAT:
                section,sha=self._paged_root(db,pid,rev,active)
                active_section=self._summary(section,sha)
            elif receipt is not None:
                section,sha=self._section(db,pid,receipt['section_id'],receipt['section_digest'])
                expected_scope={'project_id':pid,'section_id':receipt['section_id'],'section_digest':sha,'expected_revision':receipt['prior_revision'],'edit_digest':receipt['edit_digest']}
                if receipt['edit_digest']!=_digest(active) or receipt['prior_revision']!=rev-1 or receipt['approval_digest']!=_digest(expected_scope):raise RuntimeError('Active section receipt changed')
                active_section=self._summary(section,sha)
            return {'format':FORMAT,'project_id':pid,'family':family,'items':items,'next_after':cursor,'active_revision':rev,'active_section':active_section,'render_approved':False}
        return self._run(pid,read)

    def page(self,pid,ref,first=0,limit=LIMIT,after=None):
        first=_number(first,0,MAX_TICK);n=_number(limit,1,64)
        def read(db,movie):
            if type(ref) is not dict:raise ValueError('Exact selection required')
            if set(ref)=={'kind','scene_id','revision','digest'} and ref['kind']=='scene':
                selection=self._scene(db,pid,ref['scene_id'],ref['revision'])
                if selection['digest']!=_check_sha(ref['digest']) or first!=0:raise PermissionError('Selected scene changed')
                items,cursor=self._take_page(db,pid,n,after,ref['scene_id'])
                return {'format':FORMAT,'project_id':pid,'selection':selection,'items':items,'first':0,'next_after':cursor,'render_approved':False}
            if after is not None:raise ValueError('Use the exact section page position')
            if set(ref)=={'kind','section_id','digest'} and ref['kind']=='section':
                doc,sha=self._verified(db,pid,ref['section_id'],ref['digest']);rows=doc['children'];selection=self._summary(doc,sha)
                items=[{**c,'start_tick':str(c['start_tick']),'end_tick':str(c['end_tick'])} for c in rows[first:first+n]]
            elif set(ref) in ({'kind','revision','digest'},{'kind','revision','digest','first','count'}) and ref['kind']=='edit':
                doc,sha,ticks,rows=self._edit(db,pid,ref['revision'],ref['digest'])
                offset=0;origin=0
                if 'first' in ref:
                    count,ticks,_,_=self._reference(db,pid,ref)
                    offset=ref['first'];rows=rows[offset:offset+count];origin=rows[0]['start_tick']
                selection={**ref,'label':doc['title'],'clip_count':len(rows),'duration_tick':str(ticks)}
                items=[{'label':f'Cut {offset+i+1}','take_id':r['take_id'],'start_tick':str(r['start_tick']-origin),'end_tick':str(r['end_tick']-origin)} for i,r in enumerate(rows[first:first+n],first)]
            else:raise ValueError('Choose an exact saved edit or section')
            if first>len(rows) or (first==len(rows) and rows):raise ValueError('Page outside section')
            end=first+len(items)
            return {'format':FORMAT,'project_id':pid,'selection':selection,'items':items,'first':first,'total':len(rows),'next_first':end if end<len(rows) else None,'render_approved':False}
        return self._run(pid,read)

    def preview(self,pid,title,refs):
        return self._run(pid,lambda db,movie:self._preview(db,pid,title,refs))

    def _preview(self,db,pid,title,refs):
        result=self._compose(db,pid,title,refs)
        return {'format':FORMAT,'project_id':pid,'title':result['title'],'clip_count':result['clip_count'],'duration_tick':str(result['duration_tick']),'digest':_digest(result),'render_approved':False}

    def publish(self,pid,title,refs,digest):
        _check_sha(digest)
        def write(db,movie):
            composed=self._compose(db,pid,title,refs)
            if _digest(composed)!=digest:raise PermissionError('Section preview changed; review again')
            # A repeated save of the exact same approved composition is
            # idempotent; a changed title or order requires another preview.
            ident=_digest({'project_id':pid,'composition':digest})[:32]
            doc={'format':FORMAT,'project_id':pid,'section_id':ident,**composed};sha=_digest(doc)
            prior=db.execute('SELECT 1 FROM g07_sections WHERE project_id=? AND section_id=?',(pid,ident)).fetchone()
            if prior:
                existing,existing_sha=self._section(db,pid,ident)
                if existing!=doc or existing_sha!=sha:raise RuntimeError('Section identity collision')
            else:
                raw=_json(doc);context=self._page_context(pid)
                if context:raw=pages.seal_page(raw=raw,sha=sha,**context)
                db.execute('INSERT INTO g07_sections VALUES(?,?,?,?)',(pid,ident,raw,sha))
            return {'format':FORMAT,'project_id':pid,'selection':self._summary(doc,sha),'render_approved':False}
        return self._run(pid,write,write=True)

    def _activation(self,db,pid,ident,digest,expected):
        rev,_=_project(db,pid,allow_paged=True)
        if _number(expected,0,15000)!=rev:raise RuntimeError('Your edit has newer changes; reopen it')
        doc,sha=self._verified(db,pid,ident,digest)
        result,ticks=self._materialize(db,pid,doc)
        scope={'project_id':pid,'section_id':ident,'section_digest':sha,'expected_revision':rev,'edit_digest':_digest(result)}
        return result,scope,ticks

    def _materialize(self,db,pid,doc):
        # Reject before expansion; do not flatten unbounded hierarchies or bypass
        # the existing renderer/editor's finite contract.
        if doc['clip_count']>MAX_EDL_CLIPS or doc['duration_tick']>MAX_PROJECT_SECONDS*TICKS_PER_SECOND:
            raise ValueError('This section is too large for the current active editing timeline')
        result=_blank();result['title']=doc['title'];gain=None;notes=None;seen=set()
        def walk(group,level=1):
            nonlocal gain,notes
            if level>DEPTH:raise RuntimeError("Grouped edit hierarchy exceeds depth")
            for child in group['children']:
                ref=child['source']
                if ref['kind']=='section':
                    sub,_=self._verified(db,pid,ref['section_id'],ref['digest']);walk(sub,level+1)
                else:
                    source,_,_,_=self._edit(db,pid,ref['revision'],ref['digest'])
                    if gain is None:gain=source['master_gain'];notes=source['notes']
                    elif gain!=source['master_gain']:raise ValueError('Sections have different master sound levels; reconcile before activation')
                    elif notes!=source['notes']:raise ValueError('Sections have different film notes; reconcile before activation')
                    for clip in source['clips'][ref['first']:ref['first']+ref['count']]:
                        if clip['id'] in seen:raise ValueError('Sections reuse a clip identity; choose non-overlapping sections')
                        seen.add(clip['id']);result['clips'].append(copy.deepcopy(clip))
                        if len(seen)>MAX_EDL_CLIPS:raise ValueError('Active editing timeline exceeds its limit')
        walk(doc);result['master_gain']=gain;result['notes']=notes
        ticks,_=self.editor._validate(db,pid,result)
        if ticks!=doc['duration_tick'] or len(result['clips'])!=doc['clip_count']:raise RuntimeError('Grouped cut clocks changed')
        return result,ticks

    def verify_activated_edit(self,db,pid,revision,document):
        """Native consumers of a committed grouped cut reopen its exact sources.

        No new head and no render approval. Legacy ordinary revisions remain
        ordinary revisions; an existing receipt must match its original group.
        """
        exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='g07_section_activations'").fetchone()
        if not exists:return None
        receipt=db.execute('SELECT * FROM g07_section_activations WHERE project_id=? AND revision=?',(pid,revision)).fetchone()
        if receipt is None:return None
        doc,sha=self._verified(db,pid,receipt['section_id'],receipt['section_digest'])
        rebuilt,ticks=self._materialize(db,pid,doc)
        scope={'project_id':pid,'section_id':doc['section_id'],'section_digest':sha,
               'expected_revision':revision-1,'edit_digest':_digest(rebuilt)}
        if (receipt['prior_revision']!=revision-1 or receipt['edit_digest']!=scope['edit_digest'] or
                receipt['approval_digest']!=_digest(scope) or _digest(document)!=scope['edit_digest']):
            raise RuntimeError('Active grouped cut no longer matches approved originals')
        return {'section_id':doc['section_id'],'section_digest':sha,'duration_tick':ticks}

    def cut_page(self,pid,ident,digest,first=0,limit=LIMIT):
        """Host-only bounded leaf-cut traversal. Not a render or activation grant.

        Root and visited ancestors are reopened. Unvisited branches are not
        certified; their own pages independently reopen source identities.
        """
        first=_number(first,0,MAX_TICK);n=_number(limit,1,64)
        def read(db,movie):
            root,sha=self._verified(db,pid,ident,digest)
            if first>=root['clip_count']:raise ValueError('Page outside section')
            stop=min(first+n,root['clip_count']);items=[]
            def walk(group,base,tick,level=1):
                if level>DEPTH:raise RuntimeError('Invalid grouped cut depth')
                index=base
                for child in group['children']:
                    end=index+child['clip_count'];a=max(first,index);b=min(stop,end)
                    if a<b:
                        ref=child['source'];start=tick+child['start_tick']
                        if ref['kind']=='section':
                            sub,_=self._verified(db,pid,ref['section_id'],ref['digest']);walk(sub,index,start,level+1)
                        else:
                            _,_,_,segments=self._edit(db,pid,ref['revision'],ref['digest'])
                            origin=segments[ref['first']]['start_tick']
                            for k in range(a,b):
                                seg=segments[ref['first']+k-index]
                                items.append({'index':k,'source_revision':ref['revision'],'source_digest':ref['digest'],
                                    'clip_id':seg['clip_id'],'take_id':seg['take_id'],'take_sha256':seg['take_sha256'],
                                    'start_tick':start+seg['start_tick']-origin,'end_tick':start+seg['end_tick']-origin})
                    index=end
            walk(root,0,0)
            if len(items)!=stop-first or any(x['index']!=first+i for i,x in enumerate(items)):
                raise RuntimeError('Grouped cut page has incomplete coverage')
            return {'format':FORMAT,'project_id':pid,'section_digest':sha,'first':first,'total':root['clip_count'],
                    'items':items,'next_first':stop if stop<root['clip_count'] else None,'render_approved':False}
        return self._run(pid,read)

    def _walk_cuts(self,db,pid,root,first,stop):
        """Stream ordered exact leaf records, skipping unrelated subtrees on a page."""
        def walk(group,base,tick,level):
            if level>DEPTH:raise RuntimeError('Invalid grouped cut depth')
            index=base
            for child in group['children']:
                end=index+child['clip_count'];a=max(first,index);b=min(stop,end)
                if a<b:
                    ref=child['source'];start=tick+child['start_tick']
                    if ref['kind']=='section':
                        sub,_=self._verified(db,pid,ref['section_id'],ref['digest'])
                        yield from walk(sub,index,start,level+1)
                    else:
                        source,sha,_,segments=self._edit(db,pid,ref['revision'],ref['digest'])
                        origin=segments[ref['first']]['start_tick']
                        for k in range(a,b):
                            seg=segments[ref['first']+k-index]
                            yield source,{**seg,'index':k,'source_revision':ref['revision'],'source_digest':sha,
                                'start_tick':start+seg['start_tick']-origin,'end_tick':start+seg['end_tick']-origin}
                index=end
        yield from walk(root,0,0,1)

    def _paged_root(self,db,pid,revision,document):
        paged.check(document)
        receipt=db.execute('SELECT * FROM g07_section_activations WHERE project_id=? AND revision=?',(pid,revision)).fetchone()
        root,sha=self._verified(db,pid,document['section_id'],document['section_digest'])
        scope={'project_id':pid,'section_id':root['section_id'],'section_digest':sha,'expected_revision':revision-1,'edit_digest':_digest(document)}
        if (receipt is None or receipt['section_id']!=root['section_id'] or receipt['section_digest']!=sha or receipt['prior_revision']!=revision-1 or receipt['edit_digest']!=scope['edit_digest'] or receipt['approval_digest']!=_digest(scope) or
                any(root[k]!=document[k] for k in ('title','clip_count','duration_tick'))):
            raise RuntimeError('Active section timeline receipt changed')
        return root,sha

    def _prepare_paged(self,db,pid,ident,digest,expected):
        rev,_=_project(db,pid,allow_paged=True)
        if _number(expected,0,15000)!=rev:raise RuntimeError('Your edit has newer changes; reopen it')
        root,sha=self._verified(db,pid,ident,digest)
        doc=paged.build(self,db,pid,root,sha)
        return doc,{'project_id':pid,'section_id':ident,'section_digest':sha,'expected_revision':rev,'edit_digest':_digest(doc)}

    def preview_paged(self,pid,ident,digest,expected):
        def read(db,movie):
            doc,scope=self._prepare_paged(db,pid,ident,digest,expected)
            return {'format':FORMAT,**scope,'approval_digest':_digest(scope),'clip_count':doc['clip_count'],
                    'duration_tick':str(doc['duration_tick']),'paged':True,'render_approved':False}
        return self._run(pid,read)

    def activate_paged(self,pid,ident,digest,expected,approval_digest):
        _check_sha(approval_digest)
        def write(db,movie):
            doc,scope=self._prepare_paged(db,pid,ident,digest,expected)
            if _digest(scope)!=approval_digest:raise PermissionError('Review this section timeline again')
            rev=self.editor._save(db,pid,doc,expected,expected)
            db.execute('INSERT INTO g07_section_activations VALUES(?,?,?,?,?,?,?)',(pid,rev,ident,digest,expected,scope['edit_digest'],approval_digest))
            return {'format':FORMAT,'project_id':pid,'revision':rev,'clip_count':doc['clip_count'],
                    'duration_tick':str(doc['duration_tick']),'paged':True,'render_approved':False,'original_sources_unchanged':True}
        return self._run(pid,write,write=True)

    def _active_view(self,db,pid,revision,document):
        _schema(db);root,sha=self._paged_root(db,pid,revision,document)
        return {'format':paged.FORMAT,'project_id':pid,'revision':revision,'title':document['title'],'notes':document['notes'],
                'master_gain':document['master_gain'],'clips':[],'timeline':[],'available_takes':[],'missing_sources':[],
                'history':[dict(r) for r in db.execute("SELECT revision,created_at FROM g07_edit_versions WHERE project_id=? AND json_extract(document_json,'$.format')=? ORDER BY revision DESC LIMIT 40",(pid,FINITE_FORMAT))],
                'duration_tick':str(document['duration_tick']),'duration_seconds':document['duration_tick']/TICKS_PER_SECOND,
                'active_section':self._summary(root,sha),'active_digest':_digest(document),'clip_count':document['clip_count'],
                'render_approved':False,'original_sources_unchanged':True,'final_movie_exported':False}

    def active_page(self,pid,revision,digest,first=0,limit=LIMIT,*,native=False):
        first=_number(first,0,MAX_TICK);n=_number(limit,1,64);_check_sha(digest)
        def read(db,movie):
            current,doc=_project(db,pid,allow_paged=True)
            if current!=revision or doc.get('format')!=paged.FORMAT or _digest(doc)!=digest:
                raise RuntimeError('The active edit changed; reopen it')
            root,sha=self._paged_root(db,pid,current,doc)
            if first>=root['clip_count']:raise ValueError('Page outside section timeline')
            stop=min(first+n,root['clip_count']);items=[]
            for _,seg in self._walk_cuts(db,pid,root,first,stop):
                if self.access_guard:self.access_guard()
                if native:items.append(seg)
                else:items.append({'index':seg['index'],'scene_id':seg['scene_id'],'start_tick':str(seg['start_tick']),
                    'end_tick':str(seg['end_tick']),'transition':seg['transition']['kind']})
            if len(items)!=stop-first or any(x['index']!=first+i for i,x in enumerate(items)):raise RuntimeError('Timeline page incomplete')
            return {'format':paged.FORMAT,'project_id':pid,'revision':current,'active_digest':digest,'first':first,
                    'total':root['clip_count'],'items':items,'next_first':stop if stop<root['clip_count'] else None,'render_approved':False}
        return self._run(pid,read)

    def audit_active(self,pid):
        """Explicit full source recheck, e.g. after restoring a protected folder."""
        def read(db,movie):
            revision,doc=_project(db,pid,allow_paged=True)
            root,sha=self._paged_root(db,pid,revision,doc)
            if paged.build(self,db,pid,root,sha)!=doc:raise RuntimeError('Active timeline source changed')
            return {'revision':revision,'active_digest':_digest(doc),'clip_count':doc['clip_count'],'render_approved':False}
        return self._run(pid,read)

    def verify_protected_storage(self,pid):
        """Host-only authenticated recovery audit of all indexed editorial bodies.

        No filesystem discovery of unindexed orphans, no automatic adoption,
        no database rewrite or media-decode claim. Require an unlocked live film.
        """
        if not self._page_context(pid):raise PermissionError('Unlock the protected film first')
        def read(db,movie):
            total=0;sealed=0
            for row in db.execute('SELECT section_id,document_json,document_sha256 FROM g07_sections WHERE project_id=? ORDER BY section_id',(pid,)):
                if self.access_guard:self.access_guard()
                self._verified(db,pid,row['section_id'],row['document_sha256']);total+=1
                if json.loads(row['document_json']).get('format')==pages.FORMAT:sealed+=1
            audits=0
            for row in db.execute('SELECT revision,document_json,document_sha256 FROM g07_edit_versions WHERE project_id=? ORDER BY revision',(pid,)):
                doc=protected_payloads.resolve_edit(db,pid,row['revision'],row['document_json'],row['document_sha256'])
                if doc.get('format')==paged.FORMAT:
                    root,sha=self._paged_root(db,pid,row['revision'],doc)
                    if paged.build(self,db,pid,root,sha)!=doc:raise RuntimeError('Saved section timeline changed')
                    audits+=1
                elif doc.get('format')==FINITE_FORMAT:
                    self.verify_activated_edit(db,pid,row['revision'],doc)
                else:raise RuntimeError('Unsupported saved edit format')
            rev,_=_project(db,pid,allow_paged=True)
            return {'project_id':pid,'revision':rev,'verified_sections':total,'verified_sealed_pages':sealed,'verified_paged_edits':audits,'render_approved':False}
        return self._run(pid,read)

    def recover_missing_page(self,pid,ident,digest,backup_folder,*,expected_revision,human_approved=False):
        """Trusted host only: restore one missing immutable page from a backup.

        Existing bytes are never replaced. The current authenticated SQLite
        index, exact revision and digest—not the backup HEAD—authorize repair.
        A failed/aborted repair can leave only the exact indexed encrypted body.
        """
        from backend.nvp_g03_windows_vault import VaultError
        if human_approved is not True:raise PermissionError('Director-approved recovery required')
        if type(ident) is not str or not HEX.fullmatch(ident):raise ValueError('Invalid section identity')
        _check_sha(digest)
        host=self.editor.filming.g05.g04;live=host.live
        if live is None:raise PermissionError('Unlock the protected film first')
        # Lock order matches the original sealed store; no alternate HEAD write.
        with live._guard:
            key=live._session(pid,host.token);folder=live._folder(pid)
            from backend.nvp_g07_recovery_dialog import _backup_path
            backup=_backup_path(backup_folder,folder)
            with live._write_mutex(folder):
                db,head=live._read_db(folder,pid,key)
                try:
                    if self.access_guard:self.access_guard()
                    rev,_=_project(db,pid,allow_paged=True)
                    if rev!=_number(expected_revision,1,15000):raise RuntimeError('The active edit changed')
                    row=db.execute('SELECT document_json,document_sha256 FROM g07_sections WHERE project_id=? AND section_id=?',(pid,ident)).fetchone()
                    if row is None or row['document_sha256']!=digest or json.loads(row['document_json'])!={'format':pages.FORMAT,'sha256':digest}:raise RuntimeError('No exact indexed sealed page to recover')
                    target=pages._location(folder,key,digest,create=False,missing_directory=True)
                    # A dangling link is not a missing page.
                    if target.exists() or target.is_symlink():raise VaultError('Existing page must be preserved for review')
                    raw=pages.read_page(backup,pid,key,digest);doc=json.loads(raw)
                    if type(doc) is not dict or set(doc)!={'format','project_id','section_id','title','children','duration_tick','clip_count','depth'} or doc['format']!=FORMAT or doc['project_id']!=pid or doc['section_id']!=ident or _digest(doc)!=digest:raise VaultError('Backup section ownership changed')
                    # Verify the original direct dependencies before restoring.
                    expected=self._compose(db,pid,doc['title'],[c['source'] for c in doc['children']])
                    if any(doc[k]!=v for k,v in expected.items()):raise VaultError('Backup section source changed')
                    live._session(pid,host.token)
                    if live._head(folder)!=head:raise RuntimeError('Film changed during recovery')
                    if self.access_guard:self.access_guard()
                    pages.seal_page(folder,pid,key,raw,digest)
                    self._verified(db,pid,ident,digest)
                    live._session(pid,host.token)
                    if live._head(folder)!=head:raise RuntimeError('Film changed during recovery')
                    return {'section_id':ident,'section_digest':digest,'revision':rev,'restored':True,'render_approved':False}
                finally:db.close()

    def preview_activation(self,pid,ident,digest,expected):
        def read(db,movie):
            result,scope,ticks=self._activation(db,pid,ident,digest,expected)
            return {'format':FORMAT,**scope,'approval_digest':_digest(scope),'clip_count':len(result['clips']),'duration_tick':str(ticks),'render_approved':False}
        return self._run(pid,read)

    def activate(self,pid,ident,digest,expected,approval_digest):
        _check_sha(approval_digest)
        def write(db,movie):
            result,scope,ticks=self._activation(db,pid,ident,digest,expected)
            if _digest(scope)!=approval_digest:raise PermissionError('Review the exact grouped cut before saving')
            rev=self.editor._save(db,pid,result,expected,expected)
            db.execute('INSERT INTO g07_section_activations VALUES(?,?,?,?,?,?,?)',(pid,rev,ident,digest,expected,scope['edit_digest'],approval_digest))
            return {'format':FORMAT,'project_id':pid,'revision':rev,'duration_tick':str(ticks),'clip_count':len(result['clips']),'render_approved':False,'original_sources_unchanged':True}
        return self._run(pid,write,write=True)
