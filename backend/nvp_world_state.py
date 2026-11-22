"""NVP-PROD-02: durable, typed, non-destructive world editing above approved staging.

Human changes are locked by default. AI can only propose. Every accepted edit
has a revision, provenance and an undoable durable journal entry. The approved
PROD-01 base layout is never overwritten. All geometry changes are revalidated.
"""
from __future__ import annotations

import copy
import json
import math
import sqlite3
import uuid
from datetime import datetime, timezone

from backend.nvp_studio import Studio
from backend.nvp_production_scene import ProductionScene, blender_script, digest, verify_layout, compact

FIELDS = {"pose.x": "metre", "pose.y": "metre", "pose.rotation": "degree",
          "visible": "boolean"}


def stamp():
    return datetime.now(timezone.utc).isoformat()


def check_value(field, value):
    if field not in FIELDS:
        raise ValueError("Unknown editable world attribute")
    if field == "visible":
        if type(value) is not bool:
            raise ValueError("Visibility must be a boolean")
    elif field == "pose.rotation":
        if type(value) is not int or value not in (0, 90, 180, 270):
            raise ValueError("Only 0, 90, 180, or 270 degree rotations are supported")
    elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not -16 <= value <= 32:
        raise ValueError("Position must be finite metres within stage limits")
    return value


