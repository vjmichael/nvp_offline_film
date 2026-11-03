"""NVP-PROD-04: screenplay dialogue, collision-safe actor blocking, measured camera staging.

This is static previs: paths are grid-based and cameras use thin-lens pinhole
projection. No motion clip, rig, live Blender viewport or real voice is claimed.
"""
from __future__ import annotations

from collections import defaultdict
from heapq import heappop, heappush
import hashlib
import json
import math
import re
import uuid

from backend.nvp_studio import Studio, CHARACTER_CUE, CUE_SUFFIX, SCENE_HEADING
from backend.nvp_production_scene import ProductionScene, collision, geometry_ok, extents, digest, compact
from backend.nvp_world_state import WorldState

GRID=.25
MAX_PATH_NODES=15000
SENSOR_WIDTH=36.0
SENSOR_HEIGHT=20.25
SHOT_FILL={'wide':.27,'full':.48,'medium':.66,'close_up':.90}
SHOT_HEIGHT_FRACTION={'wide':1.0,'full':1.0,'medium':.70,'close_up':.35}
MAX_WALK_MPS=2.5
LIMIT_CAMERA_NODES=384


def check_number(v, minimum, maximum, label):
    if isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) or not minimum<=v<=maximum:
        raise ValueError(label+' out of range or nonfinite')
    return float(v)


def dot(a,b):return sum(x*y for x,y in zip(a,b))
def sub(a,b):return [x-y for x,y in zip(a,b)]
def plus(a,b):return [x+y for x,y in zip(a,b)]
def mul(a,k):return [x*k for x in a]
def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def unit(v):
    d=math.sqrt(dot(v,v))
    if d<1e-7:raise ValueError('Degenerate camera direction')
    return [x/d for x in v]


def camera_basis(position, look_at):
    forward=unit(sub(look_at,position))
    right=unit(cross(forward,[0,0,1]))
    up=unit(cross(right,forward))
    return forward,right,up


def project(point,position,look_at,lens_mm):
    forward,right,up=camera_basis(position,look_at)
    direction=sub(point,position)
    depth=dot(direction,forward)
    if depth<=.01:
        return None
    sx=.5 + (dot(direction,right)*lens_mm/(depth*SENSOR_WIDTH))
    sy=.5 + (dot(direction,up)*lens_mm/(depth*SENSOR_HEIGHT))
    return [round(sx,7),round(sy,7)]


def aim_at_screen_targets(position,points,weights,targets,lens):
    """Iteratively align the weighted centroid, reporting residuals honestly."""
    center=[sum(point[i]*w for point,w in zip(points,weights))/sum(weights) for i in range(3)]
    aimed=center[:]
    for _ in range(12):
        xy=[project(point,position,aimed,lens) for point in points]
        if any(x is None for x in xy):break
        weightsum=sum(weights)
        errx=sum((p[0]-t[0])*w for p,t,w in zip(xy,targets,weights))/weightsum
        erry=sum((p[1]-t[1])*w for p,t,w in zip(xy,targets,weights))/weightsum
        f,r,u=camera_basis(position,aimed)
        distance=sum(math.dist(position,point)*w for point,w in zip(points,weights))/weightsum
        aimed=plus(aimed,plus(mul(r,errx*distance*SENSOR_WIDTH/lens),
                              mul(u,erry*distance*SENSOR_HEIGHT/lens)))
    return aimed


def bounds_contains(pose,asset,point,radius=0.0):
    hx,hy=extents(asset,pose['rotation'])
    return (pose['x']-hx-radius <= point[0] <= pose['x']+hx+radius and
            pose['y']-hy-radius <= point[1] <= pose['y']+hy+radius)


def segment_crosses_box(start,end,pose,asset,margin=0.0):
    """Liang-Barsky clipping of a 2D sightline against an axis-aligned footprint."""
    hx,hy=extents(asset,pose['rotation']); hx+=margin;hy+=margin
    lowx=pose['x']-hx;highx=pose['x']+hx;lowy=pose['y']-hy;highy=pose['y']+hy
    dx=end[0]-start[0];dy=end[1]-start[1]
    lower,upper=0.0,1.0
    for p,q in [(-dx,start[0]-lowx),(dx,highx-start[0]),(-dy,start[1]-lowy),(dy,highy-start[1])]:
        if abs(p)<1e-12:
            if q<0:return False
            continue
        t=q/p
        if p<0:lower=max(lower,t)
        else:upper=min(upper,t)
        if lower>upper:return False
    return upper>.015 and lower<.985


