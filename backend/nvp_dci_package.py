"""Independent strict NVP unsigned, unencrypted, single-volume DCP subset.

Profile grammar derived from ST 429-7:2006, 429-8:2007, 429-9:2014.
Not a general SMPTE validator; unknown optional profiles fail closed. Legacy
structural-only receipts remain legacy. No schema downloads or codec authority.
"""
from datetime import datetime
from fractions import Fraction
import base64
import hashlib
from pathlib import Path
import re
import stat
import uuid
import xml.etree.ElementTree as ET

from backend.nvp_wo3_dcp_structure import (NS_AM, NS_PKL, NS_CPL, MAX_XML_BYTES,
    MAX_PACKAGE_BYTES, MAX_ASSETS, _asset_file, _linked_entry, inspect_dcp_structure)

FORMAT = 'nvp.dci.package_profile.v1'
# Separate from the producer profile constants; accepted delivery raster ratios.
ASPECTS = {Fraction(1998,1080), Fraction(2048,858), Fraction(3996,2160),
           Fraction(4096,1716), Fraction(2048,1080), Fraction(4096,2160)}


def _require(condition, detail):
    if not condition:
        raise ValueError('NVP DCP profile: '+detail)


def _tag(ns,name):
    return '{'+ns+'}'+name


def _children(node, ns, names):
    _require(not node.attrib and not (node.text or '').strip(), 'unexpected container attributes/text')
    _require([x.tag for x in node] == [_tag(ns,n) for n in names], 'child sequence: '+node.tag)
    _require(all(not (x.tail or '').strip() for x in node), 'mixed content')
    return list(node)


def _list(node,ns,name,minimum,maximum):
    _require(not node.attrib and not (node.text or '').strip(), 'invalid list')
    rows=list(node)
    _require(minimum<=len(rows)<=maximum and all(x.tag==_tag(ns,name) and not (x.tail or '').strip() for x in rows), 'list content: '+name)
    return rows


def _text(node, *, user=False):
    _require(not list(node) and (not node.attrib or (user and set(node.attrib)=={'language'} and re.fullmatch(r'[A-Za-z]{1,8}(?:-[A-Za-z0-9]{1,8})*',node.attrib['language']))), 'invalid leaf: '+node.tag)
    value=node.text or ''
    _require(bool(value.strip()) and len(value)<=4096,'empty/oversized field: '+node.tag)
    return value


def _uuid(node, *, version=None):
    value=_text(node)
    _require(re.fullmatch(r'urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',value) is not None,'noncanonical UUID')
    ident=uuid.UUID(value[9:])
    _require(ident.variant==uuid.RFC_4122 and (version is None or ident.version==version),'UUID variant/version')
    return str(ident)


def _integer(node, minimum=0, maximum=2**63-1):
    raw=_text(node)
    _require(re.fullmatch(r'0|[1-9][0-9]{0,18}',raw) is not None,'invalid integer')
    value=int(raw)
    _require(minimum<=value<=maximum,'integer outside profile')
    return value


def _date(node):
    raw=_text(node)
    _require(re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)',raw) is not None,'invalid dateTime')
    try:
        result=datetime.fromisoformat(raw.replace('Z','+00:00'))
    except ValueError as exc:
        raise ValueError('invalid issue date') from exc
    _require(result.tzinfo is not None and abs(result.utcoffset().total_seconds())<=14*3600,'invalid zone')
    return raw


def _ratio(node):
    raw=_text(node)
    _require(re.fullmatch(r'[1-9][0-9]{0,8} [1-9][0-9]{0,8}',raw) is not None,'invalid rational')
    return Fraction(*map(int,raw.split()))


def _digest(node):
    raw=_text(node)
    try: data=base64.b64decode(raw,validate=True)
    except ValueError as exc: raise ValueError('invalid SHA1 base64') from exc
    _require(len(data)==20 and base64.b64encode(data).decode('ascii')==raw,'noncanonical SHA1')
    return raw


