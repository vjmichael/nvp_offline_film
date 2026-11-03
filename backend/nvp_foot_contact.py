"""PROD-06E2B1: authored foot contact and bend-pole intentions.

No IK is executed in this phase. The director-approved contact schedule pins
the imported, independently inspected anatomical identity, frame timeline,
pole directions and explicit foot/ground offset. The native staged-pose survey
is a separate measurement, not an authorization or an anatomy guess.
"""
from __future__ import annotations
import json
import math

from backend.nvp_leg_chains import LegChainIdentity
from backend.nvp_foot_ik import MAX_FRAMES, MAX_CONTACTS
from backend.nvp_production_scene import compact, digest

SIDES = ('left','right')


def _numeric(x, label, lower, upper):
    if type(x) not in (int,float) or not math.isfinite(x) or not lower<=x<=upper:
        raise ValueError(label+' must be finite and within declared bounds')
    return float(x)


def _vec(v, label, minimum=-1000, maximum=1000):
    if type(v) not in (list,tuple) or len(v)!=3:
        raise ValueError(label+' must contain three coordinates')
    return [_numeric(x,label,minimum,maximum) for x in v]


def validate_contacts(value, start_frame, end_frame):
    if type(value) is not dict or set(value)!=set(SIDES):
        raise ValueError('Both left and right contact plans must be explicit')
    out={}
    for side in SIDES:
        plan=value[side]
        if type(plan) is not dict or set(plan)!={
            'contact_windows','knee_pole_direction_world','ankle_to_surface_m',
            'surface_z_m','max_ankle_correction_m'}:
            raise ValueError(side+' must specify windows, pole, sole offset, surface and correction')
        direction=_vec(plan['knee_pole_direction_world'],side+' pole',-1,1)
        magnitude=math.sqrt(sum(v*v for v in direction))
        if not .01<=magnitude<=math.sqrt(3):
            raise ValueError(side+' knee pole direction is degenerate')
        direction=[round(v/magnitude,12) for v in direction]
        windows=plan['contact_windows']
        if type(windows) is not list or len(windows)>MAX_CONTACTS:
            raise ValueError('Too many contact windows')
        prior=start_frame-1;checked=[]
        for pair in windows:
            if type(pair) not in (list,tuple) or len(pair)!=2 or any(type(f) is not int for f in pair):
                raise ValueError('Contact window must contain integer frame bounds')
            a,b=pair
            if a<start_frame or b>end_frame or a>b or a<=prior:
                raise ValueError('Contact windows must be ordered, distinct, and inside take')
            checked.append([a,b]);prior=b
        out[side]={
            'contact_windows':checked,
            'knee_pole_direction_world':direction,
            'ankle_to_surface_m':_numeric(plan['ankle_to_surface_m'],
                                          side+' signed ankle/sole offset',-.5,.5),
            'surface_z_m':_numeric(plan['surface_z_m'],side+' surface',-100,100),
            'max_ankle_correction_m':_numeric(plan['max_ankle_correction_m'],
                                              side+' correction',0,.25)}
    # Stance flags are meaningful only if at least one leg has a declared stance.
    if not any(out[s]['contact_windows'] for s in SIDES):
        raise ValueError('At least one explicit contact window is required')
    return out