def evaluate_clearance(pos, actor_asset, actor_pose, room, obstacles):
    center={'asset_id':actor_pose['asset_id'],'x':pos[0],'y':pos[1],
            'z':0,'rotation':actor_pose['rotation']}
    if not geometry_ok(center,actor_asset,room):return False
    return not any(collision(center,actor_asset,item['pose'],item) for item in obstacles)


def route_actor(start,goal,actor,obstacles,room,*,grid=GRID,max_nodes=MAX_PATH_NODES):
    """Collision-checked grid A* with exact endpoints and no diagonal corner cuts."""
    start=(float(start[0]),float(start[1]));goal=(float(goal[0]),float(goal[1]))
    if not evaluate_clearance(start,actor,{'asset_id':actor['asset_id'],'rotation':actor['pose']['rotation']},room,obstacles):
        raise ValueError('Actor starting mark violates collision clearance')
    if not evaluate_clearance(goal,actor,{'asset_id':actor['asset_id'],'rotation':actor['pose']['rotation']},room,obstacles):
        raise ValueError('Actor target mark violates collision clearance')
    if math.dist(start,goal)<1e-6:return {'points':[[*start]],'distance_m':0.0,'nodes_checked':0}
    origin=start
    snapped=(round((goal[0]-start[0])/grid),round((goal[1]-start[1])/grid))
    actor_pose={'asset_id':actor['asset_id'],'rotation':actor['pose']['rotation']}
    def coord(node):return (round(origin[0]+node[0]*grid,5),round(origin[1]+node[1]*grid,5))
    def safe(node):return evaluate_clearance(coord(node),actor,actor_pose,room,obstacles)
    def finish(node):
        p=coord(node)
        if math.dist(p,goal)>grid*1.8:return False
        if abs(p[0]-goal[0])>1e-8 and abs(p[1]-goal[1])>1e-8:
            # Diagonal finishing segment can graze a corner; check closely.
            segments=10
            return all(evaluate_clearance((p[0]+(goal[0]-p[0])*t/segments,
                                           p[1]+(goal[1]-p[1])*t/segments),actor,actor_pose,room,obstacles)
                       for t in range(1,segments+1))
        return all(evaluate_clearance((p[0]+(goal[0]-p[0])*t/10,
                                       p[1]+(goal[1]-p[1])*t/10),actor,actor_pose,room,obstacles)
                   for t in range(1,11))
    queue=[(0.0,0.0,(0,0))];previous={(0,0):None};best={(0,0):0.0};checked=0
    goal_node=None
    while queue and checked<max_nodes:
        _,cost,node=heappop(queue)
        if cost>best.get(node,float('inf'))+1e-6:continue
        checked+=1
        if finish(node):goal_node=node;break
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
            nxt=(node[0]+dx,node[1]+dy)
            if not safe(nxt):continue
            newcost=cost+grid
            if newcost>=best.get(nxt,float('inf'))-1e-8:continue
            previous[nxt]=node;best[nxt]=newcost
            h=math.dist(coord(nxt),goal)
            heappush(queue,(newcost+h,newcost,nxt))
    if goal_node is None:
        raise RuntimeError('No reachable actor path under the collision and search budget')
    nodes=[];current=goal_node
    while current is not None:
        nodes.append(list(coord(current)));current=previous[current]
    nodes.reverse()
    if math.dist(nodes[-1],goal)>1e-8:nodes.append(list(goal))
    length=sum(math.dist(a,b) for a,b in zip(nodes,nodes[1:]))
    return {'points':nodes,'distance_m':round(length,4),'nodes_checked':checked,
            'method':'deterministic_grid_astar','clearance':'static XY footprints only'}


def sightline_clear(camera,target,obstacles):
    return not any(segment_crosses_box(camera,target,item['pose'],item) for item in obstacles)


