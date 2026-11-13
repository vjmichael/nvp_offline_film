"""NVP-PROD-05: frame-addressable, director-approved cinematic proxy sequences.

Film-only. Cameras come from the approved WorldState; actor paths come from
PROD-04 and dialogue durations must be measured. No rigged animation, inferred
speech time or generated voice is represented as completed film production.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from collections import defaultdict

from backend.nvp_studio import Studio
from backend.nvp_production_scene import compact, digest, blender_script
from backend.nvp_blocking_camera import BlockingCamera, check_180_axis, project

FPS = 24
MAX_FRAMES = 24 * 60 * 10
PATTERNS = frozenset({'master', 'single', 'two_shot', 'over_shoulder',
                      'reaction', 'insert', 'tracking'})


def checked_frame(value, label, *, minimum=1, maximum=MAX_FRAMES + 1):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f'{label} must be an integer frame between {minimum} and {maximum}')
    return value


def line_frames(duration, fps=FPS):
    if duration is None or isinstance(duration, bool) or not isinstance(duration, (int, float)):
        raise ValueError('Dialogue timing must be explicitly measured')
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Dialogue duration must be finite and positive')
    return max(1, math.ceil(duration * fps - 1e-9))


def follow_route(route, fraction):
    """Distance-parameterized A* waypoints: never teleport across a turn."""
    points = route['points']
    if len(points) == 1:
        return list(points[0])
    fraction = max(0., min(1., fraction))
    length = sum(math.dist(a, b) for a, b in zip(points, points[1:]))
    if length < 1e-9:
        return list(points[-1])
    distance = fraction * length
    for a, b in zip(points, points[1:]):
        segment = math.dist(a, b)
        if distance <= segment or b == points[-1]:
            ratio = 0. if segment < 1e-9 else max(0., min(1., distance / segment))
            return [a[i] + (b[i] - a[i]) * ratio for i in range(2)]
        distance -= segment
    return list(points[-1])


def actor_xy_at(instance, marks, seconds):
    """Actor starts at the approved mark, then holds at end of each move."""
    pos = [instance['pose']['x'], instance['pose']['y']]
    for row in sorted(marks, key=lambda m: (m['mark']['start_s'], m['id'])):
        mark = row['mark']
        if seconds < mark['start_s']:
            break
        if seconds <= mark['end_s']:
            fraction = (seconds - mark['start_s']) / (mark['end_s'] - mark['start_s'])
            return follow_route(row['path'], fraction)
        pos = list(mark['target_xy_m'])
    return pos


def dependencies(manifest, cameras, marks, dialogue):
    """Capture only approved/current film dependencies and their source fingerprints."""
    return digest({'world_sha': manifest['world_digest_sha256'],
                   'cameras': [{k: x[k] for k in ('id','world_sha','recipe','solution')} for x in cameras],
                   'marks': [{k: x[k] for k in ('id','world_sha','mark','path')} for x in marks],
                   'dialogue': dialogue})


def _warn(code, description, **evidence):
    return {'code': code, 'description': description, 'evidence': evidence}


def evaluate_sequence(plan, manifest, cameras, marks, dialogue):
    """Independent, deterministic structural + temporal and cinematic checks.

    Warnings are not hard errors: intentional cuts may be acknowledged by a
    human. All evidence is recomputed when approving or exporting.
    """
    errors = []
    warnings = []
    shots = plan['shots']
    cues = plan['cues']
    scene_cameras = {r['id']: r for r in cameras if not r['stale']}
    current_marks = [r for r in marks if not r['stale']]
    dialogue_by_id = {r['id']: r for r in dialogue['dialogue']}
    instances = {i['instance_id']: i for i in manifest['instances']}
    if plan.get('fps') != FPS:
        errors.append('Unknown frame rate; this release requires 24 fps')
    if not shots:
        errors.append('At least one shot is required')
    next_frame = 1
    for shot in shots:
        if shot['start_frame'] != next_frame or shot['stop_frame'] <= shot['start_frame']:
            errors.append('Shot order must cover continuous, nonempty frames')
        if shot['stop_frame'] > MAX_FRAMES + 1:
            errors.append('Sequence exceeds the ten-minute per-scene limit')
        next_frame = shot['stop_frame']
        cam = scene_cameras.get(shot['camera_id'])
        if cam is None:
            errors.append('Camera no longer belongs to approved scene: ' + shot['camera_id'])
        elif not cam['solution'].get('fits_all_subjects'):
            warnings.append(_warn('initial_framing:' + shot['id'],
                                  'Original camera solve does not fit every subject',shot=shot['id']))
    end = next_frame
    if len({s['id'] for s in shots}) != len(shots):
        errors.append('Duplicate shot identities')
    scheduled = set()
    windows = []
    for cue in cues:
        line = dialogue_by_id.get(cue['line_id'])
        if line is None:
            errors.append('Dialogue source no longer exists: ' + cue['line_id']);continue
        if cue['line_id'] in scheduled:
            errors.append('A dialogue line is scheduled more than once: ' + cue['line_id'])
        scheduled.add(cue['line_id'])
        if line.get('actor_instance_id') not in instances:
            errors.append('Unresolved dialogue speaker: ' + line['speaker_name']);continue
        try:
            duration = line_frames(line.get('duration_s'))
        except ValueError:
            errors.append('Dialogue duration was not measured: ' + cue['line_id']);continue
        start = cue['start_frame']
        if not isinstance(start,int) or isinstance(start,bool) or start<1 or start+duration>end:
            errors.append('Dialogue overruns the approved shot timeline: ' + cue['line_id'])
        windows.append((start,start+duration,cue['line_id']))
        if not any(shot['start_frame'] < start+duration and start < shot['stop_frame'] and
                   (line['actor_instance_id'] in scene_cameras.get(shot['camera_id'], {}).get('recipe', {}).get('subjects', []))
                   for shot in shots):
            warnings.append(_warn('speaker_offscreen:' + cue['line_id'],
                                  'Speaker is not a primary subject of any overlapping shot',line=cue['line_id']))
    for line in dialogue['dialogue']:
        if line['id'] not in scheduled:
            errors.append('Unscheduled screenplay dialogue: ' + line['id'])
    for earlier, later in zip(sorted(windows), sorted(windows)[1:]):
        if later[0] < earlier[1]:
            errors.append('Concurrent dialogue requires an explicit later workflow')
            break
    by_actor = defaultdict(list)
    for m in current_marks:
        by_actor[m['mark']['actor_instance_id']].append(m)
        if m['mark']['end_s'] > (end-1)/FPS + 1e-6:
            errors.append('Blocking movement continues beyond sequence: ' + m['id'])
    for shot in shots:
        row = scene_cameras.get(shot['camera_id'])
        if row is None:
            continue
        sol = row['solution']
        for frame in sorted({shot['start_frame'],(shot['start_frame']+shot['stop_frame']-1)//2,shot['stop_frame']-1}):
            for actor_id in row['recipe']['subjects']:
                item = instances.get(actor_id)
                if item is None:
                    errors.append('Camera subject no longer exists: ' + actor_id)
                    continue
                pos = actor_xy_at(item,by_actor[actor_id],(frame-1)/FPS)
                pt = [pos[0],pos[1],min(manifest['room_m'][2]-.2,item['dimensions'][2]*.86)]
                try:
                    xy = project(pt,sol['position_m'],sol['look_at_m'],sol['lens_mm'])
                except ValueError:
                    xy = None
                if xy is None or not .02<=xy[0]<=.98 or not .03<=xy[1]<=.97:
                    code = 'moving_out_of_frame:' + shot['id'] + ':' + actor_id
                    if not any(w['code']==code for w in warnings):
                        warnings.append(_warn(code,'Actor drifts outside static camera frame',
                                              shot=shot['id'],actor=actor_id,frame=frame,screen_xy=xy))
    for left, right in zip(shots,shots[1:]):
        ca=scene_cameras.get(left['camera_id']);cb=scene_cameras.get(right['camera_id'])
        if ca is None or cb is None:continue
        shared=[x for x in ca['recipe']['subjects'] if x in cb['recipe']['subjects']]
        if len(shared)>=2:
            actors=[instances.get(shared[0]),instances.get(shared[1])]
            if all(actors):
                sec=(right['start_frame']-1)/FPS
                coords=[actor_xy_at(a,by_actor[a['instance_id']],sec) for a in actors]
                result=check_180_axis(coords[0],coords[1],ca['solution']['position_m'],cb['solution']['position_m'])
                if result['crossed']:
                    warnings.append(_warn('axis_cross:' + left['id'] + ':' + right['id'],
                                          'Camera cut crosses the two-character 180-degree axis',
                                          from_shot=left['id'],to_shot=right['id']))
                elif result['ambiguous_on_line']:
                    warnings.append(_warn('axis_ambiguous:' + left['id'] + ':' + right['id'],
                                          'Camera sits on the character axis; screen direction is ambiguous',
                                          from_shot=left['id'],to_shot=right['id']))
        if shared and ca['recipe']['shot_size']==cb['recipe']['shot_size']:
            item=instances[shared[0]]
            sec=(right['start_frame']-1)/FPS
            point=actor_xy_at(item,by_actor[shared[0]],sec)
            a=math.atan2(ca['solution']['position_m'][1]-point[1],ca['solution']['position_m'][0]-point[0])
            b=math.atan2(cb['solution']['position_m'][1]-point[1],cb['solution']['position_m'][0]-point[0])
            diff=abs((a-b+math.pi)%(2*math.pi)-math.pi)
            if diff<math.pi/6:
                warnings.append(_warn('near_identical_cut:' + left['id'] + ':' + right['id'],
                                      'Near-identical angle and shot size may cause a jump cut',
                                      angle_difference_deg=round(math.degrees(diff),2)))
    return {'errors': errors,'warnings': warnings,
            'unacknowledged_warnings': [w for w in warnings if w['code'] not in plan['acknowledged_warnings']],
            'duration_s': round((end-1)/FPS,6),
            'total_frames': max(0,end-1), 'fps':FPS,
            'limitations': ['Proxy-only root translation; no skeletal animation or lip sync',
                            'Static camera per shot; no pixel-level occlusion/lighting assurance',
                            'Dialogue durations are measured inputs; speech audio is not produced']}


class ShotSequence:
    def __init__(self,studio: Studio):
        self.studio=studio
        self.bc=BlockingCamera(studio)
        with self.studio._connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS prod_shot_sequences (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, revision INTEGER NOT NULL, status TEXT NOT NULL,
                world_sha TEXT NOT NULL, dependency_sha TEXT NOT NULL,
                sequence_json TEXT NOT NULL, approved_digest TEXT,
                PRIMARY KEY(project_id,scene_id))''')
            db.execute('''CREATE TABLE IF NOT EXISTS prod_sequence_revisions (
                project_id TEXT NOT NULL, scene_id TEXT NOT NULL, revision INTEGER NOT NULL,
                action TEXT NOT NULL, sequence_json TEXT NOT NULL, recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(project_id,scene_id,revision))''')

    def _context(self,project_id,scene_id):
        manifest,world_sha=self.bc._snapshot(project_id,scene_id)
        cameras=self.bc.cameras(project_id,scene_id)
        marks=self.bc.marks(project_id,scene_id)
        dialogue=self.bc.dialogue(project_id,scene_id)
        return manifest, cameras, marks, dialogue, dependencies(manifest,cameras,marks,dialogue)

    def _stored(self,db,project_id,scene_id):
        r=db.execute('SELECT * FROM prod_shot_sequences WHERE project_id=? AND scene_id=?',
                     (project_id,scene_id)).fetchone()
        if r is None:raise KeyError('Shot sequence does not exist')
        return dict(r)

    def create(self,project_id,scene_id):
        manifest,cs,ms,dl,sha=self._context(project_id,scene_id)
        plan={'format':'nvp.production.sequence.v1','fps':FPS,'shots':[],'cues':[],
              'acknowledged_warnings':[]}
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if self._context(project_id,scene_id)[-1]!=sha:
                raise RuntimeError('Film inputs changed during sequence creation')
            db.execute('INSERT INTO prod_shot_sequences VALUES (?,?,?,?,?,?,?,?)',
                       (project_id,scene_id,0,'draft',manifest['world_digest_sha256'],sha,compact(plan),None))
            db.execute('INSERT INTO prod_sequence_revisions(project_id,scene_id,revision,action,sequence_json) VALUES (?,?,?,?,?)',
                       (project_id,scene_id,0,'create',compact(plan)))
        return self.read(project_id,scene_id)

    def read(self,project_id,scene_id):
        manifest,cs,ms,dl,sha=self._context(project_id,scene_id)
        with self.studio._connection() as db:
            row=self._stored(db,project_id,scene_id)
        plan=json.loads(row['sequence_json'])
        stale=sha!=row['dependency_sha'] or row['world_sha']!=manifest['world_digest_sha256']
        result=evaluate_sequence(plan,manifest,cs,ms,dl) if not stale else None
        if row['status']=='approved' and row['approved_digest']!=digest({'plan':plan,'dependency_sha':row['dependency_sha']}):
            stale=True
        return {'project_id':project_id,'scene_id':scene_id,'revision':row['revision'],
                'status':row['status'],'stale':stale,'world_sha':row['world_sha'],
                'dependency_sha':row['dependency_sha'],'plan':plan,'review':result}

    def _change(self,project_id,scene_id,expected_revision,action,mutator):
        manifest,cs,ms,dl,sha=self._context(project_id,scene_id)
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=self._stored(db,project_id,scene_id)
            if row['revision']!=expected_revision:raise RuntimeError('Shot sequence changed elsewhere')
            if row['status']!='draft':raise RuntimeError('Approved sequence is immutable; begin an explicit revision')
            if row['dependency_sha']!=sha or row['world_sha']!=manifest['world_digest_sha256']:
                raise RuntimeError('Sequence dependencies changed; create a new revision')
            plan=json.loads(row['sequence_json'])
            mutator(plan,cs,ms,dl)
            if self._context(project_id,scene_id)[-1]!=sha:
                raise RuntimeError('Scene changed while editing sequence')
            revision=expected_revision+1
            db.execute('UPDATE prod_shot_sequences SET revision=?,sequence_json=? WHERE project_id=? AND scene_id=?',
                       (revision,compact(plan),project_id,scene_id))
            db.execute('INSERT INTO prod_sequence_revisions(project_id,scene_id,revision,action,sequence_json) VALUES (?,?,?,?,?)',
                       (project_id,scene_id,revision,action,compact(plan)))
        return self.read(project_id,scene_id)

    def add_shot(self,project_id,scene_id,camera_id,frames,pattern,expected_revision):
        frames=checked_frame(frames,'Shot duration',minimum=1,maximum=MAX_FRAMES)
        if pattern not in PATTERNS:raise ValueError('Unknown coverage pattern')
        def op(plan,cs,ms,dl):
            if camera_id not in {x['id'] for x in cs if not x['stale']}:
                raise ValueError('Camera must be a current approved-scene camera')
            start=plan['shots'][-1]['stop_frame'] if plan['shots'] else 1
            if start+frames>MAX_FRAMES+1:raise ValueError('Shot would exceed sequence duration limit')
            plan['shots'].append({'id':'SH_'+uuid.uuid4().hex,'camera_id':camera_id,
                                  'pattern':pattern,'start_frame':start,'stop_frame':start+frames})
            plan['acknowledged_warnings']=[]
        return self._change(project_id,scene_id,expected_revision,'append_shot',op)

    def remove_last_shot(self,project_id,scene_id,expected_revision):
        def op(plan,cs,ms,dl):
            if not plan['shots']:raise ValueError('There are no shots to remove')
            plan['shots'].pop()
            limit=plan['shots'][-1]['stop_frame'] if plan['shots'] else 1
            existing={l['id']:l for l in dl['dialogue']}
            plan['cues']=[cue for cue in plan['cues'] if
                          cue['line_id'] in existing and existing[cue['line_id']].get('duration_s') is not None and
                          cue['start_frame']+line_frames(existing[cue['line_id']]['duration_s'])<=limit]
            plan['acknowledged_warnings']=[]
        return self._change(project_id,scene_id,expected_revision,'remove_last_shot',op)

    def clear_cue(self,project_id,scene_id,line_id,expected_revision):
        def op(plan,cs,ms,dl):
            before=len(plan['cues'])
            plan['cues']=[x for x in plan['cues'] if x['line_id']!=line_id]
            if before==len(plan['cues']):raise ValueError('Dialogue cue not scheduled')
            plan['acknowledged_warnings']=[]
        return self._change(project_id,scene_id,expected_revision,'remove_dialogue',op)

    def reset_draft(self,project_id,scene_id,expected_revision):
        """Discard draft shots, cue timings and stale references explicitly."""
        manifest,cs,ms,dl,sha=self._context(project_id,scene_id)
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=self._stored(db,project_id,scene_id)
            if row['revision']!=expected_revision or row['status']!='draft':
                raise RuntimeError('Only the current draft sequence can be reset')
            plan={'format':'nvp.production.sequence.v1','fps':FPS,'shots':[],
                  'cues':[],'acknowledged_warnings':[]}
            new_rev=expected_revision+1
            db.execute('UPDATE prod_shot_sequences SET revision=?,dependency_sha=?,world_sha=?,sequence_json=? WHERE project_id=? AND scene_id=?',
                       (new_rev,sha,manifest['world_digest_sha256'],compact(plan),project_id,scene_id))
            db.execute('INSERT INTO prod_sequence_revisions(project_id,scene_id,revision,action,sequence_json) VALUES (?,?,?,?,?)',
                       (project_id,scene_id,new_rev,'reset_draft',compact(plan)))
        return self.read(project_id,scene_id)

    def place_cue(self,project_id,scene_id,line_id,start_frame,expected_revision):
        start_frame=checked_frame(start_frame,'Dialogue first frame')
        def op(plan,cs,ms,dl):
            lines={x['id']:x for x in dl['dialogue']}
            if line_id not in lines:raise KeyError('Dialogue line not in current screenplay')
            line=lines[line_id]
            if line['actor_instance_id'] is None:raise ValueError('Speaker is not resolved to a staged actor')
            duration=line_frames(line['duration_s'])
            limit=plan['shots'][-1]['stop_frame'] if plan['shots'] else 1
            if start_frame+duration>limit:raise ValueError('Measured dialogue does not fit the shot timeline')
            plan['cues']=[x for x in plan['cues'] if x['line_id']!=line_id]
            plan['cues'].append({'line_id':line_id,'start_frame':start_frame})
            plan['cues'].sort(key=lambda x:(x['start_frame'],x['line_id']))
            plan['acknowledged_warnings']=[]
        return self._change(project_id,scene_id,expected_revision,'place_dialogue',op)

    def acknowledge(self,project_id,scene_id,codes,expected_revision):
        if not isinstance(codes,list) or len(set(codes))!=len(codes) or len(codes)>128 or any(not isinstance(x,str) for x in codes):
            raise ValueError('Expected distinct continuity warning codes')
        def op(plan,cs,ms,dl):
            manifest=self.bc._snapshot(project_id,scene_id)[0]
            review=evaluate_sequence(plan,manifest,cs,ms,dl)
            available={w['code'] for w in review['warnings']}
            if any(code not in available for code in codes):
                raise ValueError('Cannot acknowledge a non-existent continuity warning')
            plan['acknowledged_warnings']=sorted(codes)
        return self._change(project_id,scene_id,expected_revision,'director_acknowledged',op)

    def approve(self,project_id,scene_id,expected_revision):
        manifest,cs,ms,dl,sha=self._context(project_id,scene_id)
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=self._stored(db,project_id,scene_id)
            if row['revision']!=expected_revision:raise RuntimeError('Sequence revision conflict')
            if row['status']!='draft':raise RuntimeError('Sequence already approved')
            if row['dependency_sha']!=sha:raise RuntimeError('Sequence dependencies changed')
            plan=json.loads(row['sequence_json'])
            review=evaluate_sequence(plan,manifest,cs,ms,dl)
            if review['errors'] or review['unacknowledged_warnings']:
                raise RuntimeError('Resolve sequence errors and explicitly acknowledge cut warnings before approval')
            if self._context(project_id,scene_id)[-1]!=sha:
                raise RuntimeError('Dependencies changed during sequence approval')
            signature=digest({'plan':plan,'dependency_sha':sha})
            newrev=expected_revision+1
            db.execute('UPDATE prod_shot_sequences SET status=?,approved_digest=?,revision=? WHERE project_id=? AND scene_id=?',
                       ('approved',signature,newrev,project_id,scene_id))
            db.execute('INSERT INTO prod_sequence_revisions(project_id,scene_id,revision,action,sequence_json) VALUES (?,?,?,?,?)',
                       (project_id,scene_id,newrev,'director_approved',compact(plan)))
        return self.read(project_id,scene_id)

    def new_revision(self,project_id,scene_id,expected_revision):
        """Explicitly fork the last approved edit without erasing journal history."""
        manifest,cs,ms,dl,sha=self._context(project_id,scene_id)
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=self._stored(db,project_id,scene_id)
            if row['revision']!=expected_revision or row['status']!='approved':
                raise RuntimeError('Expected current approved sequence revision')
            newrev=row['revision']+1
            plan=json.loads(row['sequence_json'])
            plan['acknowledged_warnings']=[]
            # Do not keep stale camera/mark references: require the director to review or replace them.
            db.execute('UPDATE prod_shot_sequences SET revision=?,status=?,approved_digest=NULL,dependency_sha=?,world_sha=?,sequence_json=? WHERE project_id=? AND scene_id=?',
                       (newrev,'draft',sha,manifest['world_digest_sha256'],compact(plan),project_id,scene_id))
            db.execute('INSERT INTO prod_sequence_revisions(project_id,scene_id,revision,action,sequence_json) VALUES (?,?,?,?,?)',
                       (project_id,scene_id,newrev,'begin_revision',compact(plan)))
        return self.read(project_id,scene_id)

    def history(self,project_id,scene_id):
        self.studio.get_project(project_id)
        with self.studio._connection() as db:
            return [dict(x) for x in db.execute('SELECT * FROM prod_sequence_revisions WHERE project_id=? AND scene_id=? ORDER BY revision',
                                                (project_id,scene_id))]

    def export(self,project_id,scene_id):
        seq=self.read(project_id,scene_id)
        if seq['stale'] or seq['status']!='approved':raise RuntimeError('Only a current director-approved sequence can be exported')
        if seq['review']['errors'] or seq['review']['unacknowledged_warnings']:
            raise RuntimeError('Sequence was not independently valid at export')
        manifest,cs,ms,dl,sha=self._context(project_id,scene_id)
        if seq['dependency_sha']!=sha:raise RuntimeError('Sequence changed during export')
        current_cameras={c['id']:c for c in cs if not c['stale']}
        payload={'format':'nvp.production.timed_proxy.v1','project_id':project_id,'scene_id':scene_id,
                 'world_sha':manifest['world_digest_sha256'],'dependency_sha':sha,
                 'sequence_sha':digest(seq['plan']),'fps':FPS,'shots':[], 'actors':[],
                 'dialogue':[],'limitations':seq['review']['limitations']}
        for shot in seq['plan']['shots']:
            c=current_cameras[shot['camera_id']]
            payload['shots'].append({**shot, 'solution':c['solution'],'recipe':c['recipe']})
        for instance in manifest['instances']:
            if instance['category']!='character':continue
            payload['actors'].append({'instance_id':instance['instance_id'],'height_m':instance['dimensions'][2],
                                      'initial_xy':[instance['pose']['x'],instance['pose']['y']],
                                      'marks':[{'id':m['id'],'mark':m['mark'],'path':m['path']} for m in ms
                                               if not m['stale'] and m['mark']['actor_instance_id']==instance['instance_id']]})
        lines={x['id']:x for x in dl['dialogue']}
        for cue in seq['plan']['cues']:
            line=lines[cue['line_id']]
            payload['dialogue'].append({**cue,'speaker':line['actor_instance_id'],
                  'duration_frames':line_frames(line['duration_s']),
                  'source_script_line':line['script_line'],'timing_origin':line['timing_origin']})
        return {'manifest':manifest,'take':payload,'review':seq['review']}

    def blender_script(self,project_id,scene_id):
        package=self.export(project_id,scene_id)
        return animated_blender_script(package['manifest'],package['take'])


def animated_blender_script(manifest,take):
    """Append data-only animation before the trusted PROD-01 scene save command."""
    source=blender_script(manifest)
    anchor='args = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []'
    if source.count(anchor)!=1:raise RuntimeError('Unrecognized Blender script generator version')
    insertion='''# NVP-PROD-05 frame-accurate proxy camera coverage and A* actor motion.
# No model-generated source code is executed. All values below are inert JSON.
take = json.loads('''+repr(compact(take))+''')
assert take['format'] == 'nvp.production.timed_proxy.v1'
sc = bpy.context.scene
sc.render.fps = take['fps']
sc.frame_start = 1
sc.frame_end = max(1,take['shots'][-1]['stop_frame']-1)
sc['nvp_take_sha'] = take['sequence_sha']
sc['nvp_take_dependencies'] = take['dependency_sha']

def apply_walk(actor_id,actor_data):
    obj=bpy.data.objects['NVP_'+actor_id]
    initial=actor_data['initial_xy']
    h=actor_data['height_m']/2
    obj.location=(initial[0],initial[1],h)
    obj.keyframe_insert(data_path='location',frame=1)
    for step in sorted(actor_data['marks'],key=lambda x:x['mark']['start_s']):
        mark=step['mark'];path=step['path']['points']
        segments=[math.dist(a,b) for a,b in zip(path,path[1:])]
        length=sum(segments)
        start=mark['start_s'];end=mark['end_s']
        if length < 1e-10:
            obj.location=(path[0][0],path[0][1],h)
            obj.keyframe_insert(data_path='location',frame=1+start*take['fps'])
            obj.keyframe_insert(data_path='location',frame=1+end*take['fps'])
            continue
        traveled=0.0
        for n,point in enumerate(path):
            if n: traveled+=segments[n-1]
            frame=1+(start+(end-start)*traveled/length)*take['fps']
            obj.location=(point[0],point[1],h)
            obj.keyframe_insert(data_path='location',frame=frame)
    if obj.animation_data and obj.animation_data.action:
        action=obj.animation_data.action
        # Blender 5.x layered action handles were introduced recently; apply
        # interpolation only when the legacy fcurve collection is present.
        curves=[]
        if hasattr(action,'fcurves'):
            curves.extend(action.fcurves)
        if hasattr(action,'layers'):
            for layer in action.layers:
                for strip in layer.strips:
                    for bag in strip.channelbags:
                        curves.extend(bag.fcurves)
        for curve in curves:
            for key in curve.keyframe_points:key.interpolation='LINEAR'

for actor in take['actors']:
    apply_walk(actor['instance_id'],actor)

for shot in take['shots']:
    item=shot['solution']
    data=bpy.data.cameras.new('NVP_CAMERA_'+shot['id'])
    obj=bpy.data.objects.new('NVP_CAMERA_'+shot['id'],data)
    bpy.context.collection.objects.link(obj)
    obj.location=item['position_m']
    aim=Vector(item['look_at_m']) - obj.location
    obj.rotation_euler=aim.to_track_quat('-Z','Y').to_euler()
    data.lens=float(item['lens_mm'])
    obj['nvp_shot_id']=shot['id']
    obj['nvp_sequence_sha']=take['sequence_sha']
    marker=sc.timeline_markers.new('CUT_'+shot['id'],frame=shot['start_frame'])
    marker.camera=obj
sc.camera=bpy.data.objects['NVP_CAMERA_'+take['shots'][0]['id']]
sc.frame_set(1)
'''
    return source.replace(anchor,insertion+'\n'+anchor)

# Real Blender acceptance remains an explicit external execution step.
# The Python camera geometry tests do not stand in for a Blender scene audit.
SHOTS_AUDIT_SCRIPT = r'''import bpy, json, math, sys
from pathlib import Path
args=sys.argv[sys.argv.index('--')+1:]
opts=dict(zip(args[::2],args[1::2]))
take=json.loads(Path(opts['--take']).read_text('utf8'))
sc=bpy.context.scene
checks=[]
def check(key,success,evidence):
    checks.append({'check':key,'passed':bool(success),'evidence':evidence})
check('take_sha',sc.get('nvp_take_sha')==take['sequence_sha'],'approved shot sequence')
check('dependency_sha',sc.get('nvp_take_dependencies')==take['dependency_sha'],'source snapshot')
check('fps',sc.render.fps==take['fps'],sc.render.fps)
check('duration',sc.frame_start==1 and sc.frame_end==take['shots'][-1]['stop_frame']-1,sc.frame_end)
for shot in take['shots']:
    name='NVP_CAMERA_'+shot['id'];obj=bpy.data.objects.get(name)
    check('camera:'+shot['id'],obj is not None and obj.type=='CAMERA',name)
    if obj is None:continue
    check('lens:'+shot['id'],abs(obj.data.lens-shot['solution']['lens_mm'])<.01,obj.data.lens)
    check('camera_pose:'+shot['id'],all(abs(obj.location[i]-shot['solution']['position_m'][i])<.002 for i in range(3)),list(obj.location))
    markers=[m for m in sc.timeline_markers if m.name=='CUT_'+shot['id']]
    check('cut:'+shot['id'],len(markers)==1 and markers[0].frame==shot['start_frame'] and markers[0].camera==obj,shot['start_frame'])
for item in take['actors']:
    obj=bpy.data.objects.get('NVP_'+item['instance_id'])
    check('actor:'+item['instance_id'],obj is not None,'proxy actor object')
    if obj is None:continue
    for sample in item['audit_samples']:
        sc.frame_set(sample['frame'])
        xy=list(obj.location[:2])
        delta=math.dist(xy,sample['xy'])
        check('pose:'+item['instance_id']+':'+str(sample['frame']),delta<.035,
              {'actual':xy,'expected':sample['xy'],'error_m':delta})
sc.frame_set(1)
report={'format':'nvp.production.blender.take.audit.v1','blender':bpy.app.version_string,
        'passed':all(x['passed'] for x in checks),'checks':checks,
        'rendered':opts.get('--skip-render')!='1'}
Path(opts['--audit']).write_text(json.dumps(report,indent=2,sort_keys=True),'utf8')
if not report['passed']:raise RuntimeError('Shot sequence audit failed')
if opts.get('--skip-render')!='1':
    sc.frame_set(max(1,round(sc.frame_end/2)))
    sc.render.engine='BLENDER_WORKBENCH'
    sc.render.filepath=opts['--preview'];sc.render.image_settings.file_format='PNG'
    sc.render.resolution_x=640;sc.render.resolution_y=360
    sc.render.resolution_percentage=100
    bpy.ops.render.render(write_still=True)
'''


def run_shot_acceptance(seq,project_id,scene_id,directory,*,executable='blender',render_preview=True,timeout=180):
    """Save, reopen, audit cut cameras and evaluated animated actor XY in real bpy.

    GPU-less Windows CI may audit without claiming raster render. Linux CI also
    verifies an actual Workbench image. Unavailable Blender is never a pass.
    """
    from pathlib import Path
    import subprocess
from backend.nvp_w1g_owned_subprocess import run_owned_subprocess
    from backend.nvp_blender_acceptance import blender_available
    root=Path(directory).resolve();root.mkdir(parents=True,exist_ok=True)
    package=seq.export(project_id,scene_id)
    take=package['take']
    for actor in take['actors']:
        source=next(x for x in package['manifest']['instances'] if x['instance_id']==actor['instance_id'])
        marks=[{'id':x['id'],'mark':x['mark'],'path':x['path']} for x in actor['marks']]
        total=take['shots'][-1]['stop_frame']-1
        frames={1,max(1,total//2),total}
        for mark in marks:
            frames.add(max(1,min(total,1+round(mark['mark']['start_s']*FPS))))
            frames.add(max(1,min(total,1+round((mark['mark']['start_s']+mark['mark']['end_s'])/2*FPS))))
            frames.add(max(1,min(total,1+round(mark['mark']['end_s']*FPS))))
        actor['audit_samples']=[{'frame':frame,'xy':actor_xy_at(source,marks,(frame-1)/FPS)} for frame in sorted(frames)]
    script=animated_blender_script(package['manifest'],take)
    paths={'script':root/'make_take.py','take':root/'take.json','audit_script':root/'audit_take.py',
           'blend':root/'take.blend','audit':root/'take_audit.json','preview':root/'take_preview.png'}
    paths['script'].write_text(script,'utf8')
    paths['take'].write_text(compact(take),'utf8')
    paths['audit_script'].write_text(SHOTS_AUDIT_SCRIPT,'utf8')
    state=blender_available(executable)
    if not state['available']:
        return {'status':'blocked_no_blender','reason':state['reason'],
                'script':str(paths['script']),'take':str(paths['take'])}
    commands=[
        [state['path'],'-b','--factory-startup','-t','2','--python',str(paths['script']),
         '--','--output',str(paths['blend'])],
        [state['path'],'-b',str(paths['blend']),'-t','2','--python',str(paths['audit_script']),
         '--','--take',str(paths['take']),'--audit',str(paths['audit']),'--preview',str(paths['preview'])]
    ]
    if not render_preview:commands[1].extend(['--skip-render','1'])
    logs=[]
    for command in commands:
        try:
            run=run_owned_subprocess(command,cwd=root,capture_output=True,text=True,timeout=timeout)
        except subprocess.TimeoutExpired:
            return {'status':'failed','reason':'Blender timed out','step':len(logs)+1}
        logs.append({'exit_code':run.returncode,'stdout':run.stdout[-1500:],'stderr':run.stderr[-1500:]})
        if run.returncode:
            return {'status':'failed','reason':'Real Blender scene build or audit failed','steps':logs}
    if not paths['audit'].is_file() or not paths['blend'].is_file() or paths['blend'].stat().st_size==0:
        return {'status':'failed','reason':'Native scene or audit output missing','steps':logs}
    audit=json.loads(paths['audit'].read_text('utf8'))
    if not audit['passed']:
        return {'status':'failed','reason':'Shot audit check failed','audit':audit}
    if render_preview and (not paths['preview'].is_file() or paths['preview'].stat().st_size==0):
        return {'status':'failed','reason':'Requested Blender preview was not rendered','steps':logs}
    return {'status':'passed_blender' if render_preview else 'passed_blender_audit_only',
            'version':state['version'],'checks':len(audit['checks']),
            'blend':str(paths['blend']),'audit':str(paths['audit']),
            'preview':str(paths['preview']) if render_preview else None}
