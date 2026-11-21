"""Immutable native feature section composition. No authorization to render.

Each finite leaf retains its existing approved source assembly. A group pins
only direct children, exact revisions and a continuous local frame clock.
Walk recursively for independent leaf verification; never flatten a feature.
"""
from copy import deepcopy
import hashlib
import json
import re

GROUP='nvp.wo4.approved_feature_sections.v1'
LEAF='nvp.wo4.approved_feature_assembly.v1'
MAX_CHILDREN=64
MAX_DEPTH=4
MAX_TICKS=2**53-1  # exact transport integer, not a film length target
SHA=re.compile(r'[0-9a-f]{64}\Z')
ID=re.compile(r'[A-Za-z0-9_-]{1,128}\Z')


def ref(entry):
    if type(entry) is not dict or set(entry)!={'object_id','revision','sha256'}:
        raise ValueError('Exact feature section reference required')
    if (type(entry['object_id']) is not str or not ID.fullmatch(entry['object_id']) or
        type(entry['revision']) is not int or entry['revision']<1 or
        type(entry['sha256']) is not str or not SHA.fullmatch(entry['sha256'])):
        raise ValueError('Invalid feature section reference')
    return dict(entry)


def inspect(index,pid,entry,*,frame_ticks):
    entry=ref(entry)
    record=index.read_revision(pid,entry['object_id'],entry['revision'])
    if record['kind'] not in ('edit','presentation') or record['document_sha256']!=entry['sha256']:
        raise PermissionError('Feature section revision changed')
    data=record['data'];fmt=data.get('format')
    if fmt==LEAF:
        jobs=data.get('ordered_reel_job_ids')
        if type(jobs) is not list or not 2<=len(jobs)<=127 or len(set(jobs))!=len(jobs):
            raise PermissionError('Existing finite approved feature assembly required')
        count=1;depth=0
    elif fmt==GROUP:
        count=data.get('section_count');depth=data.get('depth')
        if (type(count) is not int or count<2 or type(depth) is not int or not 1<=depth<=MAX_DEPTH or
                type(data.get('children')) is not list or not 2<=len(data['children'])<=MAX_CHILDREN):
            raise PermissionError('Invalid feature section group')
    else: raise PermissionError('Unknown feature section format')
    end=data.get('end_tick')
    if (data.get('start_tick')!=0 or type(end) is not int or not 0<end<=MAX_TICKS or end%frame_ticks):
        raise PermissionError('Section clock is not exact local cinema-frame time')
    return record,end,count,depth


def build(index,pid,children,*,frame_ticks):
    if type(frame_ticks) is not int or frame_ticks<=0:raise ValueError('Invalid Film Time')
    if type(children) is not list or not 2<=len(children)<=MAX_CHILDREN:
        raise ValueError('Bounded direct feature section group required')
    start=0;count=0;depth=0;entries=[];seen=set()
    for child in children:
        child=ref(child); key=(child['object_id'],child['revision'])
        if key in seen:raise PermissionError('Repeated direct feature section')
        seen.add(key)
        _,length,n,level=inspect(index,pid,child,frame_ticks=frame_ticks)
        end=start+length; count+=n;depth=max(depth,level+1)
        if end>MAX_TICKS or depth>MAX_DEPTH or count>MAX_CHILDREN**MAX_DEPTH:
            raise ValueError('Feature section group exceeds structural budget')
        entries.append({**child,'start_tick':start,'end_tick':end});start=end
    return {'format':GROUP,'start_tick':0,'end_tick':start,'section_count':count,'depth':depth,
            'children':entries,'source_modified':False,'production_dcp_accepted':False}


