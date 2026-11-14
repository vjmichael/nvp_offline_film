"""NVP-PROD-06E2B: director-scoped two-leg ankle-lock authoring.

Prerequisite: an independently inspected, approved PROD-06E2A anatomical
identity. This service stores approvals; Blender applies and verifies the
articulated motion separately. Ankle markers are NOT verified shoe soles.
"""
from __future__ import annotations

import json
import math

from backend.nvp_leg_chains import LegChainIdentity
from backend.nvp_production_scene import compact, digest

SIDES = ('left','right')
MAX_CONTACTS = 32
MAX_FRAMES = 2400


def number(value, name, minimum, maximum):
    if type(value) not in (int,float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(name+' must be a finite number within declared bounds')
    return float(value)


def vector(value,name,limit=2.0):
    if type(value) not in (list,tuple) or len(value)!=3:
        raise ValueError(name+' must contain exactly three coordinates')
    return [number(x,name,-limit,limit) for x in value]


def check_side(value, *, max_frame):
    if type(value) is not dict or set(value)!={'contact_windows','pole_offset_actor_m','anchor_pull_to_hip_m'}:
        raise ValueError('Contact configuration requires windows, pole offset and explicit anchor pull')
    windows=value['contact_windows']
    if type(windows) is not list or not 1<=len(windows)<=MAX_CONTACTS:
        raise ValueError('At least one bounded, explicit stance window is required')
    validated=[]
    stop=0
    for pair in windows:
        if (type(pair) not in (list,tuple) or len(pair)!=2 or
            any(type(x) is not int for x in pair)):
            raise ValueError('Contact windows need integer inclusive frame indices')
        a,b=pair
        if a<=stop or a<1 or b<a or b>max_frame:
            raise ValueError('Contact windows must be ordered, disjoint and within take')
        validated.append([a,b]);stop=b
    pole=vector(value['pole_offset_actor_m'],'actor-relative knee-pole offset',2.0)
    if math.sqrt(sum(x*x for x in pole)) < .02:
        raise ValueError('A meaningful explicit knee-pole displacement is required')
    pull=number(value['anchor_pull_to_hip_m'],'ankle target pull',0,.06)
    return {'contact_windows':validated,'pole_offset_actor_m':pole,
            'anchor_pull_to_hip_m':pull}


def validate_actor(value,max_frame):
    if type(value) is not dict or set(value)!={'left','right','max_ankle_correction_m','max_ankle_slide_m'}:
        raise ValueError('Both legs and explicit correction/sliding ceilings are required')
    return {**{side:check_side(value[side],max_frame=max_frame) for side in SIDES},
            'max_ankle_correction_m':number(value['max_ankle_correction_m'],
                                            'maximum ankle correction',.0001,.25),
            'max_ankle_slide_m':number(value['max_ankle_slide_m'],
                                       'maximum sliding',.00001,.05)}


class FootLockPlan:
    """Scene-scoped revisioned contact and pole intent; no implicit execution."""
    def __init__(self,studio):
        self.studio=studio
        self.identities=LegChainIdentity(studio)
        with studio._connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS prod_foot_lock_sessions (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL,
                revision INTEGER NOT NULL, status TEXT NOT NULL,
                identity_sha TEXT NOT NULL, plan_json TEXT NOT NULL,
                approval_sha TEXT,
                PRIMARY KEY(project_id,scene_id))''')
            db.execute('''CREATE TABLE IF NOT EXISTS prod_foot_lock_history (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, revision INTEGER NOT NULL,
                action TEXT NOT NULL, snapshot_json TEXT NOT NULL,
                PRIMARY KEY(project_id,scene_id,revision))''')

    def _source(self,pid,sid):
        pkg=self.identities.export(pid,sid)
        identity=pkg['leg_identity']
        if identity['ik_authorized'] is not False:
            raise RuntimeError('Upstream anatomy improperly claims foot IK authority')
        sha=digest([identity['approval_sha'],identity['retarget_dependency_sha'],
                    pkg['retarget']['approval_sha'],pkg['character']['approval_sha'],
                    pkg['take']])
        return pkg,sha

    def _row(self,db,pid,sid):
        row=db.execute('SELECT * FROM prod_foot_lock_sessions WHERE project_id=? AND scene_id=?',
                       (pid,sid)).fetchone()
        if row is None:raise KeyError('Foot lock authoring has not been initialized')
        return dict(row)

    def create(self,pid,sid):
        pkg,sha=self._source(pid,sid)
        plan={'format':'nvp.footlock.authored.v1',
              'actors':[{'instance_id':a['instance_id'],'config':None}
                        for a in pkg['leg_identity']['actors']]}
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM prod_foot_lock_sessions WHERE project_id=? AND scene_id=?',(pid,sid)).fetchone():
                raise RuntimeError('Foot lock plan already exists')
            db.execute('INSERT INTO prod_foot_lock_sessions VALUES(?,?,?,?,?,?,?)',
                       (pid,sid,0,'draft',sha,compact(plan),None))
            db.execute('INSERT INTO prod_foot_lock_history VALUES(?,?,?,?,?)',
                       (pid,sid,0,'create',compact(plan)))
        return self.read(pid,sid)

    def read(self,pid,sid):
        pkg,sha=self._source(pid,sid)
        with self.studio._connection() as db:r=self._row(db,pid,sid)
        return {'project_id':pid,'scene_id':sid,'revision':r['revision'],
                'status':r['status'],'stale':sha!=r['identity_sha'],
                'actors':json.loads(r['plan_json'])['actors'],
                'approval_sha':r['approval_sha']}

    def configure(self,pid,sid,actor_id,config,expected_revision):
        pkg,sha=self._source(pid,sid)
        max_frame=max(int(shot['stop_frame'])-1 for shot in pkg['take']['shots'])
        if max_frame>MAX_FRAMES:raise ValueError('Approved shot range exceeds the bounded animation frame budget')
        checked=validate_actor(config,max_frame)
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            r=self._row(db,pid,sid)
            if (r['identity_sha']!=sha or r['status']!='draft' or
                type(expected_revision) is not int or expected_revision!=r['revision']):
                raise RuntimeError('Foot lock edit is stale, conflicting or already approved')
            plan=json.loads(r['plan_json'])
            actor=next((a for a in plan['actors'] if a['instance_id']==actor_id),None)
            if actor is None:raise KeyError('Actor not approved for this identity scene')
            actor['config']=checked
            revision=r['revision']+1
            db.execute('UPDATE prod_foot_lock_sessions SET revision=?,plan_json=? WHERE project_id=? AND scene_id=?',
                       (revision,compact(plan),pid,sid))
            db.execute('INSERT INTO prod_foot_lock_history VALUES(?,?,?,?,?)',
                       (pid,sid,revision,'configure',compact(plan)))
        return self.read(pid,sid)

    def approve(self,pid,sid,expected_revision):
        pkg,sha=self._source(pid,sid)
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            r=self._row(db,pid,sid)
            if (r['identity_sha']!=sha or r['status']!='draft' or
                type(expected_revision) is not int or expected_revision!=r['revision']):
                raise RuntimeError('Only a current reviewed foot lock plan may be approved')
            plan=json.loads(r['plan_json'])
            identity=pkg['leg_identity']
            if ({a['instance_id'] for a in plan['actors']} !=
                {a['instance_id'] for a in identity['actors']} or
                any(a['config'] is None for a in plan['actors'])):
                raise RuntimeError('Every approved actor requires a complete authored two-leg plan')
            approved=digest([sha,plan])
            revision=r['revision']+1
            db.execute('UPDATE prod_foot_lock_sessions SET revision=?,status=?,approval_sha=? WHERE project_id=? AND scene_id=?',
                       (revision,'approved',approved,pid,sid))
            db.execute('INSERT INTO prod_foot_lock_history VALUES(?,?,?,?,?)',
                       (pid,sid,revision,'approve',compact({'approval_sha':approved})))
        return self.read(pid,sid)

    def export(self,pid,sid):
        pkg,sha=self._source(pid,sid)
        with self.studio._connection() as db:r=self._row(db,pid,sid)
        plan=json.loads(r['plan_json'])
        if (r['identity_sha']!=sha or r['status']!='approved' or
            r['approval_sha']!=digest([sha,plan])):
            raise RuntimeError('Foot lock approval or upstream identity is missing, stale or corrupted')
        return {**pkg,'foot_lock':{
            'format':'nvp.footlock.approved.v1','identity_sha':sha,
            'leg_identity_approval_sha':pkg['leg_identity']['approval_sha'],
            'approval_sha':r['approval_sha'],'actors':plan['actors'],
            'limitations':'Ankle-lock previsualization; no semantic sole, collision dynamics, or gait quality guarantee'}}

    def history(self,pid,sid):
        with self.studio._connection() as db:
            return [dict(x) for x in db.execute('SELECT revision,action,snapshot_json FROM prod_foot_lock_history WHERE project_id=? AND scene_id=? ORDER BY revision',(pid,sid))]