def camera_candidates(room,read_points,lens,fill,subject_height_m):
    center=[sum(p[i] for p in read_points)/len(read_points) for i in range(3)]
    base=max(.7,min(16.0,(lens*subject_height_m)/(fill*SENSOR_HEIGHT)))
    for scale in (0.8,1.0,1.3,1.6,2.1):
        distance=base*scale
        for i in range(24):
            theta=2*math.pi*i/24
            x=center[0]+distance*math.sin(theta)
            y=center[1]-distance*math.cos(theta)
            z=min(room[2]-.2,max(.6,center[2]+.13))
            if .15<=x<=room[0]-.15 and .15<=y<=room[1]-.15:
                yield [round(x,6),round(y,6),round(z,6)]


def solve_camera(manifest, subject_ids, *, lens_mm=50, shot_size='medium',
                 desired_positions=None, worst_weight=.35):
    lens=check_number(lens_mm,18,135,'Focal length')
    worst_weight=check_number(worst_weight,0,1,'Worst-case weight')
    if shot_size not in SHOT_FILL:raise ValueError('Unknown shot size')
    if not isinstance(subject_ids,list) or not 1<=len(subject_ids)<=3 or len(set(subject_ids))!=len(subject_ids):
        raise ValueError('Use one to three unique subject instance IDs')
    scene={item['instance_id']:item for item in manifest['instances']}
    if any(i not in scene for i in subject_ids):raise KeyError('Camera subject not found')
    if any(scene[i]['category']!='character' for i in subject_ids):raise ValueError('Camera subject must be a character')
    points=[[scene[i]['pose']['x'],scene[i]['pose']['y'],
             min(manifest['room_m'][2]-.2,scene[i]['dimensions'][2]*.86)] for i in subject_ids]
    if desired_positions is None:
        desired_positions=([[.5,.52]] if len(points)==1 else
                           [[.38,.52],[.62,.52]] if len(points)==2 else
                           [[.3,.52],[.5,.52],[.7,.52]])
    if (len(desired_positions)!=len(points) or any(not isinstance(t,(list,tuple)) or len(t)!=2 or
        any(isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) or not .1<=v<=.9 for v in t)
        for t in desired_positions)):
        raise ValueError('Screen-space targets must be normalized XY points')
    room=manifest['room_m']
    subject_height_m=sum(scene[i]['dimensions'][2] for i in subject_ids)/len(subject_ids) * SHOT_HEIGHT_FRACTION[shot_size]
    obstacles=[item for item in manifest['instances'] if item['instance_id'] not in subject_ids]
    best=None;measured=0;blocked=0
    for position in camera_candidates(room,points,lens,SHOT_FILL[shot_size],subject_height_m):
        if any(bounds_contains(item['pose'],item,position,.20) for item in manifest['instances']):
            blocked+=1;continue
        if any(not sightline_clear(position,p,obstacles) for p in points):
            blocked+=1;continue
        aim=aim_at_screen_targets(position,points,[1]*len(points),desired_positions,lens)
        projected=[project(p,position,aim,lens) for p in points]
        if any(p is None for p in projected):continue
        residuals=[math.dist(p,q) for p,q in zip(projected,desired_positions)]
        mean=sum(residuals)/len(residuals);worst=max(residuals)
        # Encourage the requested shot size as well as camera composition.
        fill_error=abs((lens*subject_height_m/(max(.1,math.dist(position,points[0]))*SENSOR_HEIGHT))-SHOT_FILL[shot_size])
        penalty=.035*fill_error
        score=(1-worst_weight)*mean+worst_weight*worst+penalty
        measured+=1
        candidate={'position_m':position,'look_at_m':[round(v,6) for v in aim],
                   'screen_targets':desired_positions,
                   'screen_observed':projected,
                   'residuals': [round(x,6) for x in residuals],
                   'mean_residual':round(mean,6),'max_residual':round(worst,6),
                   'lens_mm':lens,'shot_size':shot_size,
                   'score':round(score,7),'subjects':subject_ids}
        if best is None or score<best['score']:
            best=candidate
    if best is None:
        raise RuntimeError('No camera position has an unobstructed valid line of sight')
    best['candidates_evaluated']=measured
    best['occlusion_or_collision_rejects']=blocked
    best['fits_all_subjects']=all(.02<=p[0]<=.98 and .03<=p[1]<=.97 for p in best['screen_observed'])
    best['limitations']='Static point projection and footprint occlusion; actual Blender raster framing not yet verified'
    return best


