"""NVP-PROD-06C: bounded, immutable local rigged GLB and director-approved bone retarget.

Previs only. The GLB and declared rights are NOT proof of commercial suitability.
No executable code is read from model files; Blender importer runs in a separate
trusted production process when actual geometry is evaluated.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
from backend.nvp_w1g_owned_subprocess import run_owned_subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile

from backend.nvp_studio import Studio
from backend.nvp_production_scene import compact, digest
from backend.nvp_rig_motion import ROLES
from backend.nvp_skinning import SkinnedPerformance
from backend.nvp_mesh_assets import validate_license
from backend.nvp_blender_acceptance import blender_available

MAX_GLB_BYTES = 32 * 1024 * 1024
MAX_NODES = 512
MAX_JOINTS = 128
MAX_VERTICES = 250_000
MAX_MESHES = 32
MAX_INSTANCES = 16
_GLTF_ACCESSOR_COMPONENTS = {5120:1,5121:1,5122:2,5123:2,5125:4,5126:4}
_GLTF_ACCESSOR_FIELDS = {'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}


def inspect_rigged_glb(payload: bytes) -> dict:
    """Bounded structural and binary-accessor validation, not a Blender import proof.

    Intentionally supports a conservative subset: one skin, no sparse accessors,
    no required extensions, external buffer/image URIs, or embedded animations.
    """
    if not isinstance(payload,bytes) or not 32 <= len(payload) <= MAX_GLB_BYTES:
        raise ValueError('A local rigged GLB under 32 MiB is required')
    if payload[:4] != b'glTF' or struct.unpack_from('<II',payload,4)!=(2,len(payload)):
        raise ValueError('Invalid GLB 2.0 header')
    pos=12; chunks=[]
    while pos < len(payload):
        if pos+8>len(payload):raise ValueError('Truncated GLB chunk header')
        length,kind=struct.unpack_from('<II',payload,pos)
        pos+=8
        if length%4 or pos+length>len(payload):raise ValueError('Malformed GLB chunk length')
        chunks.append((kind,payload[pos:pos+length]));pos+=length
        if len(chunks)>2:raise ValueError('Only a JSON and a BIN chunk are supported')
    if len(chunks)!=2 or chunks[0][0]!=0x4E4F534A or chunks[1][0]!=0x004E4942:
        raise ValueError('Rigged GLB requires ordered JSON and BIN chunks')
    try:doc=json.loads(chunks[0][1].rstrip(b' \x00').decode('utf8'))
    except (UnicodeError,ValueError,TypeError) as exc:raise ValueError('Invalid GLB JSON') from exc
    binary=chunks[1][1]
    if not isinstance(doc,dict) or doc.get('asset',{}).get('version')!='2.0':
        raise ValueError('Not a glTF 2.0 asset')
    if doc.get('extensionsRequired') or doc.get('animations'):
        raise ValueError('Unsupported glTF extensions or pre-existing animations')
    if not isinstance(doc.get('buffers'),list) or len(doc['buffers'])!=1:
        raise ValueError('Only one self-contained GLB buffer is accepted')
    buff=doc['buffers'][0]
    if 'uri' in buff or not isinstance(buff.get('byteLength'),int) or buff['byteLength']>len(binary) or buff['byteLength']<0:
        raise ValueError('External or truncated GLB buffer')
    for img in doc.get('images',[]):
        if 'uri' in img:raise ValueError('External image URI is forbidden')
    for node in doc.get('nodes',[]):
        if 'extensions' in node:raise ValueError('Unreviewed glTF node extensions')
    nodes=doc.get('nodes',[]); meshes=doc.get('meshes',[])
    skins=doc.get('skins',[]); views=doc.get('bufferViews',[]); accessors=doc.get('accessors',[])
    if not isinstance(nodes,list) or not 1<=len(nodes)<=MAX_NODES:
        raise ValueError('Invalid node budget')
    if not isinstance(meshes,list) or not 1<=len(meshes)<=MAX_MESHES:
        raise ValueError('Invalid mesh budget')
    if not isinstance(skins,list) or len(skins)!=1:
        raise ValueError('A single, explicit skinned armature is required')
    if not all(isinstance(v,dict) and v.get('buffer')==0 and
               isinstance(v.get('byteOffset',0),int) and isinstance(v.get('byteLength'),int) and
               0<=v.get('byteOffset',0)<=buff['byteLength'] and
               0<=v['byteLength']<=buff['byteLength']-v.get('byteOffset',0) for v in views):
        raise ValueError('Invalid GLB bufferView bounds')
    if len(views)>2048 or len(accessors)>4096:raise ValueError('GLB accessor budget exceeded')
    for i,a in enumerate(accessors):
        if not isinstance(a,dict) or 'sparse' in a or not isinstance(a.get('bufferView'),int):
            raise ValueError('Sparse or missing-buffer accessor is unsupported')
        vi=a['bufferView']
        if not 0<=vi<len(views):raise ValueError('Invalid GLB accessor view')
        v=views[vi];component=a.get('componentType');kind=a.get('type');count=a.get('count')
        if component not in _GLTF_ACCESSOR_COMPONENTS or kind not in _GLTF_ACCESSOR_FIELDS or not isinstance(count,int) or not 1<=count<=MAX_VERTICES*4:
            raise ValueError('Invalid or oversized GLB accessor')
        stride=_GLTF_ACCESSOR_COMPONENTS[component]*_GLTF_ACCESSOR_FIELDS[kind]
        offset=a.get('byteOffset',0)
        width=v.get('byteStride',stride)
        if (not isinstance(offset,int) or offset<0 or not isinstance(width,int) or width<stride or
                width>252 or offset + (count-1)*width + stride>v['byteLength']):
            raise ValueError('Accessor crosses its buffer view')
    skin=skins[0]; joints=skin.get('joints')
    if not isinstance(joints,list) or not 3<=len(joints)<=MAX_JOINTS or len(joints)!=len(set(joints)):
        raise ValueError('Invalid armature joints')
    if not all(isinstance(i,int) and not isinstance(i,bool) and 0<=i<len(nodes) for i in joints):
        raise ValueError('Skin references an invalid joint')
    names=[nodes[i].get('name') for i in joints]
    if not all(isinstance(n,str) and n and len(n)<=100 and '\x00' not in n for n in names) or len(names)!=len(set(names)):
        raise ValueError('Joint names must be unique and nonempty')
    if 'inverseBindMatrices' in skin:
        i=skin['inverseBindMatrices']
        if not isinstance(i,int) or not 0<=i<len(accessors) or accessors[i]['type']!='MAT4' or accessors[i]['count']!=len(joints):
            raise ValueError('Invalid inverse-bind matrices')
    total=0; linked=0
    for node in nodes:
        if 'skin' not in node:continue
        if node['skin']!=0 or not isinstance(node.get('mesh'),int) or not 0<=node['mesh']<len(meshes):
            raise ValueError('Skinned node has invalid mesh')
        linked+=1
        for primitive in meshes[node['mesh']].get('primitives',[]):
            a=primitive.get('attributes',{})
            needed={'POSITION':'VEC3','JOINTS_0':'VEC4','WEIGHTS_0':'VEC4'}
            counts=[]
            for label,kind in needed.items():
                idx=a.get(label)
                if not isinstance(idx,int) or not 0<=idx<len(accessors) or accessors[idx]['type']!=kind:
                    raise ValueError(f'Skinned mesh is missing {label}')
                counts.append(accessors[idx]['count'])
            if len(set(counts))!=1:raise ValueError('Vertex skin attribute counts disagree')
            jtype=accessors[a['JOINTS_0']]['componentType']
            wtype=accessors[a['WEIGHTS_0']]['componentType']
            if jtype not in (5121,5123) or wtype not in (5121,5123,5126) or accessors[a['POSITION']]['componentType']!=5126:
                raise ValueError('Unsupported joint/weight/position encoding')
            total+=counts[0]
    if linked<1 or total<3 or total>MAX_VERTICES:
        raise ValueError('GLB must contain a bounded skinned mesh')
    return {'format':'nvp.character.glb.v1','sha256':hashlib.sha256(payload).hexdigest(),
            'joint_names':names,'joint_count':len(joints),'skinned_vertices':total,
            'skinned_nodes':linked,'license_verified':False,
            'limitations':'Validated glTF structure and byte ranges only; Blender deformation must be audited'}


class CharacterAssets:
    """Immutable local asset registry and scene-scoped director bindings."""
    def __init__(self,studio:Studio):
        self.studio=studio;self.skin=SkinnedPerformance(studio)
        self.root=(studio.db_path.parent/'nvp_rigged_store').resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        with studio._connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS prod_character_assets (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                asset_id TEXT NOT NULL, sha TEXT NOT NULL, info_json TEXT NOT NULL,
                license TEXT NOT NULL, attribution TEXT NOT NULL, source TEXT NOT NULL,
                PRIMARY KEY(project_id,asset_id))''')
            db.execute('''CREATE TABLE IF NOT EXISTS prod_character_sessions (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, revision INTEGER NOT NULL, status TEXT NOT NULL,
                skin_sha TEXT NOT NULL, plan_json TEXT NOT NULL, approval_sha TEXT,
                PRIMARY KEY(project_id,scene_id))''')
            db.execute('''CREATE TABLE IF NOT EXISTS prod_character_history (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, revision INTEGER NOT NULL, action TEXT NOT NULL,
                snapshot_json TEXT NOT NULL, PRIMARY KEY(project_id,scene_id,revision))''')

    def register(self,project_id:str,payload:bytes,license_code:str,attribution='',source=''):
        self.studio.get_project(project_id)
        validate_license(license_code,attribution,source)
        info=inspect_rigged_glb(payload);sha=info['sha256']
        aid='CHR_'+digest([project_id,sha,license_code,attribution,source])[:24]
        blob=self.root/(sha+'.glb')
        if not blob.exists():
            with NamedTemporaryFile(dir=self.root,prefix='.rig_',suffix='.tmp',delete=False) as stream:
                stream.write(payload);stream.flush();os.fsync(stream.fileno());temp=Path(stream.name)
            os.replace(temp,blob)
        if hashlib.sha256(blob.read_bytes()).hexdigest()!=sha:
            raise RuntimeError('Rigged character content-addressed blob corrupted')
        with self.studio._connection() as db:
            db.execute('INSERT OR IGNORE INTO prod_character_assets VALUES (?,?,?,?,?,?,?)',
                       (project_id,aid,sha,compact(info),license_code,attribution,source))
        return {'asset_id':aid,**info,'license':license_code,'attribution':attribution,'source':source}

    def list(self,project_id):
        self.studio.get_project(project_id)
        with self.studio._connection() as db:
            return [{'asset_id':r['asset_id'],'license':r['license'],'attribution':r['attribution'],
                     'source':r['source'],**json.loads(r['info_json'])} for r in db.execute(
                'SELECT * FROM prod_character_assets WHERE project_id=? ORDER BY asset_id',(project_id,))]

    def _asset(self,db,project_id,asset_id):
        row=db.execute('SELECT * FROM prod_character_assets WHERE project_id=? AND asset_id=?',(project_id,asset_id)).fetchone()
        if not row:raise KeyError('Character asset does not belong to this project')
        return dict(row)

    def _context(self,project_id,scene_id):
        pkg=self.skin.export(project_id,scene_id)
        return pkg,digest(pkg['skin'])

    def create(self,project_id,scene_id):
        pkg,sha=self._context(project_id,scene_id)
        roster=[x['instance_id'] for x in pkg['skin']['actors']]
        if not roster or len(roster)>MAX_INSTANCES:raise ValueError('Missing approved actor for rigged character binding')
        plan={'format':'nvp.character.bindings.v1','actors':[]}
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM prod_character_sessions WHERE project_id=? AND scene_id=?',(project_id,scene_id)).fetchone():
                raise RuntimeError('Rigged character session already exists')
            db.execute('INSERT INTO prod_character_sessions VALUES (?,?,?,?,?,?,?)',
                       (project_id,scene_id,0,'draft',sha,compact(plan),None))
            db.execute('INSERT INTO prod_character_history VALUES (?,?,?,?,?)',
                       (project_id,scene_id,0,'create',compact(plan)))
        return self.read(project_id,scene_id)

    def _row(self,db,pid,sid):
        row=db.execute('SELECT * FROM prod_character_sessions WHERE project_id=? AND scene_id=?',(pid,sid)).fetchone()
        if not row:raise KeyError('Rigged character session does not exist')
        return dict(row)

    def read(self,pid,sid):
        _,current=self._context(pid,sid)
        with self.studio._connection() as db:row=self._row(db,pid,sid)
        return {'project_id':pid,'scene_id':sid,'revision':row['revision'],
                'status':row['status'],'stale':row['skin_sha']!=current,
                'actors':json.loads(row['plan_json'])['actors'],'approval_sha':row['approval_sha']}

    def bind(self,pid,sid,actor_id,asset_id,role_map,expected_revision,scale=1.0):
        if (not isinstance(role_map,dict) or set(role_map)!=set(ROLES) or
            len(set(role_map.values()))!=len(ROLES)):
            raise ValueError('Explicit, one-to-one mapping for all seven preview roles required')
        if isinstance(scale,bool) or not isinstance(scale,(int,float)) or not math.isfinite(scale) or not .1<=scale<=10:
            raise ValueError('Character scale must be finite in [0.1,10]')
        pkg,sha=self._context(pid,sid)
        actors={x['instance_id'] for x in pkg['skin']['actors']}
        if actor_id not in actors:raise KeyError('Actor does not belong to approved motion take')
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=self._row(db,pid,sid)
            if isinstance(expected_revision,bool) or row['revision']!=expected_revision or row['status']!='draft' or row['skin_sha']!=sha:
                raise RuntimeError('Rig binding revision, approval, or motion changed')
            source=self._asset(db,pid,asset_id)
            info=json.loads(source['info_json'])
            if not all(isinstance(name,str) and name in info['joint_names'] for name in role_map.values()):
                raise ValueError('Mapped joint missing in registered character')
            plan=json.loads(row['plan_json'])
            plan['actors']=[x for x in plan['actors'] if x['instance_id']!=actor_id]
            plan['actors'].append({'instance_id':actor_id,'character_asset_id':asset_id,
                                   'role_map':role_map,'uniform_scale':float(scale),'author':'director'})
            plan['actors'].sort(key=lambda x:x['instance_id'])
            nextrev=row['revision']+1
            db.execute('UPDATE prod_character_sessions SET revision=?,plan_json=? WHERE project_id=? AND scene_id=?',
                       (nextrev,compact(plan),pid,sid))
            db.execute('INSERT INTO prod_character_history VALUES (?,?,?,?,?)',
                       (pid,sid,nextrev,'bind',compact(plan)))
        return self.read(pid,sid)

    def approve(self,pid,sid,expected_revision):
        pkg,sha=self._context(pid,sid)
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=self._row(db,pid,sid)
            if row['revision']!=expected_revision or row['status']!='draft' or row['skin_sha']!=sha:
                raise RuntimeError('Rigged character approval is stale or already finalized')
            plan=json.loads(row['plan_json'])
            if not plan['actors']:raise ValueError('A mapped character must be bound before approval')
            for binding in plan['actors']:self._asset(db,pid,binding['character_asset_id'])
            approval=digest([sha,plan])
            nextrev=row['revision']+1
            db.execute('UPDATE prod_character_sessions SET revision=?,status=?,approval_sha=? WHERE project_id=? AND scene_id=?',
                       (nextrev,'approved',approval,pid,sid))
            db.execute('INSERT INTO prod_character_history VALUES (?,?,?,?,?)',
                       (pid,sid,nextrev,'approve',compact(plan)))
        return self.read(pid,sid)

    def history(self,pid,sid):
        self.studio.get_project(pid)
        with self.studio._connection() as db:
            return [dict(x) for x in db.execute('SELECT revision,action,snapshot_json FROM prod_character_history '
                     'WHERE project_id=? AND scene_id=? ORDER BY revision',(pid,sid))]

    def export(self,pid,sid):
        pkg,sha=self._context(pid,sid)
        with self.studio._connection() as db:
            row=self._row(db,pid,sid)
            plan=json.loads(row['plan_json'])
            if row['status']!='approved' or row['skin_sha']!=sha or row['approval_sha']!=digest([sha,plan]):
                raise RuntimeError('Only director-approved, current rig bindings may be exported')
            records=[]
            for bind in plan['actors']:
                a=self._asset(db,pid,bind['character_asset_id'])
                sha256=a['sha'];blob=self.root/(sha256+'.glb')
                if not blob.is_file() or hashlib.sha256(blob.read_bytes()).hexdigest()!=sha256:
                    raise RuntimeError('Rigged asset has changed or disappeared')
                records.append({'instance_id':bind['instance_id'],'character_asset_id':bind['character_asset_id'],
                                'sha256':sha256,'file':'assets/'+sha256+'.glb',
                                'role_map':bind['role_map'],'uniform_scale':bind['uniform_scale'],
                                'license':a['license'],'attribution':a['attribution'],'source':a['source']})
        return {**pkg,'character':{'format':'nvp.production.character.v1','skin_sha':sha,
                'approval_sha':row['approval_sha'],'bindings':records,
                'rights_status':'creator_declared_not_independently_verified'}}

    def export_bundle(self,pid,sid,directory):
        pkg=self.export(pid,sid)
        out=Path(directory).resolve();out.mkdir(parents=True,exist_ok=True)
        assets=out/'assets';assets.mkdir(exist_ok=True)
        for item in pkg['character']['bindings']:
            blob=self.root/(item['sha256']+'.glb');target=assets/(item['sha256']+'.glb')
            if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest()!=item['sha256']:
                shutil.copyfile(blob,target)
        (out/'character.json').write_text(compact(pkg),'utf8')
        (out/'licenses.json').write_text(json.dumps([{k:x[k] for k in ('character_asset_id','sha256','license','attribution','source')}
                                 for x in pkg['character']['bindings']],indent=2),'utf8')
        (out/'build_characters.py').write_text(inject_character_script(self.skin.blender_script(pid,sid),pkg),'utf8')
        (out/'audit_characters.py').write_text(CHARACTER_AUDIT_SCRIPT,'utf8')
        return {'status':'exported_for_blender_validation','path':str(out),'actors':len(pkg['character']['bindings'])}


# Import does not grant permissions or author script. The generated Python is a
# trusted template; source GLB bytes are verified and parsed with Blender's importer.
CHARACTER_SCRIPT = r'''# NVP-PROD-06C: explicit external humanoid, no external dependencies.
import hashlib
from pathlib import Path
from mathutils import Euler
character=json.loads(CHARACTER_PAYLOAD)
for binding in character['bindings']:
    rid=binding['instance_id']
    target=Path(__file__).resolve().parent/binding['file']
    if target.name!=binding['sha256']+'.glb' or target.parent.name!='assets':
        raise ValueError('Invalid rigged GLB filename')
    if hashlib.sha256(target.read_bytes()).hexdigest()!=binding['sha256']:
        raise ValueError('Changed rigged GLB: refusing import')
    before=set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(target))
    imported=set(bpy.data.objects)-before
    rigs=[obj for obj in imported if obj.type=='ARMATURE']
    if len(rigs)!=1:raise RuntimeError('Rigged GLB did not import one Blender armature')
    rig=rigs[0];actor=bpy.data.objects['NVP_'+rid]
    if not all(name in rig.pose.bones for name in binding['role_map'].values()):
        raise RuntimeError('Imported rig does not contain the approved bone map')
    meshes=[obj for obj in imported if obj.type=='MESH' and any(
        m.type=='ARMATURE' and m.object==rig for m in obj.modifiers)]
    if not meshes:raise RuntimeError('Imported GLB has no skinned mesh')
    rig.name='NVP_CHARACTER_RIG_'+rid
    rig.parent=actor;rig.matrix_parent_inverse.identity()
    height=float(next(x['height_m'] for x in take['actors'] if x['instance_id']==rid))
    rig.location=(0,0,-height/2)
    rig.rotation_euler=(0,0,0)
    rig.scale=[binding['uniform_scale']]*3
    rig['nvp_character_asset_id']=binding['character_asset_id']
    rig['nvp_character_sha']=binding['sha256']
    for obj in meshes:
        obj['nvp_character_actor']=rid
        obj['nvp_character_sha']=binding['sha256']
    source=bpy.data.objects['NVP_RIG_'+rid]
    skin=bpy.data.objects['NVP_SKIN_'+rid]
    skin.hide_render=True
    for segment in next(x for x in motion['plan']['actors'] if x['instance_id']==rid)['segments']:
        clip=motion['clips'][segment['clip_id']]
        for sample in clip['frames']:
            frame=segment['start_frame']+sample['frame']*take['fps']/clip['fps']
            for role,bone_name in binding['role_map'].items():
                if role not in sample['joints']:continue
                # Reuse director-approved, quaternion-calibrated preview motion.
                bpy.context.scene.frame_set(int(frame),subframe=frame-int(frame))
                source_pose=source.pose.bones[role]
                dest=rig.pose.bones[bone_name]
                dest.rotation_mode='QUATERNION'
                dest.rotation_quaternion=source_pose.rotation_quaternion.copy()
                dest.keyframe_insert(data_path='rotation_quaternion',frame=frame,group=bone_name)
    rig['nvp_motion_approval_sha']=motion['approval_sha']
    rig['nvp_skin_approval_sha']=character['skin_approval_sha']
    rig['nvp_character_approval_sha']=character['approval_sha']
sc['nvp_character_approval_sha']=character['approval_sha']
'''


def inject_character_script(base:str,package:dict):
    anchor='args = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []'
    if base.count(anchor)!=1:raise RuntimeError('Unexpected Blender script insertion point')
    data=dict(package['character'])
    data['skin_approval_sha']=package['skin']['approval_sha']
    # Blender's original generated rig/skin script already binds `motion` and `take`.
    return base.replace(anchor,'CHARACTER_PAYLOAD='+repr(compact(data))+'\n'+CHARACTER_SCRIPT+'\n'+anchor)


CHARACTER_AUDIT_SCRIPT = r'''import bpy,sys,json,math
from pathlib import Path
argv=sys.argv[sys.argv.index('--')+1:]
opts=dict(zip(argv[::2],argv[1::2]))
payload=json.loads(Path(opts['--package']).read_text('utf8'))
sc=bpy.context.scene
checks=[]
def check(name,ok,detail):checks.append({'name':name,'passed':bool(ok),'detail':detail})
check('approval',sc.get('nvp_character_approval_sha')==payload['character']['approval_sha'],'scene pinned')
for item in payload['character']['bindings']:
    rid=item['instance_id']
    rig=bpy.data.objects.get('NVP_CHARACTER_RIG_'+rid)
    check('imported_rig:'+rid,rig is not None and rig.type=='ARMATURE',rid)
    if rig is None:continue
    actor=bpy.data.objects.get('NVP_'+rid)
    check('actor_parent:'+rid,rig.parent==actor,rid)
    check('rig_digest:'+rid,rig.get('nvp_character_sha')==item['sha256'],item['sha256'])
    check('rig_provenance:'+rid,rig.get('nvp_character_asset_id')==item['character_asset_id'],item['character_asset_id'])
    for role,bone_name in item['role_map'].items():
        check('mapped_bone:'+role,bone_name in rig.pose.bones,bone_name)
    meshes=[o for o in bpy.data.objects if o.get('nvp_character_actor')==rid and o.type=='MESH']
    check('skinned_mesh:'+rid,len(meshes)>=1,len(meshes))
    if not meshes:continue
    check('armature_modifier:'+rid,any(m.type=='ARMATURE' and m.object==rig for obj in meshes for m in obj.modifiers),'skin linkage')
    source=bpy.data.objects['NVP_RIG_'+rid]
    motion_actor=next(x for x in payload['motion']['plan']['actors'] if x['instance_id']==rid)
    motion_samples=[]
    for segment in motion_actor['segments']:
        clip=payload['motion']['clips'][segment['clip_id']]
        for sample in clip['frames']:
            if 'arm_left' in sample['joints']:
                motion_samples.append((segment['start_frame']+sample['frame']*payload['take']['fps']/clip['fps'],sample))
    if len(motion_samples)>=2:
        a=motion_samples[0][0];b=next((f for f,s in motion_samples[1:] if s['joints']['arm_left']['euler_deg']!=motion_samples[0][1]['joints']['arm_left']['euler_deg']),None)
        if b is not None:
            snapshots=[]
            for t in (a,b):
                sc.frame_set(int(t),subframe=t-int(t))
                q=rig.pose.bones[item['role_map']['arm_left']].rotation_quaternion
                source_q=source.pose.bones['arm_left'].rotation_quaternion
                check('retarget_rotation:'+rid+':'+str(t),abs(abs(q.dot(source_q))-1)<.001,tuple(q))
                deps=bpy.context.evaluated_depsgraph_get()
                obj=meshes[0].evaluated_get(deps);geo=obj.to_mesh()
                snapshots.append([tuple(obj.matrix_world@v.co) for v in geo.vertices])
                obj.to_mesh_clear()
            if snapshots[0] and len(snapshots[0])==len(snapshots[1]):
                moved=max(math.dist(a,b) for a,b in zip(snapshots[0],snapshots[1]))
                check('mesh_actually_deforms:'+rid,moved>.01,moved)
            else:check('evaluated_geometry:'+rid,False,'missing geometry')
check('preview_skin_hidden',all(bpy.data.objects['NVP_SKIN_'+r['instance_id']].hide_render for r in payload['character']['bindings']),'only imported character rendered')
report={'format':'nvp.character.audit.v1','blender':bpy.app.version_string,'passed':all(x['passed'] for x in checks),'checks':checks}
Path(opts['--audit']).write_text(json.dumps(report,sort_keys=True,indent=2),'utf8')
if not report['passed']:raise RuntimeError('Imported humanoid audit failed')
if opts.get('--skip-render')!='1':
    sc.frame_set(max(1,int(sc.frame_end//2)))
    sc.render.engine='BLENDER_WORKBENCH';sc.render.filepath=opts['--preview']
    sc.render.image_settings.file_format='PNG';sc.render.resolution_x=960;sc.render.resolution_y=540
    bpy.ops.render.render(write_still=True)
'''


def run_character_acceptance(service:CharacterAssets,pid,sid,directory,*,executable='blender',render_preview=True,timeout=240):
    root=Path(directory).resolve()
    service.export_bundle(pid,sid,root)
    pkg=service.export(pid,sid)
    audit=root/'audit_characters.py';blend=root/'characters.blend';report=root/'character_audit.json';preview=root/'character_preview.png'
    probe=blender_available(executable)
    if not probe['available']:
        return {'status':'blocked_no_blender','reason':probe['reason'],'bundle':str(root)}
    cmds=[
        [probe['path'],'-b','--factory-startup','-t','2','--python',str(root/'build_characters.py'),'--','--output',str(blend)],
        [probe['path'],'-b',str(blend),'-t','2','--python',str(audit),'--','--package',str(root/'character.json'),
         '--audit',str(report),'--preview',str(preview)]
    ]
    if not render_preview:cmds[1].extend(['--skip-render','1'])
    attempts=[]
    for i,cmd in enumerate(cmds,1):
        try:p=run_owned_subprocess(cmd,capture_output=True,text=True,cwd=root,timeout=timeout)
        except subprocess.TimeoutExpired:return {'status':'failed','reason':'Native Blender timed out','step':i}
        attempts.append({'step':i,'code':p.returncode,'stdout':p.stdout[-1800:],'stderr':p.stderr[-2400:]})
        if p.returncode:return {'status':'failed','reason':'Native Blender import or audit failed','attempts':attempts}
        expected=blend if i==1 else report
        if not expected.is_file():
            return {'status':'failed','reason':'Blender returned success without creating required output',
                    'step':i,'expected':str(expected),'attempts':attempts}
    if not blend.is_file() or not report.is_file() or (render_preview and not preview.is_file()):
        return {'status':'failed','reason':'Native files missing','attempts':attempts}
    checks=json.loads(report.read_text('utf8'))
    if not checks['passed']:return {'status':'failed','reason':'Geometry or retarget failed','audit':checks}
    return {'status':'passed_blender' if render_preview else 'passed_blender_audit_only',
            'blend':str(blend),'audit':str(report),'preview':str(preview) if render_preview else None,
            'checks':len(checks['checks']),'blender':probe['version']}