class WorldState:
    def __init__(self, studio: Studio):
        self.studio = studio
        self.production = ProductionScene(studio)
        with studio._connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS prod_world_sessions (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, base_sha TEXT NOT NULL, base_plan_revision INTEGER NOT NULL,
                revision INTEGER NOT NULL, fields_json TEXT NOT NULL, updated_at TEXT NOT NULL,
                PRIMARY KEY(project_id,scene_id))""")
            db.execute("""CREATE TABLE IF NOT EXISTS prod_world_events (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, revision INTEGER NOT NULL, action TEXT NOT NULL,
                before_json TEXT NOT NULL, after_json TEXT NOT NULL, detail_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(project_id,scene_id,revision))""")
            db.execute("""CREATE TABLE IF NOT EXISTS prod_world_proposals (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, instance_id TEXT NOT NULL, field TEXT NOT NULL,
                value_json TEXT NOT NULL, proposed_at_revision INTEGER NOT NULL,
                rationale TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL)""")

    def _base(self, project_id, scene_id):
        manifest=self.production.export_manifest(project_id, scene_id)
        plan=self.production.get_plan(project_id, scene_id)
        return manifest,plan

    def _session(self, db, project_id, scene_id, manifest, plan):
        row=db.execute("SELECT * FROM prod_world_sessions WHERE project_id=? AND scene_id=?",
                       (project_id,scene_id)).fetchone()
        if row is None:
            db.execute("INSERT INTO prod_world_sessions VALUES (?,?,?,?,?,?,?)",
                       (project_id,scene_id,manifest['layout_sha256'],plan['plan_revision'],0,'{}',stamp()))
            row=db.execute("SELECT * FROM prod_world_sessions WHERE project_id=? AND scene_id=?",
                           (project_id,scene_id)).fetchone()
        return dict(row)

    @staticmethod
    def _guard(row, manifest, plan, expected_revision=None):
        if row['base_sha'] != manifest['layout_sha256'] or row['base_plan_revision'] != plan['plan_revision']:
            raise RuntimeError('Approved staging changed; explicitly rebase world edits before proceeding')
        if expected_revision is not None and row['revision'] != expected_revision:
            raise RuntimeError('World state changed elsewhere; refresh before editing')

    @staticmethod
    def _compose(manifest, plan, fields):
        out=copy.deepcopy(manifest)
        instances={i['instance_id']:i for i in out['instances']}
        for instance_id, attributes in fields.items():
            if instance_id not in instances:
                raise RuntimeError('World edit refers to an instance no longer present')
            for field, metadata in attributes.items():
                val=check_value(field, metadata['value'])
                if field.startswith('pose.'):
                    instances[instance_id]['pose'][field.split('.',1)[1]]=val
                elif field == 'visible':
                    instances[instance_id]['visible']=val
        assets={i['asset_id']:i for i in out['instances']}
        poses={i['instance_id']:i['pose'] for i in out['instances']}
        verify_layout(plan['room'], plan['instances'], poses, assets)
        out['world_fields']=copy.deepcopy(fields)
        out['world_digest_sha256']=digest({'base':manifest['layout_sha256'],'fields':fields})
        return out

    def _write(self, db, project_id, scene_id, row, fields, action, detail, *, rebase=None):
        next_rev=row['revision']+1
        before=json.loads(row['fields_json'])
        db.execute("""INSERT INTO prod_world_events VALUES (?,?,?,?,?,?,?,?)""",
                   (project_id,scene_id,next_rev,action,compact(before),compact(fields),compact(detail),stamp()))
        base_sha,base_rev=rebase if rebase is not None else (row['base_sha'],row['base_plan_revision'])
        db.execute("""UPDATE prod_world_sessions SET revision=?,fields_json=?,base_sha=?,
                   base_plan_revision=?,updated_at=? WHERE project_id=? AND scene_id=?""",
                   (next_rev,compact(fields),base_sha,base_rev,stamp(),project_id,scene_id))
        return next_rev

    def read(self, project_id, scene_id):
        manifest,plan=self._base(project_id,scene_id)
        with self.studio._connection() as db:
            row=self._session(db,project_id,scene_id,manifest,plan)
            stale=row['base_sha']!=manifest['layout_sha256'] or row['base_plan_revision']!=plan['plan_revision']
            fields=json.loads(row['fields_json'])
            proposals=[dict(r) for r in db.execute("SELECT * FROM prod_world_proposals WHERE project_id=? AND scene_id=? ORDER BY created_at,id",
                       (project_id,scene_id))]
            for p in proposals:
                p['value']=json.loads(p.pop('value_json'))
        result={'revision':row['revision'],'base_layout_sha256':row['base_sha'],
                'base_plan_revision':row['base_plan_revision'],'stale':stale,
                'fields':fields,'proposals':proposals}
        if not stale:
            result['manifest']=self._compose(manifest,plan,fields)
        return result

    def set_human(self, project_id, scene_id, instance_id, field, value, expected_revision, *, lock=True):
        check_value(field,value)
        manifest,plan=self._base(project_id,scene_id)
        if instance_id not in {i['instance_id'] for i in manifest['instances']}:
            raise KeyError('Instance does not exist in this approved scene')
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=self._session(db,project_id,scene_id,manifest,plan)
            self._guard(row,manifest,plan,expected_revision)
            fields=json.loads(row['fields_json'])
            fields.setdefault(instance_id,{})[field]={
                'value':value,'unit':FIELDS[field],'author':'human',
                'provenance':'authored','locked':bool(lock),'at':stamp()}
            self._compose(manifest,plan,fields)
            self._write(db,project_id,scene_id,row,fields,'human_set',{'instance_id':instance_id,'field':field})
        return self.read(project_id,scene_id)

    def set_lock(self, project_id, scene_id, instance_id, field, locked, expected_revision):
        if type(locked) is not bool:
            raise ValueError('Lock state must be boolean')
        manifest,plan=self._base(project_id,scene_id)
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=self._session(db,project_id,scene_id,manifest,plan)
            self._guard(row,manifest,plan,expected_revision)
            fields=json.loads(row['fields_json'])
            if field not in fields.get(instance_id,{}):
                raise KeyError('Edited field not found')
            fields[instance_id][field]['locked']=locked
            self._write(db,project_id,scene_id,row,fields,'human_lock',{'field':field,'locked':locked})
        return self.read(project_id,scene_id)

    def propose_ai(self, project_id, scene_id, instance_id, field, value, expected_revision, rationale=''):
        check_value(field,value)
        if not isinstance(rationale,str) or len(rationale)>1000:
            raise ValueError('Invalid proposal rationale')
        manifest,plan=self._base(project_id,scene_id)
        if instance_id not in {i['instance_id'] for i in manifest['instances']}:
            raise KeyError('Instance does not exist')
        ident='WP_'+uuid.uuid4().hex
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=self._session(db,project_id,scene_id,manifest,plan)
            self._guard(row,manifest,plan,expected_revision)
            db.execute('INSERT INTO prod_world_proposals VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (ident,project_id,scene_id,instance_id,field,compact(value),row['revision'],rationale,'proposed',stamp()))
        return {'proposal_id':ident,'status':'proposed','world_revision':expected_revision}

    def decide(self, project_id, scene_id, proposal_id, decision, expected_revision):
        if decision not in ('accept','reject'):
            raise ValueError('Decision must be accept or reject')
        manifest,plan=self._base(project_id,scene_id)
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=self._session(db,project_id,scene_id,manifest,plan)
            self._guard(row,manifest,plan,expected_revision)
            proposal=db.execute('SELECT * FROM prod_world_proposals WHERE id=? AND project_id=? AND scene_id=?',
                                (proposal_id,project_id,scene_id)).fetchone()
            if not proposal:
                raise KeyError('AI proposal not found')
            if proposal['status'] != 'proposed':
                raise RuntimeError('AI proposal has already been decided')
            if decision == 'accept' and proposal['proposed_at_revision'] != row['revision']:
                raise RuntimeError('AI proposal was based on outdated world state')
            fields=json.loads(row['fields_json'])
            if decision=='accept':
                old=fields.get(proposal['instance_id'],{}).get(proposal['field'])
                if old and old['locked']:
                    raise RuntimeError('Human-locked attribute cannot be silently replaced by AI')
                fields.setdefault(proposal['instance_id'],{})[proposal['field']]={
                    'value':json.loads(proposal['value_json']), 'unit':FIELDS[proposal['field']],
                    'author':'accepted_ai', 'provenance':'authored','locked':False,'at':stamp()}
                self._compose(manifest,plan,fields)
                self._write(db,project_id,scene_id,row,fields,'accept_ai',{'proposal_id':proposal_id})
            db.execute('UPDATE prod_world_proposals SET status=? WHERE id=?',
                       ('accepted' if decision=='accept' else 'rejected',proposal_id))
        return self.read(project_id,scene_id)

    def undo(self, project_id, scene_id, expected_revision):
        manifest,plan=self._base(project_id,scene_id)
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=self._session(db,project_id,scene_id,manifest,plan)
            self._guard(row,manifest,plan,expected_revision)
            latest=db.execute('SELECT * FROM prod_world_events WHERE project_id=? AND scene_id=? ORDER BY revision DESC LIMIT 1',
                              (project_id,scene_id)).fetchone()
            if latest is None or latest['action']=='undo':
                raise RuntimeError('No directly undoable world edit; review history')
            if latest['revision']!=row['revision']:
                raise RuntimeError('World journal is out of sync')
            fields=json.loads(latest['before_json'])
            self._compose(manifest,plan,fields)
            if latest['action']=='accept_ai':
                prop=json.loads(latest['detail_json'])['proposal_id']
                db.execute("UPDATE prod_world_proposals SET status='undone' WHERE id=? AND status='accepted'",(prop,))
            self._write(db,project_id,scene_id,row,fields,'undo',{'undid_revision':latest['revision']})
        return self.read(project_id,scene_id)

    def rebase(self, project_id, scene_id, expected_revision):
        """Explicitly recheck inherited edits against a newly approved base plan."""
        manifest,plan=self._base(project_id,scene_id)
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=self._session(db,project_id,scene_id,manifest,plan)
            if row['revision']!=expected_revision:
                raise RuntimeError('World changed elsewhere')
            fields=json.loads(row['fields_json'])
            self._compose(manifest,plan,fields)
            self._write(db,project_id,scene_id,row,fields,'human_rebase',
                        {'previous_layout_sha':row['base_sha']},
                        rebase=(manifest['layout_sha256'],plan['plan_revision']))
        return self.read(project_id,scene_id)

    def export_manifest(self,project_id,scene_id):
        state=self.read(project_id,scene_id)
        if state['stale']:
            raise RuntimeError('World state is stale; explicit rebase required')
        return state['manifest']

    def export_blender_script(self,project_id,scene_id):
        return blender_script(self.export_manifest(project_id,scene_id))

    def journal(self, project_id, scene_id):
        self.production.export_manifest(project_id,scene_id)
        with self.studio._connection() as db:
            return [dict(row) for row in db.execute('SELECT revision,action,before_json,after_json,detail_json,created_at FROM prod_world_events WHERE project_id=? AND scene_id=? ORDER BY revision',
                                                    (project_id,scene_id))]