def validate_screenplay_dialogue(scene,registered_cast):
    """Use rigid cue+dialogue text, preserving evidence and unresolved speakers."""
    lines=scene['text'].splitlines()
    dialogue=[];unresolved=[]
    for ix,line in enumerate(lines):
        cue=line.strip()
        if not CHARACTER_CUE.fullmatch(cue) or SCENE_HEADING.fullmatch(cue):continue
        if cue in {'CUT TO:','FADE OUT:','THE END'}:continue
        j=ix+1
        while j<len(lines) and not lines[j].strip():j+=1
        if j>=len(lines):continue
        spoken=lines[j].strip()
        if not spoken or CHARACTER_CUE.fullmatch(spoken) or SCENE_HEADING.fullmatch(spoken):continue
        speaker=CUE_SUFFIX.sub('',cue).strip()
        actor=registered_cast.get(speaker.casefold())
        if not actor and speaker not in unresolved:unresolved.append(speaker)
        ident='DL_'+hashlib.sha256((scene['id']+'|'+str(ix)+'|'+speaker+'|'+spoken).encode()).hexdigest()[:16]
        dialogue.append({'id':ident,'speaker_name':speaker,'actor_instance_id':actor,
                         'text':spoken,'scene_line':j+1,'script_line':scene['start_line']+j,
                         'duration_s':None,'timing_origin':'requires_audio_or_director'})
    return {'dialogue':dialogue,'unresolved_speakers':unresolved}