def _read_xml(root, name, ns, tag):
    path=_asset_file(root,name)
    with path.open('rb') as stream: raw=stream.read(MAX_XML_BYTES+1)
    _require(0<len(raw)<=MAX_XML_BYTES and b'\x00' not in raw and b'<!' not in raw,'unsafe XML')
    raw.decode('utf-8',errors='strict')
    body=raw.removeprefix(b'\xef\xbb\xbf')
    if body.startswith(b'<?xml '):
        declaration,separator,body=body.partition(b'?>')
        _require(bool(separator),'invalid XML declaration')
        encoding=re.search(rb'encoding\s*=\s*[\"\']([^\"\']+)[\"\']',declaration,re.I)
        _require(encoding is None or encoding.group(1).lower()==b'utf-8','non-UTF8 XML declaration')
    _require(b'<?' not in body,'processing instruction')
    try: node=ET.fromstring(raw)
    except ET.ParseError as exc: raise ValueError('malformed package XML') from exc
    _require(node.tag==_tag(ns,tag),'root/namespace mismatch')
    return node,hashlib.sha256(raw).hexdigest()


def inspect_cinema_package(folder, *, expected_profile=None, expected_reels=None,
                           require_minimum_track=False):
    """Read-back schema/semantic checks for newly authored NVP packages.

    The caller may bind trusted reel IDs, frame counts and profile. Minimum
    one-second tracks are a separate gate; 3-frame historical pilots may pass
    the structure but not this minimum. No physical or normative acceptance.
    """
    root=Path(folder)
    _require(root.is_dir() and not any(_linked_entry(p) for p in (root,*root.parents)),'untrusted folder')
    root=root.resolve(strict=True)
    # Read exact XML first and compare to hash-audit results and readbacks.
    am,am_sha=_read_xml(root,'ASSETMAP.xml',NS_AM,'AssetMap')
    vol,vol_sha=_read_xml(root,'VOLINDEX.xml',NS_AM,'VolumeIndex')
    _require(_integer(_children(vol,NS_AM,['Index'])[0],1,1)==1,'volume index')
    aid,ann,creator,volcount,issued,issuer,a_list=_children(am,NS_AM,['Id','AnnotationText','Creator','VolumeCount','IssueDate','Issuer','AssetList'])
    am_id=_uuid(aid,version=4); _text(ann,user=True); _text(creator,user=True); _integer(volcount,1,1); _date(issued); _text(issuer,user=True)
    locations={}; pkl_ids=[]
    for row in _list(a_list,NS_AM,'Asset',4,MAX_ASSETS):
        is_pkl=len(row)==3
        fields=_children(row,NS_AM,['Id','PackingList','ChunkList'] if is_pkl else ['Id','ChunkList'])
        ident=_uuid(fields[0],version=4)
        if is_pkl:
            _require(_text(fields[1])=='true','packing list flag'); pkl_ids.append(ident)
        chunk=_list(fields[-1],NS_AM,'Chunk',1,1)[0]
        name,volume,offset,length=_children(chunk,NS_AM,['Path','VolumeIndex','Offset','Length'])
        name=_text(name); _asset_file(root,name); _integer(volume,1,1); _integer(offset,0,0)
        _require(ident not in locations and ident!=am_id,'duplicate/colliding AM id')
        locations[ident]=(name,_integer(length,1,MAX_PACKAGE_BYTES))
    _require(len(pkl_ids)==1,'one packing list')
    pkl_id=pkl_ids[0]; pkl_name=locations[pkl_id][0]
    _require(pkl_name=='PKL.xml','NVP packing list path')
    pkl,pkl_sha=_read_xml(root,pkl_name,NS_PKL,'PackingList')
    pid,ann,issued,issuer,creator,alist=_children(pkl,NS_PKL,['Id','AnnotationText','IssueDate','Issuer','Creator','AssetList'])
    _require(_uuid(pid,version=4)==pkl_id,'packing list id'); _text(ann,user=True);_date(issued);_text(issuer,user=True);_text(creator,user=True)
    records={}
    for row in _list(alist,NS_PKL,'Asset',3,MAX_ASSETS):
        ident,ann,digest,size,mime,name=_children(row,NS_PKL,['Id','AnnotationText','Hash','Size','Type','OriginalFileName'])
        ident=_uuid(ident,version=4); _text(ann,user=True); filename=_text(name,user=True); size=_integer(size,1,MAX_PACKAGE_BYTES); mime=_text(mime); digest=_digest(digest)
        _require(mime in ('application/mxf','text/xml') and filename.endswith('.mxf' if mime=='application/mxf' else '.xml'),'file type mismatch')
        _require(ident not in records and ident!=pkl_id and locations.get(ident)==(filename,size),'PKL/AM mismatch')
        records[ident]=(filename,mime,digest)
    _require(set(locations)==set(records)|{pkl_id},'unpacked asset')
    cpls=[(i,v) for i,v in records.items() if v[1]=='text/xml']
    _require(len(cpls)==1 and cpls[0][1][0]=='CPL.xml','one composition')
    cpl_id=cpls[0][0]; cpl,cpl_sha=_read_xml(root,'CPL.xml',NS_CPL,'CompositionPlaylist')
    cid,ann,issued,issuer,creator,title,kind,version,ratings,reels=_children(cpl,NS_CPL,['Id','AnnotationText','IssueDate','Issuer','Creator','ContentTitleText','ContentKind','ContentVersion','RatingList','ReelList'])
    _require(_uuid(cid,version=4)==cpl_id,'composition id'); _text(ann,user=True);_date(issued);_text(issuer,user=True);_text(creator,user=True);_text(title,user=True)
    _require(_text(kind)=='feature','unsupported content kind')
    cv_id,label=_children(version,NS_CPL,['Id','LabelText']); cv_id=_uuid(cv_id);_text(label,user=True)
    _require(cv_id not in locations and cv_id!=am_id,'content version identity collides')
    _list(ratings,NS_CPL,'Rating',0,0) # empty, never invent classification
    reel_rows=[]; used=set(); reel_ids=set(); total=0; aspect=None
    for reel in _list(reels,NS_CPL,'Reel',1,1000):
        rid,alist=_children(reel,NS_CPL,['Id','AssetList']); rid=_uuid(rid,version=4)
        _require(rid not in locations and rid not in reel_ids and rid not in (am_id,cv_id),'reel identity collision');reel_ids.add(rid)
        row={'reel_uuid':rid,'start_frame':total}
        pic,snd=_children(alist,NS_CPL,['MainPicture','MainSound'])
        durations=[]
        for typ,entry in [('picture',pic),('sound',snd)]:
            fields=_children(entry,NS_CPL,['Id','EditRate','IntrinsicDuration','EntryPoint','Duration','Hash']+(['FrameRate','ScreenAspectRatio'] if typ=='picture' else []))
            ident=_uuid(fields[0],version=4);_require(ident not in used and ident in records and records[ident][1]=='application/mxf','duplicate or unknown track')
            used.add(ident);_require(_ratio(fields[1])==24,'edit rate'); intrinsic=_integer(fields[2],1);_integer(fields[3],0,0);duration=_integer(fields[4],1)
            _require(intrinsic==duration,'NVP full untrimmed track duration required');_require(_digest(fields[5])==records[ident][2],'CPL track hash differs from PKL')
            durations.append(duration);row[typ+'_uuid']=ident
            if typ=='picture':
                _require(_ratio(fields[6])==24,'frame rate'); current=_ratio(fields[7]);_require(current in ASPECTS and (aspect is None or current==aspect),'invalid or mixed aspect ratio');aspect=current
        _require(durations[0]==durations[1],'picture/sound duration mismatch'); row['frames']=durations[0]; total+=durations[0];reel_rows.append(row)
    _require(used=={i for i,v in records.items() if v[1]=='application/mxf'},'unreferenced essence')
    expected_names={'ASSETMAP.xml','VOLINDEX.xml'}|{v[0] for v in locations.values()}
    _require(len(expected_names)==len(locations)+2 and len({n.casefold() for n in expected_names})==len(expected_names),'filename alias or reserved metadata collision')
    listed=list(root.iterdir());_require({p.name for p in listed}==expected_names,'extra or missing package files')
    file_ids=set()
    for file in listed:
        s=file.lstat();fid=(s.st_dev,s.st_ino)
        _require(stat.S_ISREG(s.st_mode) and not _linked_entry(file) and s.st_nlink==1 and fid not in file_ids,'linked/aliased/nonregular file');file_ids.add(fid)
    if expected_profile is not None:
        from backend.nvp_wo3_j2k_audit import PROFILES
        _require(expected_profile in PROFILES,'unsupported expected profile');w,h,_=PROFILES[expected_profile];_require(aspect==Fraction(w,h),'approved profile aspect mismatch')
    if expected_reels is not None:
        _require(reel_rows==expected_reels,'approved reel identities/order/ranges differ')
    minimum=all(row['frames']>=24 for row in reel_rows)
    _require(minimum or not require_minimum_track,'one second minimum track duration')
    _require(sum(v[1] for v in locations.values())<=MAX_PACKAGE_BYTES,'package byte budget')
    audit=inspect_dcp_structure(root)
    _require(audit['cpl_uuid']==cpl_id and audit['pkl_uuid']==pkl_id and audit['assets'][cpl_id]['sha256']==cpl_sha and audit['reel_durations']==[r['frames'] for r in reel_rows],'independent structural hash readback differs')
    for name,ns,tag,expected in [('ASSETMAP.xml',NS_AM,'AssetMap',am_sha),('VOLINDEX.xml',NS_AM,'VolumeIndex',vol_sha),(pkl_name,NS_PKL,'PackingList',pkl_sha),('CPL.xml',NS_CPL,'CompositionPlaylist',cpl_sha)]:
        _require(_read_xml(root,name,ns,tag)[1]==expected,'metadata changed during audit')
    return {**audit,'package_profile_format':FORMAT,'nvp_unsigned_xml_profile_verified':True,
            'official_smpte_xsd_verified':False,'all_tracks_minimum_one_second_verified':minimum,
            'reel_manifest':reel_rows,'total_frames':total,'screen_aspect_ratio':[aspect.numerator,aspect.denominator],
            'metadata_sha256':{ 'ASSETMAP.xml':am_sha,'VOLINDEX.xml':vol_sha,pkl_name:pkl_sha,'CPL.xml':cpl_sha},
            'mxf_descriptor_crosscheck_verified':False,'production_dcp_accepted':False}