def walk(index,pid,entry,*,frame_ticks,offset=0,ancestors=()):
    """Bounded-depth generator. Fully exhaust before using as a verified plan."""
    entry=ref(entry);key=(entry['object_id'],entry['revision'])
    if key in ancestors or len(ancestors)>MAX_DEPTH:raise PermissionError('Feature section cycle or-depth overflow')
    record,length,count,depth=inspect(index,pid,entry,frame_ticks=frame_ticks)
    data=record['data']
    if data['format']==LEAF:
        yield {**entry,'start_tick':offset,'end_tick':offset+length,'frame_count':length//frame_ticks}
        return
    refs=[{k:c[k] for k in ('object_id','revision','sha256')} for c in data['children']]
    if build(index,pid,refs,frame_ticks=frame_ticks)!=data:
        raise PermissionError('Feature group clock or child descriptor changed')
    actual=0
    for c,r in zip(data['children'],refs):
        for item in walk(index,pid,r,frame_ticks=frame_ticks,offset=offset+c['start_tick'],ancestors=ancestors+(key,)):
            actual+=1;yield item
    if actual!=count:raise PermissionError('Feature group section count differs')


def register(index,pid,object_id,children,*,frame_ticks,approve):
    if type(object_id) is not str or not ID.fullmatch(object_id):raise ValueError('Invalid group identity')
    data=build(index,pid,children,frame_ticks=frame_ticks)
    if any(c['object_id']==object_id for c in data['children']):raise PermissionError('Self dependency')
    # Audit descendants before granting creator consent; no flat list.
    for child in children:
        for _ in walk(index,pid,child,frame_ticks=frame_ticks):pass
    digest=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')).hexdigest()
    if approve({'operation':'nvp.wo4.register_feature_sections.v1','project_id':pid,
                'object_id':object_id,'document_sha256':digest,'section_count':data['section_count'],
                'end_tick':data['end_tick'],'source_modified':False}) is not True:
        return {'status':'DENIED'}
    if data!=build(index,pid,children,frame_ticks=frame_ticks):raise PermissionError('Feature composition changed during consent')
    deps=[{'object_id':c['object_id'],'revision':c['revision'],'role':'presentation'} for c in data['children']]
    def guard(db):
        for c in data['children']:
            row=index._read_revision(db,pid,c['object_id'],c['revision'])
            if row is None or row['document_sha']!=c['sha256']:
                raise PermissionError('Feature child changed at FilmIndex commit')
    return index.register_revision(pid,object_id,'presentation',deepcopy(data),expected_revision=0,
                                   dependencies=deps,precommit_guard=guard)


def finite_export_plan(index, project_id, source, *, frame_ticks, profile,
                       reel_budget, read_reel, cancelled=lambda: False):
    """Project an exact approved hierarchy into the existing *finite* WO4 path.

    No native job is admitted here. Never flatten beyond the original native
    package and FilmIndex dependency ceilings. The native journal will still
    audit the full original picture/sound/source chain before export and index.
    read_reel is a trusted host lookup returning independently scoped metadata.
    """
    source=ref(source)
    if (type(frame_ticks) is not int or frame_ticks<=0 or type(reel_budget) is not int or
            not 2<=reel_budget<=127 or not callable(read_reel) or not callable(cancelled)):
        raise ValueError('Original bounded cinema admission required')
    record,end,leaf_count,_=inspect(index,project_id,source,frame_ticks=frame_ticks)
    if record['data']['format']!=GROUP:
        raise PermissionError('Exact approved section hierarchy required')
    # A finite source leaf has at least two reels. Reject a huge group before
    # enumerating descendants, not after materializing the entire hierarchy.
    if leaf_count*2>reel_budget:
        raise ValueError('Whole film exceeds current finite native package budget')
    jobs=[];receipts=[];seen=set();cursor=0
    for leaf in walk(index,project_id,source,frame_ticks=frame_ticks):
        if cancelled():raise InterruptedError('Feature export planning cancelled')
        if leaf['start_tick']!=cursor:
            raise PermissionError('Feature section clock is not contiguous')
        child={k:leaf[k] for k in ('object_id','revision','sha256')}
        frozen,_,_,_=inspect(index,project_id,child,frame_ticks=frame_ticks)
        for job_id in frozen['data']['ordered_reel_job_ids']:
            if cancelled():raise InterruptedError('Feature export planning cancelled')
            if len(jobs)>=reel_budget:
                raise ValueError('Whole film exceeds current finite native package budget')
            if type(job_id) is not str or not job_id or job_id in seen:
                raise PermissionError('Repeated or invalid source reel job')
            reel=read_reel(job_id)
            frames=reel.get('frame_count')
            if (reel.get('project_id')!=project_id or reel.get('job_id')!=job_id or
                reel.get('profile')!=profile or reel.get('state')!='DCP_INDEXED' or
                type(frames) is not int or not 3<=frames<=7200 or
                type(reel.get('receipt_sha256')) is not str or not SHA.fullmatch(reel['receipt_sha256'])):
                raise PermissionError('Original indexed reel identity, timing or profile differs')
            cursor+=frames*frame_ticks;seen.add(job_id);jobs.append(job_id)
            receipts.append(reel['receipt_sha256'])
        if cursor!=leaf['end_tick']:
            raise PermissionError('Indexed reels disagree with approved section clock')
    if cursor!=end or not 2<=len(jobs)<=reel_budget:
        raise PermissionError('Incomplete approved hierarchy coverage')
    return {'format':LEAF,'ordered_reel_job_ids':jobs,'start_tick':0,'end_tick':end,
            'hierarchical_source_ref':source,'hierarchical_profile':profile,
            'hierarchical_reel_receipt_sha256':receipts,
            'original_source_modified':False}


def register_finite_export(index,project_id,object_id,source,*,frame_ticks,profile,
                           reel_budget,read_reel,approve,cancelled=lambda:False):
    from backend.nvp_film_index import _id
    _id(object_id,'derived feature assembly')
    source=ref(source)
    if object_id==source['object_id'] or not callable(approve):
        raise PermissionError('New derived assembly and exact creator action required')
    def plan():return finite_export_plan(index,project_id,source,frame_ticks=frame_ticks,
        profile=profile,reel_budget=reel_budget,read_reel=read_reel,cancelled=cancelled)
    data=plan()
    digest=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')).hexdigest()
    if approve({'operation':'nvp.wo4.approve_finite_hierarchical_export_assembly.v1',
                'project_id':project_id,'object_id':object_id,'document_sha256':digest,
                'source_ref':source,'reel_count':len(data['ordered_reel_job_ids']),
                'end_tick':data['end_tick'],'profile':profile,'authorizes_output':False}) is not True:
        return {'status':'DENIED'}
    if plan()!=data:raise PermissionError('Source hierarchy changed during approval')
    def guard(db):
        row=index._read_revision(db,project_id,source['object_id'],source['revision'])
        if row is None or row['document_sha']!=source['sha256'] or cancelled():
            raise PermissionError('Source hierarchy changed at assembly commit')
    return index.register_revision(project_id,object_id,'presentation',data,expected_revision=0,
        dependencies=[{'object_id':source['object_id'],'revision':source['revision'],'role':'presentation'}],
        precommit_guard=guard)


def native_reel_metadata(journal, project_id, job_id):
    """Trusted native journal projection; no fresh media grant or path exposure."""
    j=journal.status_page(job_id,limit=1,expected_project_id=project_id)
    r=journal.reel(job_id); d=journal.delivery(job_id)
    if j['project_id']!=project_id or j['cancel_requested'] or d['phase']!='INDEXED':
        raise PermissionError('Source reel is not indexed in this project')
    return {'job_id':j['job_id'],'project_id':j['project_id'],'state':j['state'],
            'frame_count':r['frame_count'],'profile':r['profile'],'receipt_sha256':d['filmindex_sha256']}
