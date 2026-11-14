"""NVP-PROD-06E2A: explicit anatomical leg identity, before any IK.

Only developer-invoked Blender inspection is implemented here. No animation,
contact, source rig rest pose or camera key is ever modified by this module.
The input mapping is creator-authored and must match actual imported bone
hierarchy, world-space rest geometry and the approved PROD-06D actor binding.
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
from backend.nvp_w1g_owned_subprocess import run_owned_subprocess
from pathlib import Path

from backend.nvp_blender_acceptance import blender_available
from backend.nvp_character_assets import CharacterAssets
from backend.nvp_production_scene import compact, digest
from backend.nvp_retarget import RetargetCalibration

LEGS = ('left', 'right')
PARTS = ('hip', 'knee', 'ankle', 'toe')
MAX_BONES = 128
MAX_ACTORS = 16
ANATOMY_VERSION = 'nvp.legchain.anatomy.v1'


def _number(value, label, lo=-1e5, hi=1e5):
    if type(value) not in (float, int) or not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(label + ' must be bounded and finite')
    return float(value)


def _vec(value, label):
    if type(value) not in (list, tuple) or len(value) != 3:
        raise ValueError(label + ' must be a 3-vector')
    return tuple(_number(v, label) for v in value)


def _matrix(value, label):
    if type(value) not in (list, tuple) or len(value) != 16:
        raise ValueError(label + ' must be a flattened 4x4 matrix')
    v = tuple(_number(x, label) for x in value)
    a,b,c,_,d,e,f,_,g,h,i,_,_,_,_,_ = v
    determinant = a*(e*i-f*h)-b*(d*i-f*g)+c*(d*h-e*g)
    if abs(determinant) < 1e-12:
        raise ValueError(label + ' has singular rest basis')
    return v


def _dist(a, b):
    return math.sqrt(sum((x-y)**2 for x, y in zip(a,b)))


def validate_leg_mapping(mapping, role_map, joint_names):
    """Require a complete one-to-one authored mapping; do not guess anatomy."""
    if type(mapping) is not dict or set(mapping) != set(LEGS):
        raise ValueError('Left and right leg chains must both be explicit')
    if type(role_map) is not dict or not isinstance(joint_names, (list, tuple)):
        raise ValueError('Approved actor role map and asset joints are required')
    available = set(joint_names)
    if len(available) != len(joint_names):
        raise ValueError('Asset joint names are not unique')
    used=[]
    out={}
    for side in LEGS:
        chain = mapping[side]
        if type(chain) is not dict or set(chain) != set(PARTS):
            raise ValueError(side + ' leg requires hip, knee, ankle and toe joints')
        names={}
        for role in PARTS:
            name=chain[role]
            if type(name) is not str or not 1<=len(name)<=100 or name not in available:
                raise ValueError(side + ' ' + role + ' bone absent from registered asset')
            used.append(name)
            names[role]=name
        expected=role_map.get('leg_left' if side=='left' else 'leg_right')
        if names['hip'] != expected:
            raise ValueError(side + ' hip must match the approved PROD-06D leg role')
        out[side]=names
    if len(set(used)) != 8:
        raise ValueError('The two leg chains must have eight distinct joint identities')
    return out


def analyze_anatomy_snapshot(snapshot, mapping, *, asset_sha256, actor_id):
    """Independent host-side review of a Blender *observation*, not its verdict.

    Joints are checked for direct parentage and world-space rest points. The
    mapping and asset identity must already have come from an approved NVP
    binding. A report is evidence for identity, not an IK / motion approval.
    """
    if type(snapshot) is not dict or snapshot.get('format') != 'nvp.legchain.observation.v1':
        raise ValueError('Unsupported native anatomy observation')
    if snapshot.get('asset_sha256') != asset_sha256 or snapshot.get('armature_count') != 1:
        raise ValueError('Native armature/source identity mismatch')
    if snapshot.get('skinned_mesh_count',0) < 1 or type(snapshot.get('skinned_mesh_count')) is not int:
        raise ValueError('Native import lacks an armature-bound skinned mesh')
    bones = snapshot.get('bones')
    if not isinstance(bones, list) or not 8<=len(bones)<=MAX_BONES:
        raise ValueError('Imported native bone count is unsupported')
    by_name={}
    for entry in bones:
        if type(entry) is not dict or type(entry.get('name')) is not str or entry['name'] in by_name:
            raise ValueError('Duplicate/invalid native bone identity')
        name=entry['name']
        if not 1<=len(name)<=100 or type(entry.get('parent')) not in (str, type(None)):
            raise ValueError('Invalid native bone name/parent')
        head=_vec(entry.get('head_world_m'),'rest head')
        tail=_vec(entry.get('tail_world_m'),'rest tail')
        _matrix(entry.get('rest_matrix_world'),'rest matrix world')
        _matrix(entry.get('rest_matrix_local'),'rest matrix local')
        by_name[name]={'parent':entry['parent'],'head':head,'tail':tail}
    for item in by_name.values():
        if item['parent'] is not None and item['parent'] not in by_name:
            raise ValueError('Native hierarchy has unresolved parent')
    if type(mapping) is not dict or set(mapping)!=set(LEGS):
        raise ValueError('Full two-leg mapping is required')
    seen=[];lengths={};points={}
    for side in LEGS:
        m=mapping[side]
        if type(m) is not dict or set(m)!=set(PARTS):
            raise ValueError('Invalid anatomical chain mapping')
        if any(name not in by_name for name in m.values()):
            raise ValueError('Approved mapped joint absent from Blender imported rig')
        for part in PARTS:
            if type(m[part]) is not str:
                raise ValueError('Invalid joint identity')
            seen.append(m[part])
        for child,parent in (('knee','hip'),('ankle','knee'),('toe','ankle')):
            if by_name[m[child]]['parent'] != m[parent]:
                raise ValueError(side + ' bone hierarchy is not an immediate anatomical chain: ' + child)
        heads={part:by_name[m[part]]['head'] for part in PARTS}
        upper=_dist(heads['hip'],heads['knee'])
        lower=_dist(heads['knee'],heads['ankle'])
        foot=_dist(heads['ankle'],heads['toe'])
        if not .02 <= upper <= 3.0 or not .02 <= lower <= 3.0 or not .005 <= foot <= 1.5:
            raise ValueError(side + ' anatomical rest segment lengths are degenerate or implausible')
        lengths[side]={'upper_m':round(upper,9),'lower_m':round(lower,9),
                       'ankle_to_toe_m':round(foot,9)}
        points[side]={part:list(heads[part]) for part in PARTS}
    if len(set(seen))!=8:
        raise ValueError('Overlapping left/right anatomical identity')
    if _dist(tuple(points['left']['hip']),tuple(points['right']['hip'])) < .02:
        raise ValueError('Left/right hips coincide in rest frame')
    if _dist(tuple(points['left']['ankle']),tuple(points['right']['ankle'])) < .02:
        raise ValueError('Left/right ankles coincide in rest frame')
    lateral_hip=tuple(b-a for a,b in zip(points['left']['hip'],points['right']['hip']))
    lateral_ankle=tuple(b-a for a,b in zip(points['left']['ankle'],points['right']['ankle']))
    side_consistency=sum(a*b for a,b in zip(lateral_hip,lateral_ankle))
    return {
        'format':ANATOMY_VERSION,'actor_id':actor_id,'asset_sha256':asset_sha256,
        'mapping_sha':digest(mapping),'native_snapshot_sha':digest(snapshot),
        'blender_version':snapshot.get('blender_version','unreported'),
        'chains':mapping,'rest_lengths_m':lengths,'rest_heads_world_m':points,
        'warnings':(['Crossed left/right foot positions in rest stance; director review required']
                    if side_consistency<=0 else []),
        'ik_authorized':False,
    }


# The fixed probe only reads a known registered local GLB. It does not include
# model-produced code and does not animate or alter the imported asset.
LEGCHAIN_PROBE_SCRIPT = r'''import bpy,sys,json,hashlib
from pathlib import Path
argv=sys.argv[sys.argv.index('--')+1:]
opts=dict(zip(argv[::2],argv[1::2]))
source=Path(opts['--asset']).resolve()
expected=opts['--sha']
if source.suffix.lower()!='.glb' or source.name!=expected+'.glb':
    raise RuntimeError('Unexpected imported anatomical asset location')
data=source.read_bytes()
if hashlib.sha256(data).hexdigest()!=expected:
    raise RuntimeError('Registered character SHA mismatch before Blender import')
bpy.ops.import_scene.gltf(filepath=str(source))
rigs=[obj for obj in bpy.data.objects if obj.type=='ARMATURE']
meshes=[obj for obj in bpy.data.objects if obj.type=='MESH' and any(
    modifier.type=='ARMATURE' and modifier.object in rigs for modifier in obj.modifiers)]
if len(rigs)!=1 or not meshes:
    raise RuntimeError('Expected a single genuine armature and skinned geometry')
rig=rigs[0]
rig.update_from_editmode()
bpy.context.view_layer.update()
def flat(matrix):
    return [float(v) for row in matrix for v in row]
bones=[]
for bone in rig.data.bones:
    matrix=rig.matrix_world @ bone.matrix_local
    head=rig.matrix_world @ bone.head_local
    tail=rig.matrix_world @ bone.tail_local
    bones.append({'name':bone.name,'parent':bone.parent.name if bone.parent else None,
                  'head_world_m':[float(v) for v in head],
                  'tail_world_m':[float(v) for v in tail],
                  'rest_matrix_local':flat(bone.matrix_local),
                  'rest_matrix_world':flat(matrix)})
report={'format':'nvp.legchain.observation.v1','asset_sha256':expected,
        'armature_count':len(rigs),'skinned_mesh_count':len(meshes),
        'blender_version':bpy.app.version_string,'bones':bones}
Path(opts['--output']).write_text(json.dumps(report,indent=2,sort_keys=True),'utf8')
'''


class LegChainIdentity:
    """Revision-controlled authored maps with native evidence and approval."""
    def __init__(self, studio):
        self.studio=studio
        self.retarget=RetargetCalibration(studio)
        self.characters=CharacterAssets(studio)
        with studio._connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS prod_legchain_sessions(
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, revision INTEGER NOT NULL,
                status TEXT NOT NULL, dependency_sha TEXT NOT NULL,
                plan_json TEXT NOT NULL, evidence_json TEXT NOT NULL,
                approval_sha TEXT,
                PRIMARY KEY(project_id,scene_id))''')
            db.execute('''CREATE TABLE IF NOT EXISTS prod_legchain_history(
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, revision INTEGER NOT NULL,
                action TEXT NOT NULL, snapshot_json TEXT NOT NULL,
                PRIMARY KEY(project_id,scene_id,revision))''')

    def _context(self,pid,sid):
        pkg=self.retarget.export(pid,sid)
        return pkg,digest([pkg['character'],pkg['retarget']])

    def _record(self,db,pid,sid):
        row=db.execute('SELECT * FROM prod_legchain_sessions WHERE project_id=? AND scene_id=?',
                       (pid,sid)).fetchone()
        if row is None:raise KeyError('Leg-chain identity session not found')
        return dict(row)

    def create(self,pid,sid):
        pkg,source=self._context(pid,sid)
        bindings=pkg['character']['bindings']
        if not 1<=len(bindings)<=MAX_ACTORS:raise ValueError('No approved target actors')
        plan={'format':'nvp.legchain.plan.v1','actors':[
            {'instance_id':b['instance_id'],'asset_sha256':b['sha256'],'mapping':None}
            for b in bindings]}
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM prod_legchain_sessions WHERE project_id=? AND scene_id=?',(pid,sid)).fetchone():
                raise RuntimeError('Leg-chain identity already exists')
            db.execute('INSERT INTO prod_legchain_sessions VALUES (?,?,?,?,?,?,?,?)',
                       (pid,sid,0,'draft',source,compact(plan),compact({}),None))
            db.execute('INSERT INTO prod_legchain_history VALUES (?,?,?,?,?)',
                       (pid,sid,0,'create',compact(plan)))
        return self.read(pid,sid)

    def read(self,pid,sid):
        _,sha=self._context(pid,sid)
        with self.studio._connection() as db:row=self._record(db,pid,sid)
        return {'project_id':pid,'scene_id':sid,'revision':row['revision'],
                'status':row['status'],'stale':row['dependency_sha']!=sha,
                'actors':json.loads(row['plan_json'])['actors'],
                'inspected_actors':sorted(json.loads(row['evidence_json']).keys()),
                'approval_sha':row['approval_sha']}

    def configure(self,pid,sid,actor_id,mapping,expected_revision):
        pkg,sha=self._context(pid,sid)
        binding=next((b for b in pkg['character']['bindings'] if b['instance_id']==actor_id),None)
        if binding is None:raise KeyError('Actor is absent from approved retarget')
        asset=next((a for a in self.characters.list(pid) if a['asset_id']==binding['character_asset_id']),None)
        if asset is None or asset['sha256']!=binding['sha256']:
            raise RuntimeError('Character registry no longer matches its approved asset')
        checked=validate_leg_mapping(mapping,binding['role_map'],asset['joint_names'])
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=self._record(db,pid,sid)
            if row['status']!='draft' or row['dependency_sha']!=sha or type(expected_revision) is not int or row['revision']!=expected_revision:
                raise RuntimeError('Leg identity plan is stale, approved or conflicted')
            plan=json.loads(row['plan_json'])
            target=next((a for a in plan['actors'] if a['instance_id']==actor_id),None)
            if target is None:raise KeyError('Actor missing from leg identity plan')
            target['mapping']=checked
            evidence=json.loads(row['evidence_json']);evidence.pop(actor_id,None)
            revision=row['revision']+1
            db.execute('UPDATE prod_legchain_sessions SET revision=?,plan_json=?,evidence_json=? WHERE project_id=? AND scene_id=?',
                       (revision,compact(plan),compact(evidence),pid,sid))
            db.execute('INSERT INTO prod_legchain_history VALUES (?,?,?,?,?)',
                       (pid,sid,revision,'configure',compact(plan)))
        return self.read(pid,sid)

    def inspect_native(self,pid,sid,directory,*,executable='blender',timeout=240):
        """Import exact approved source asset(s) in Blender, then analyze outside it.

        This is a developer-only execution path. Production worker dispatch
        requires Lu resource brokerage and OS-enforced containment later.
        """
        pkg,sha=self._context(pid,sid)
        with self.studio._connection() as db:row=self._record(db,pid,sid)
        if row['status']!='draft' or row['dependency_sha']!=sha:
            raise RuntimeError('Only the current draft can be inspected')
        plan=json.loads(row['plan_json'])
        if not plan['actors'] or any(a['mapping'] is None for a in plan['actors']):
            raise ValueError('Every actor requires an explicit authored leg map')
        probe=blender_available(executable)
        if not probe['available']:
            return {'status':'blocked_no_blender','reason':probe['reason']}
        out=Path(directory).resolve();out.mkdir(parents=True,exist_ok=True)
        script=out/'observe_legchain.py';script.write_text(LEGCHAIN_PROBE_SCRIPT,'utf8')
        evidence={}
        for index,entry in enumerate(plan['actors']):
            rid=entry['instance_id'];sha_asset=entry['asset_sha256']
            source=self.characters.root/(sha_asset+'.glb')
            if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=sha_asset:
                raise RuntimeError('Approved rigged asset missing or corrupted')
            report=out/('legchain_observation_'+str(index)+'.json')
            report.unlink(missing_ok=True)
            command=[probe['path'],'-b','--factory-startup','-t','2',
                     '--python-exit-code','30','--python',str(script),'--',
                     '--asset',str(source),'--sha',sha_asset,'--output',str(report)]
            try:result=run_owned_subprocess(command,cwd=out,capture_output=True,text=True,timeout=timeout)
            except subprocess.TimeoutExpired:
                return {'status':'failed','reason':'Blender anatomical inspection timed out','actor':rid}
            if result.returncode or not report.is_file():
                return {'status':'failed','reason':'Blender native anatomy inspection failed','actor':rid,
                        'returncode':result.returncode,'stdout':result.stdout[-1500:],
                        'stderr':result.stderr[-2000:]}
            try:
                snapshot=json.loads(report.read_text('utf8'))
                evidence[rid]=analyze_anatomy_snapshot(snapshot,entry['mapping'],
                    asset_sha256=sha_asset,actor_id=rid)
            except (ValueError,TypeError,KeyError,OverflowError) as error:
                return {'status':'failed','reason':'Independent anatomy validation refused: '+str(error),
                        'actor':rid}
        # Recheck after external process: no stale/approved races may commit.
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            current=self._record(db,pid,sid)
            if (current['revision']!=row['revision'] or current['status']!='draft' or
                current['dependency_sha']!=sha or current['plan_json']!=row['plan_json']):
                raise RuntimeError('Leg mapping changed while Blender was inspecting')
            nowpkg,nowsha=self._context(pid,sid)
            if nowsha != sha:raise RuntimeError('Approved retarget changed during native inspection')
            revision=row['revision']+1
            db.execute('UPDATE prod_legchain_sessions SET revision=?,evidence_json=? WHERE project_id=? AND scene_id=?',
                       (revision,compact(evidence),pid,sid))
            db.execute('INSERT INTO prod_legchain_history VALUES (?,?,?,?,?)',
                       (pid,sid,revision,'native_inspect',
                        compact({'plan_sha':digest(plan),'evidence_sha':digest(evidence)})))
        return {'status':'native_anatomy_inspected','revision':revision,'actors':evidence,
                'inspection_path':str(out),'ik_applied':False}

    def approve(self,pid,sid,expected_revision):
        pkg,sha=self._context(pid,sid)
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=self._record(db,pid,sid)
            if row['status']!='draft' or row['dependency_sha']!=sha or type(expected_revision) is not int or row['revision']!=expected_revision:
                raise RuntimeError('Only current inspected leg map can be approved')
            plan=json.loads(row['plan_json'])
            evidence=json.loads(row['evidence_json'])
            if set(evidence)!={a['instance_id'] for a in plan['actors']}:
                raise RuntimeError('Missing independent Blender anatomy evidence')
            for actor in plan['actors']:
                proof=evidence[actor['instance_id']]
                if (proof['asset_sha256']!=actor['asset_sha256'] or
                    proof['mapping_sha']!=digest(actor['mapping']) or
                    proof.get('ik_authorized') is not False):
                    raise RuntimeError('Anatomy inspection evidence no longer matches the mapping')
            approval=digest([sha,plan,evidence])
            revision=row['revision']+1
            db.execute('UPDATE prod_legchain_sessions SET revision=?,status=?,approval_sha=? WHERE project_id=? AND scene_id=?',
                       (revision,'approved',approval,pid,sid))
            db.execute('INSERT INTO prod_legchain_history VALUES (?,?,?,?,?)',
                       (pid,sid,revision,'approve',compact({'approval_sha':approval})))
        return self.read(pid,sid)

    def export(self,pid,sid):
        pkg,sha=self._context(pid,sid)
        with self.studio._connection() as db:row=self._record(db,pid,sid)
        plan=json.loads(row['plan_json']);evidence=json.loads(row['evidence_json'])
        if row['status']!='approved' or row['dependency_sha']!=sha or row['approval_sha']!=digest([sha,plan,evidence]):
            raise RuntimeError('Only approved current inspected leg identity can be exported')
        return {**pkg,'leg_identity':{
            'format':'nvp.legchain.approved_identity.v1','retarget_dependency_sha':sha,
            'approval_sha':row['approval_sha'],'actors':plan['actors'],
            'native_anatomy_evidence':evidence,
            'ik_authorized':False,
            'limitations':'Real Blender bone hierarchy/rest geometry inspected; no IK or motion approved'}}