class FootContactPlan:
    """Project-scoped, creator-controlled contact intent; IK remains forbidden."""
    def __init__(self,studio):
        self.studio=studio
        self.legs=LegChainIdentity(studio)
        with studio._connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS prod_foot_contact_plans (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL,
                revision INTEGER NOT NULL, status TEXT NOT NULL,
                upstream_sha TEXT NOT NULL, plan_json TEXT NOT NULL,
                approval_sha TEXT, PRIMARY KEY(project_id,scene_id))''')
            db.execute('''CREATE TABLE IF NOT EXISTS prod_foot_contact_history (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, revision INTEGER NOT NULL,
                action TEXT NOT NULL, snapshot_json TEXT NOT NULL,
                PRIMARY KEY(project_id,scene_id,revision))''')

    def _context(self,pid,sid):
        pkg=self.legs.export(pid,sid)
        shots=pkg['take']['shots']
        first=min(x['start_frame'] for x in shots)
        last=max(x['stop_frame']-1 for x in shots)
        if type(first) is not int or type(last) is not int or first<1 or last<first or last-first+1>MAX_FRAMES:
            raise ValueError('Contact planning requires a bounded integer-frame take')
        return pkg,digest([pkg['leg_identity'],pkg['take']]),first,last

    def _record(self,db,pid,sid):
        row=db.execute('SELECT * FROM prod_foot_contact_plans WHERE project_id=? AND scene_id=?',(pid,sid)).fetchone()
        if row is None:raise KeyError('Foot contact plan not found in this project/scene')
        return dict(row)

    def create(self,pid,sid):
        pkg,upstream,first,last=self._context(pid,sid)
        actors=[{'instance_id':a['instance_id'],'sides':None}
                for a in pkg['leg_identity']['actors']]
        plan={'format':'nvp.foot.contact_intent.v1','start_frame':first,
              'end_frame':last,'actors':actors,'author':'director'}
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM prod_foot_contact_plans WHERE project_id=? AND scene_id=?',(pid,sid)).fetchone():
                raise RuntimeError('Foot contact plan already exists')
            db.execute('INSERT INTO prod_foot_contact_plans VALUES (?,?,?,?,?,?,?)',
                       (pid,sid,0,'draft',upstream,compact(plan),None))
            db.execute('INSERT INTO prod_foot_contact_history VALUES (?,?,?,?,?)',
                       (pid,sid,0,'create',compact(plan)))
        return self.read(pid,sid)

    def read(self,pid,sid):
        _,upstream,_,_=self._context(pid,sid)
        with self.studio._connection() as db:row=self._record(db,pid,sid)
        return {'project_id':pid,'scene_id':sid,'status':row['status'],
                'revision':row['revision'],'stale':row['upstream_sha']!=upstream,
                'approval_sha':row['approval_sha'],
                'plan':json.loads(row['plan_json'])}

    def configure(self,pid,sid,actor_id,sides,expected_revision):
        _,upstream,first,last=self._context(pid,sid)
        checked=validate_contacts(sides,first,last)
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=self._record(db,pid,sid)
            if row['status']!='draft' or row['upstream_sha']!=upstream or type(expected_revision) is not int or row['revision']!=expected_revision:
                raise RuntimeError('Foot contact plan approved, stale or concurrently modified')
            plan=json.loads(row['plan_json'])
            actor=next((x for x in plan['actors'] if x['instance_id']==actor_id),None)
            if actor is None:raise KeyError('Actor not found in approved anatomical plan')
            actor['sides']=checked
            revision=row['revision']+1
            db.execute('UPDATE prod_foot_contact_plans SET revision=?,plan_json=? WHERE project_id=? AND scene_id=?',
                       (revision,compact(plan),pid,sid))
            db.execute('INSERT INTO prod_foot_contact_history VALUES (?,?,?,?,?)',
                       (pid,sid,revision,'configure',compact(plan)))
        return self.read(pid,sid)

    def approve(self,pid,sid,expected_revision):
        pkg,upstream,first,last=self._context(pid,sid)
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=self._record(db,pid,sid)
            if row['status']!='draft' or row['upstream_sha']!=upstream or type(expected_revision) is not int or row['revision']!=expected_revision:
                raise RuntimeError('Foot contact plan cannot be approved from stale draft')
            plan=json.loads(row['plan_json'])
            if not plan['actors'] or any(a['sides'] is None for a in plan['actors']):
                raise RuntimeError('Every actor requires authored contact and pole directions')
            for actor in plan['actors']:
                if validate_contacts(actor['sides'],first,last)!=actor['sides']:
                    raise RuntimeError('Foot contact plan has been altered after validation')
            approved=digest([upstream,plan])
            revision=row['revision']+1
            db.execute('UPDATE prod_foot_contact_plans SET revision=?,status=?,approval_sha=? WHERE project_id=? AND scene_id=?',
                       (revision,'approved',approved,pid,sid))
            db.execute('INSERT INTO prod_foot_contact_history VALUES (?,?,?,?,?)',
                       (pid,sid,revision,'approve',compact({'approval_sha':approved})))
        return self.read(pid,sid)

    def export(self,pid,sid):
        pkg,upstream,first,last=self._context(pid,sid)
        with self.studio._connection() as db:row=self._record(db,pid,sid)
        plan=json.loads(row['plan_json'])
        if row['status']!='approved' or row['upstream_sha']!=upstream or row['approval_sha']!=digest([upstream,plan]):
            raise RuntimeError('Only approved current contact intent can be exported')
        return {**pkg,'foot_contacts':{
            'format':'nvp.foot.contacts.approved.v1',
            'upstream_sha':upstream,'approval_sha':row['approval_sha'],
            'plan':plan,'ik_authorized':False,
            'limitations':'Director-approved stance windows and bend-pole intent; no IK or native rig deformation'}}
