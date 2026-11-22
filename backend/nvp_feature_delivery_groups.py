"""Native FilmIndex hierarchy of independently indexed finite feature sections.

A delivery group records a verified ordered set of existing packages. It is NOT
one newly assembled DCP, does not publish any files, and has no worker authority.
"""
from copy import deepcopy
import hashlib
import json
from backend import nvp_feature_sections as sections

FORMAT='nvp.wo4.indexed_feature_delivery_group.v1'


def selection(value):
    if type(value) is not dict:raise ValueError('Exact section delivery selection required')
    if set(value)=={'feature_id'}:
        uid=value['feature_id']
        if type(uid) is not str or not sections.ID.fullmatch(uid):raise ValueError('Invalid feature identity')
        return dict(value)
    return sections.ref(value)


def _ref_child(child):return {k:child[k] for k in ('object_id','revision','sha256')}


def _source(index,pid,source,frame_ticks):
    source=sections.ref(source)
    record,_,_,_=sections.inspect(index,pid,source,frame_ticks=frame_ticks)
    if record['data']['format']!=sections.GROUP:raise PermissionError('Approved feature group required')
    doc=record['data'];children=[_ref_child(c) for c in doc['children']]
    if sections.build(index,pid,children,frame_ticks=frame_ticks)!=doc:
        raise PermissionError('Source hierarchy changed')
    return doc,children


def compose(index,pid,source,selections,*,frame_ticks,verify_leaf,ancestors=()):
    """Full independent leaf audit; bounded per-node lists and traversal depth."""
    source=sections.ref(source);doc,children=_source(index,pid,source,frame_ticks)
    if type(selections) is not list or len(selections)!=len(children):raise ValueError('Exact ordered delivery coverage required')
    entries=[];profile=None;count=0
    for src,edge,choice in zip(children,doc['children'],selections):
        choice=selection(choice)
        rec,length,n,depth=sections.inspect(index,pid,src,frame_ticks=frame_ticks)
        if 'feature_id' in choice:
            if rec['data']['format']!=sections.LEAF:raise PermissionError('Grouped source requires grouped delivery')
            verified=verify_leaf(choice['feature_id'],src)
            if (verified.get('feature_id')!=choice['feature_id'] or verified.get('source_ref')!=src or
                    type(verified.get('frame_count')) is not int or verified['frame_count']*frame_ticks!=length or
                    verified.get('production_dcp_accepted') is not False):
                raise PermissionError('Native indexed package differs from approved section')
            receipt_ref=sections.ref(verified['receipt_ref'])
            # Exact independently verified output identity and source binding.
            out=index.read_revision(pid,receipt_ref['object_id'],receipt_ref['revision'])
            if out['kind']!='presentation' or out['document_sha256']!=receipt_ref['sha256']:
                raise PermissionError('Native section receipt changed')
            if type(verified.get('manifest_sha256')) is not str or not sections.SHA.fullmatch(verified['manifest_sha256']):
                raise PermissionError('Missing verified native manifest digest')
            native={'receipt_ref':receipt_ref,'manifest_sha256':verified['manifest_sha256']}
            child_profile=verified['profile']
        else:
            if rec['data']['format']!=sections.GROUP:raise PermissionError('Finite source requires native package')
            nested=verify_group(index,pid,choice,frame_ticks=frame_ticks,verify_leaf=verify_leaf,ancestors=ancestors)
            if nested['source_ref']!=src or nested['end_tick']!=length or nested['section_count']!=n:
                raise PermissionError('Child delivery group differs from source hierarchy')
            native={'receipt_ref':choice};child_profile=nested['profile']
        if type(child_profile) is not str or not 1<=len(child_profile)<=128 or (profile is not None and profile!=child_profile):
            raise PermissionError('Delivery group requires one cinema profile')
        profile=child_profile;count+=n
        entries.append({'source_ref':src,'selection':choice,**native,'start_tick':edge['start_tick'],'end_tick':edge['end_tick']})
    if count!=doc['section_count']:raise PermissionError('Incomplete section coverage')
    return {'format':FORMAT,'source_ref':source,'start_tick':0,'end_tick':doc['end_tick'],
            'section_count':count,'profile':profile,'children':entries,
            'single_dcp_published':False,'production_dcp_accepted':False,'source_modified':False}


def verify_group(index,pid,entry,*,frame_ticks,verify_leaf,ancestors=()):
    entry=sections.ref(entry);key=(entry['object_id'],entry['revision'])
    if key in ancestors or len(ancestors)>=sections.MAX_DEPTH:raise PermissionError('Delivery group recursion limit')
    record=index.read_revision(pid,entry['object_id'],entry['revision']);data=record['data']
    if (record['kind']!='presentation' or record['document_sha256']!=entry['sha256'] or data.get('format')!=FORMAT or
            type(data.get('children')) is not list or not 2<=len(data['children'])<=sections.MAX_CHILDREN):
        raise PermissionError('Exact native delivery group required')
    result=compose(index,pid,data['source_ref'],[c['selection'] for c in data['children']],
                   frame_ticks=frame_ticks,verify_leaf=verify_leaf,ancestors=ancestors+(key,))
    if result!=data:raise PermissionError('Native delivery group evidence differs')
    return result


def register(index,pid,oid,source,selections,*,frame_ticks,verify_leaf,approve):
    if type(oid) is not str or not sections.ID.fullmatch(oid):raise ValueError('Invalid delivery group identity')
    source=sections.ref(source)
    data=compose(index,pid,source,selections,frame_ticks=frame_ticks,verify_leaf=verify_leaf)
    digest=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')).hexdigest()
    scope={'operation':'nvp.wo4.register_feature_delivery_group.v1','project_id':pid,'object_id':oid,
           'document_sha256':digest,'section_count':data['section_count'],'end_tick':data['end_tick'],
           'single_dcp_published':False,'production_dcp_accepted':False}
    if approve(scope) is not True:return {'status':'DENIED'}
    if compose(index,pid,source,selections,frame_ticks=frame_ticks,verify_leaf=verify_leaf)!=data:
        raise PermissionError('Native delivery changed during consent')
    refs=[source]+[c['receipt_ref'] for c in data['children']]
    if len({(r['object_id'],r['revision']) for r in refs})!=len(refs) or any(r['object_id']==oid for r in refs):
        raise PermissionError('Duplicate or self delivery receipt')
    def guard(db):
        for r in refs:
            row=index._read_revision(db,pid,r['object_id'],r['revision'])
            if row is None or row['document_sha']!=r['sha256']:raise PermissionError('Indexed delivery receipt changed at commit')
    deps=[{'object_id':r['object_id'],'revision':r['revision'],'role':'presentation'} for r in refs]
    return index.register_revision(pid,oid,'presentation',deepcopy(data),expected_revision=0,dependencies=deps,precommit_guard=guard)