def verify_native_track_descriptor(props, *, kind, asset_id, frames, profile, channels=None):
    """Check a pinned asdcp-info readback against approved CPL/essence identity.

    Called only with results from the protected worker, never UI metadata.
    This function by itself is not evidence of native execution.
    """
    from backend.nvp_wo3_mxf_native import _verify_info
    from backend.nvp_wo3_j2k_audit import PROFILES
    _verify_info(props,asset_id,frames)
    _require(props.get('label_set_type','').startswith('SMPTE'),'MXF not SMPTE')
    def prop(*names):
        values=[props[n] for n in names if n in props]
        _require(bool(values) and len(set(values))==1,'missing/conflicting MXF property: '+names[0])
        return values[0]
    if kind=='picture':
        w,h,_=PROFILES[profile]
        _require(prop('storedwidth','stored_width')==str(w) and prop('storedheight','stored_height')==str(h),'MXF stored raster mismatch')
    elif kind=='sound':
        _require(type(channels) is int and channels in (2,6,8,16),'invalid expected sound channel count')
        _require(prop('audiosamplingrate','audio_sampling_rate')=='48000/1' and prop('quantizationbits','quantization_bits')=='24' and prop('channelcount','channel_count')==str(channels),'MXF audio descriptor mismatch')
    else:raise ValueError('unsupported track kind')
    return True