class BlockingCamera:
    def __init__(self,studio:Studio):
        self.studio=studio
        self.prod=ProductionScene(studio)
        self.world=WorldState(studio)
        with studio._connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS prod_actor_marks (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, world_sha TEXT NOT NULL, actor_instance_id TEXT NOT NULL,
                mark_json TEXT NOT NULL, path_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            db.execute("""CREATE TABLE IF NOT EXISTS prod_cameras (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, world_sha TEXT NOT NULL, recipe_json TEXT NOT NULL,
                solution_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            db.execute("""CREATE TABLE IF NOT EXISTS prod_dialogue_listeners (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, line_id TEXT NOT NULL, source_scene_sha TEXT NOT NULL,
                listeners_json TEXT NOT NULL,
                PRIMARY KEY(project_id,scene_id,line_id))""")
            db.execute("""CREATE TABLE IF NOT EXISTS prod_dialogue_timing (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scene_id TEXT NOT NULL, line_id TEXT NOT NULL, source_scene_sha TEXT NOT NULL,
                duration_s REAL NOT NULL, audio_sha256 TEXT, timing_origin TEXT NOT NULL,
                PRIMARY KEY(project_id,scene_id,line_id))""")

    def _snapshot(self,project_id,scene_id):
        state=self.world.read(project_id,scene_id)
        if state['stale']:raise RuntimeError('World state changed; explicit rebase required')
        manifest=state['manifest']
        return manifest,manifest['world_digest_sha256']

    def dialogue(self,project_id,scene_id):
        manifest,sha=self._snapshot(project_id,scene_id)
        project=self.studio.get_project(project_id)
        scene=next((s for s in project['scenes'] if s['id']==scene_id),None)
        if not scene:raise KeyError('Screenplay scene absent')
        names={}
        for item in manifest['instances']:
            if item['category']=='character':
                name=item['name'].casefold()
                if name in names:
                    names[name]=None  # Duplicate names become unresolved, never silently selected.
                else:names[name]=item['instance_id']
        parsed=validate_screenplay_dialogue(scene,names)
        with self.studio._connection() as db:
            timed={r['line_id']:dict(r) for r in db.execute(
                'SELECT * FROM prod_dialogue_timing WHERE project_id=? AND scene_id=?',(project_id,scene_id))}
            listeners={r['line_id']:dict(r) for r in db.execute(
                'SELECT * FROM prod_dialogue_listeners WHERE project_id=? AND scene_id=?',(project_id,scene_id))}
        for line in parsed['dialogue']:
            linked=listeners.get(line['id'])
            line['listener_instance_ids']=(json.loads(linked['listeners_json'])
                 if linked and linked['source_scene_sha']==manifest['source_scene_sha256'] else [])
            state=timed.get(line['id'])
            if state and state['source_scene_sha']==manifest['source_scene_sha256']:
                line['duration_s']=state['duration_s'];line['timing_origin']=state['timing_origin']
        return {'scene_id':scene_id,'world_sha':sha,**parsed}

    def set_listeners(self,project_id,scene_id,line_id,listener_instance_ids):
        manifest,_=self._snapshot(project_id,scene_id)
        if not isinstance(listener_instance_ids,list) or len(listener_instance_ids)>12 or len(set(listener_instance_ids))!=len(listener_instance_ids):
            raise ValueError('Listeners must be a short list of unique actor IDs')
        cast={i['instance_id'] for i in manifest['instances'] if i['category']=='character'}
        if any(id not in cast for id in listener_instance_ids):
            raise ValueError('Listener not present in the film scene')
        lines={l['id']:l for l in self.dialogue(project_id,scene_id)['dialogue']}
        if line_id not in lines:raise KeyError('Dialogue line does not exist')
        if lines[line_id]['actor_instance_id'] in listener_instance_ids:
            raise ValueError('Speaker cannot also be the listener')
        with self.studio._connection() as db:
            db.execute('INSERT OR REPLACE INTO prod_dialogue_listeners VALUES (?,?,?,?,?)',
                       (project_id,scene_id,line_id,manifest['source_scene_sha256'],compact(listener_instance_ids)))
        return self.dialogue(project_id,scene_id)

    def set_dialogue_duration(self,project_id,scene_id,line_id,duration_s,origin='director_measured',audio_sha=None):
        check_number(duration_s,.05,300,'Dialogue duration')
        if origin not in {'director_measured','tts_measured'}:raise ValueError('Duration must be explicitly measured')
        if audio_sha is not None and (not isinstance(audio_sha,str) or not re.fullmatch('[a-f0-9]{64}',audio_sha)):
            raise ValueError('Audio fingerprint must be SHA256')
        manifest,sha=self._snapshot(project_id,scene_id)
        if line_id not in {l['id'] for l in self.dialogue(project_id,scene_id)['dialogue']}:
            raise KeyError('Dialogue line no longer exists')
        with self.studio._connection() as db:
            db.execute('INSERT OR REPLACE INTO prod_dialogue_timing VALUES (?,?,?,?,?,?,?)',
                       (project_id,scene_id,line_id,manifest['source_scene_sha256'],float(duration_s),audio_sha,origin))
        return self.dialogue(project_id,scene_id)

    def add_mark(self,project_id,scene_id,actor_instance_id,target_xy,
                 *,target_instance_id=None,anchor_name=None,max_gap=1.5,
                 start_s=0,end_s=5,action='walk',facing_instance_id=None):
        manifest,sha=self._snapshot(project_id,scene_id)
        instances={i['instance_id']:i for i in manifest['instances']}
        actor=instances.get(actor_instance_id)
        if actor is None or actor['category']!='character':
            raise ValueError('Blocking actor must be a registered character instance')
        if not isinstance(target_xy,(tuple,list)) or len(target_xy)!=2:
            raise ValueError('Blocking target must be XY metres')
        xy=[check_number(v,0,16,'Blocking mark') for v in target_xy]
        check_number(max_gap,.05,3.0,'Anchor gap')
        start_s=check_number(start_s,0,1e5,'Mark start')
        end_s=check_number(end_s,0,1e5,'Mark end')
        if end_s<=start_s:raise ValueError('Blocking end must follow start')
        if action not in {'walk','stand','turn','enter','exit'}:raise ValueError('Unknown blocking action')
        if facing_instance_id is not None and facing_instance_id not in instances:
            raise ValueError('Facing target absent')
        if target_instance_id is not None:
            target=instances.get(target_instance_id)
            if target is None or not anchor_name or anchor_name not in target['anchors']:
                raise ValueError('Referenced blocking anchor missing')
            ax,ay,az=target['anchors'][anchor_name]
            radians=math.radians(target['pose']['rotation'])
            p=(target['pose']['x']+ax*math.cos(radians)-ay*math.sin(radians),
               target['pose']['y']+ax*math.sin(radians)+ay*math.cos(radians))
            if math.dist(p,xy)>max_gap:
                raise ValueError('Blocking mark is too far from named anchor')
        elif anchor_name is not None:
            raise ValueError('Anchor requires a target instance')
        obstacles=[i for i in manifest['instances'] if i['instance_id']!=actor_instance_id]
        with self.studio._connection() as db:
            prior=[json.loads(r['mark_json']) for r in db.execute(
               'SELECT mark_json FROM prod_actor_marks WHERE project_id=? AND scene_id=? AND actor_instance_id=? AND world_sha=?',
               (project_id,scene_id,actor_instance_id,sha))]
        if prior:
            last=max(prior,key=lambda item:item['end_s'])
            if start_s<last['end_s']-1e-6:
                raise ValueError('Actor marks cannot overlap in time')
            origin=last['target_xy_m']
        else:
            origin=(actor['pose']['x'],actor['pose']['y'])
        route=route_actor(origin,xy,actor,obstacles,manifest['room_m'])
        if action in {'stand','turn'} and route['distance_m']>.11:
            raise ValueError('A stationary mark cannot teleport the actor')
        if action in {'walk','enter','exit'} and route['distance_m']>MAX_WALK_MPS*(end_s-start_s)+1e-6:
            raise ValueError('Blocking mark is unreachable within the assigned time')
        mark={'actor_instance_id':actor_instance_id,'target_xy_m':xy,
              'target_instance_id':target_instance_id,'anchor_name':anchor_name,
              'max_anchor_gap_m':max_gap,'start_s':start_s,'end_s':end_s,
              'action':action,'facing_instance_id':facing_instance_id}
        ident='MK_'+uuid.uuid4().hex
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if self._snapshot(project_id,scene_id)[1]!=sha:
                raise RuntimeError('World moved while blocking path was solving')
            db.execute('INSERT INTO prod_actor_marks(id,project_id,scene_id,world_sha,actor_instance_id,mark_json,path_json) VALUES (?,?,?,?,?,?,?)',
                       (ident,project_id,scene_id,sha,actor_instance_id,compact(mark),compact(route)))
        return {'id':ident,'world_sha':sha,'mark':mark,'path':route,'stale':False}

    def marks(self,project_id,scene_id):
        _,sha=self._snapshot(project_id,scene_id)
        with self.studio._connection() as db:
            rows=db.execute('SELECT * FROM prod_actor_marks WHERE project_id=? AND scene_id=? ORDER BY created_at,id',
                            (project_id,scene_id))
            return [{'id':r['id'],'world_sha':r['world_sha'],
                     'stale':r['world_sha']!=sha,'mark':json.loads(r['mark_json']),
                     'path':json.loads(r['path_json'])} for r in rows]

    def solve_shot(self,project_id,scene_id,subject_ids,*,lens_mm=50,shot_size='medium',desired_positions=None):
        manifest,sha=self._snapshot(project_id,scene_id)
        solution=solve_camera(manifest,subject_ids,lens_mm=lens_mm,shot_size=shot_size,
                              desired_positions=desired_positions)
        recipe={'subjects':subject_ids,'lens_mm':lens_mm,'shot_size':shot_size,
                'desired_positions':desired_positions}
        ident='CM_'+uuid.uuid4().hex
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if self._snapshot(project_id,scene_id)[1]!=sha:
                raise RuntimeError('World moved while camera was solving')
            db.execute('INSERT INTO prod_cameras(id,project_id,scene_id,world_sha,recipe_json,solution_json) VALUES (?,?,?,?,?,?)',
                       (ident,project_id,scene_id,sha,compact(recipe),compact(solution)))
        return {'id':ident,'world_sha':sha,'recipe':recipe,'solution':solution,'stale':False}

    def cameras(self,project_id,scene_id):
        _,sha=self._snapshot(project_id,scene_id)
        with self.studio._connection() as db:
            rows=db.execute('SELECT * FROM prod_cameras WHERE project_id=? AND scene_id=? ORDER BY created_at,id',
                            (project_id,scene_id))
            return [{'id':r['id'],'world_sha':r['world_sha'],
                     'stale':r['world_sha']!=sha,'recipe':json.loads(r['recipe_json']),
                     'solution':json.loads(r['solution_json'])} for r in rows]


def check_180_axis(a,b,camera_one,camera_two):
    def side(p):return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
    first=side(camera_one);second=side(camera_two)
    if abs(first)<1e-6 or abs(second)<1e-6:
        return {'crossed':False,'ambiguous_on_line':True}
    return {'crossed':first*second<0,'ambiguous_on_line':False}
