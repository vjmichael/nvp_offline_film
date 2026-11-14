"""PROD-01 external Blender acceptance, never a simulated Blender success.

Requires a *real* Blender binary. The generated .blend is independently
re-opened and inspected in another Blender process before a preview is rendered.
No remote download, no renderer fallback presented as Blender.
"""
from __future__ import annotations

from pathlib import Path
import json
import shutil
import subprocess
from backend.nvp_w1g_legacy_blender_launch import run_trusted_blender

from backend.nvp_production_scene import ProductionScene, compact

AUDIT_SCRIPT = r'''import bpy, json, sys, math
from pathlib import Path
from mathutils import Vector
argv = sys.argv[sys.argv.index('--') + 1:]
opts = dict(zip(argv[::2], argv[1::2]))
manifest = json.loads(Path(opts['--manifest']).read_text('utf-8'))
room = manifest['room_m']
report = {'format':'nvp.blender.audit.v1','blender':bpy.app.version_string,
          'scene_id':manifest['scene_id'],'checks':[]}
def check(name, okay, evidence):
    report['checks'].append({'check':name,'passed':bool(okay),'evidence':evidence})
check('scene_sha', bpy.context.scene.get('nvp_source_sha') == manifest['source_scene_sha256'], 'scene fingerprint')
check('layout_sha', bpy.context.scene.get('nvp_manifest_sha') == manifest['layout_sha256'], 'layout fingerprint')
check('floor', bpy.data.objects.get('NVP_FLOOR') is not None, 'floor object')
for item in manifest['instances']:
    name='NVP_'+item['instance_id']; obj=bpy.data.objects.get(name)
    check('instance_exists:'+item['instance_id'], obj is not None, name)
    if obj is None: continue
    check('identity:'+item['instance_id'],obj.get('nvp_asset_id') == item['asset_id'], 'persistent asset ID')
    hidden = item.get('visible', True) is False
    check('visibility:'+item['instance_id'],
          bool(obj.hide_render) == hidden and bool(obj.hide_viewport) == hidden,
          {'expected_hidden':hidden,'render_hidden':bool(obj.hide_render),
           'viewport_hidden':bool(obj.hide_viewport)})
    pose=item['pose']
    xyz=[round(float(v),4) for v in obj.location]
    expect=[round(float(pose['x']),4),round(float(pose['y']),4),round(float(item['dimensions'][2])/2,4)]
    check('pose:'+item['instance_id'], max(abs(a-b) for a,b in zip(xyz,expect)) < 0.001, [xyz,expect])
    check('rotation:'+item['instance_id'], abs(((obj.rotation_euler.z-math.radians(pose['rotation'])+math.pi)%(2*math.pi))-math.pi)<0.001, pose['rotation'])
    for anchor_name, coords in item['anchors'].items():
        marker=bpy.data.objects.get('ANCHOR_'+item['instance_id']+'_'+anchor_name)
        check('anchor:'+item['instance_id']+':'+anchor_name,marker is not None and marker.parent==obj and marker.get('nvp_spatial_anchor')==anchor_name,coords)
check('camera',bpy.context.scene.camera is not None, 'establishing camera')
report['passed'] = all(x['passed'] for x in report['checks'])
Path(opts['--audit']).write_text(json.dumps(report,indent=2,sort_keys=True),'utf-8')
if not report['passed']:
    raise RuntimeError('NVP Blender audit failed; see audit.json')
if opts.get('--skip-render') != '1':
    sc=bpy.context.scene
    # Keep the accepted native Blender renderer; Windows headless CI lacks
    # a valid Workbench OpenGL/WGL context, so use Blender Cycles CPU.
    if sys.platform == 'win32':
        sc.render.engine='CYCLES'
        sc.cycles.device='CPU'
        sc.cycles.samples=1
    else:
        sc.render.engine='BLENDER_WORKBENCH'
    sc.render.filepath=opts['--render']; sc.render.image_settings.file_format='PNG'
    bpy.ops.render.render(write_still=True)
'''


def blender_available(executable='blender') -> dict:
    path = shutil.which(executable) if not Path(executable).exists() else str(Path(executable).resolve())
    if not path:
        return {'available':False,'reason':'No real Blender executable is installed or visible on PATH'}
    try:
        result=run_trusted_blender([path, '-b', '--version'],capture_output=True,text=True,timeout=15)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {'available':False,'reason':type(error).__name__ + ': '+str(error)}
    if result.returncode != 0 or not result.stdout.startswith('Blender '):
        return {'available':False,'reason':'Executable did not return an authentic Blender version'}
    return {'available':True,'path':path,'version':result.stdout.splitlines()[0]}


def run_acceptance(production: ProductionScene, project_id: str, scene_id: str,
                   directory: str | Path, executable='blender', timeout=240, render_preview=True) -> dict:
    """Build, reopen, audit and preview a director-approved scene in real Blender.

    An unavailable Blender is a BLOCKED acceptance, *not* a successful render.
    """
    manifest=production.export_manifest(project_id,scene_id)
    out=Path(directory).resolve(); out.mkdir(parents=True,exist_ok=True)
    man=out/'approved_manifest.json'; script=out/'build_scene.py'
    checker=out/'inspect_and_render.py'; blend=out/'scene.blend'
    audit=out/'blender_audit.json'; render=out/'preview.png'
    man.write_text(compact(manifest),'utf-8')
    script.write_text(production.export_blender_script(project_id,scene_id),'utf-8')
    checker.write_text(AUDIT_SCRIPT,'utf-8')
    state=blender_available(executable)
    if not state['available']:
        return {'status':'blocked_no_blender', 'reason':state['reason'],
                'manifest':str(man),'script':str(script),'audit_script':str(checker)}
    commands=[
        [state['path'],'-b','--factory-startup','-t','2','--python',str(script),'--','--output',str(blend)],
        [state['path'],'-b',str(blend),'-t','2','--python',str(checker),'--',
         '--manifest',str(man),'--audit',str(audit),'--render',str(render)]]
    if not render_preview:
        commands[1].extend(['--skip-render','1'])
    runs=[]
    for command in commands:
        try:
            p=run_trusted_blender(command,capture_output=True,text=True,timeout=timeout,cwd=out)
        except subprocess.TimeoutExpired as e:
            return {'status':'failed','reason':'Blender timed out','step':len(runs)+1,
                    'stderr':str(e)[-3000:],'version':state.get('version')}
        runs.append({'exit_code':p.returncode,'stdout_tail':p.stdout[-2000:],
                     'stderr_tail':p.stderr[-2000:]})
        if p.returncode:
            return {'status':'failed','reason':'Real Blender reported an error',
                    'step':len(runs),'version':state['version'],'runs':runs}
    if (not blend.is_file() or blend.stat().st_size == 0 or not audit.exists()
            or (render_preview and (not render.is_file() or render.stat().st_size == 0))):
        return {'status':'failed','reason':'Expected Blender outputs absent','runs':runs}
    evidence=json.loads(audit.read_text('utf-8'))
    if not evidence.get('passed'):
        return {'status':'failed','reason':'Geometry audit failed','evidence':evidence}
    return {'status':'passed_blender' if render_preview else 'passed_blender_audit_only',
            'version':state['version'],'blend':str(blend),
            'preview':str(render) if render_preview else None,
            'audit':str(audit),'checks':len(evidence['checks']),
            'rendered':bool(render_preview)}

MESH_AUDIT_SCRIPT = r'''import bpy, json, math, sys
from pathlib import Path
from mathutils import Vector
argv=sys.argv[sys.argv.index('--')+1:]
opts=dict(zip(argv[::2],argv[1::2]))
manifest=json.loads(Path(opts['--manifest']).read_text('utf-8'))
report={'format':'nvp.blender.meshpack.audit.v1','version':bpy.app.version_string,'checks':[]}
def check(name,okay,detail):
    report['checks'].append({'check':name,'passed':bool(okay),'evidence':detail})
check('package_sha',bpy.context.scene.get('nvp_package_sha')==manifest['package_sha256'],'package signature')
for item in manifest['instances']:
    label='NVP_'+item['instance_id']; root=bpy.data.objects.get(label)
    check('object:'+label,root is not None,label)
    if root is None: continue
    check('identity:'+label,root.get('nvp_asset_id')==item['asset_id'],item['asset_id'])
    expected_sha=item['mesh']['sha256'] if item.get('mesh') else 'procedural_proxy'
    check('mesh_digest:'+label,root.get('nvp_mesh_sha')==expected_sha,expected_sha)
    pose=item['pose']
    check('xy:'+label,abs(root.location.x-pose['x'])<.002 and abs(root.location.y-pose['y'])<.002,
          [root.location.x,root.location.y])
    check('rotation:'+label,abs(((root.rotation_euler.z-math.radians(pose['rotation'])+math.pi)%(2*math.pi))-math.pi)<.002,
          pose['rotation'])
    if item.get('mesh'):
        bpy.context.view_layer.update()
        vertices=[]
        for obj in bpy.data.objects:
            p=obj
            while p is not None and p!=root:p=p.parent
            if p==root and obj.type=='MESH':
                vertices.extend([obj.matrix_world@v.co for v in obj.data.vertices])
        check('geometry_present:'+label,bool(vertices),len(vertices))
        if vertices:
            mins=[min(float(v[i]) for v in vertices) for i in range(3)]
            maxs=[max(float(v[i]) for v in vertices) for i in range(3)]
            found=[a-b for a,b in zip(maxs,mins)]
            check('grounding:'+label,abs(mins[2])<.025,{'bottom_z':mins[2]})
            dims=item['dimensions']
            expected=([dims[1],dims[0],dims[2]] if pose['rotation']%180 else dims)
            check('mesh_bounds:'+label,all(abs(a-b)<=max(.025,.03*b) for a,b in zip(found,expected)),
                  {'measured':found,'expected':expected})
    for name,xyz in item['anchors'].items():
        marker=bpy.data.objects.get('ANCHOR_'+item['instance_id']+'_'+name)
        check('anchor:'+label+':'+name,marker is not None and marker.parent==root and
              marker.get('nvp_spatial_anchor')==name,xyz)
check('camera',bpy.context.scene.camera is not None,'preview camera')
report['passed']=all(x['passed'] for x in report['checks'])
Path(opts['--audit']).write_text(json.dumps(report,indent=2,sort_keys=True),'utf-8')
if not report['passed']:raise RuntimeError('Meshpack audit failed')
if opts.get('--skip-render') != '1':
    sc=bpy.context.scene
    sc.render.engine='BLENDER_WORKBENCH';sc.render.filepath=opts['--render']
    sc.render.image_settings.file_format='PNG'
    sc.render.resolution_x=960;sc.render.resolution_y=540;sc.render.resolution_percentage=100
    bpy.ops.render.render(write_still=True)
'''


def run_meshpack_acceptance(mesh_assets, project_id: str, scene_id: str,
                             directory: str | Path, executable='blender', timeout=240, render_preview=True) -> dict:
    """Only 'passed_blender' if both Blender construction and reopen audit run."""
    out=Path(directory).resolve()
    result=mesh_assets.export_bundle(project_id,scene_id,out)
    audit_script=out/'verify_meshpack.py'
    audit_script.write_text(MESH_AUDIT_SCRIPT,'utf-8')
    state=blender_available(executable)
    if not state['available']:
        return {'status':'blocked_no_blender','reason':state['reason'],
                'bundle_dir':str(out),'meshes':result['meshes']}
    blend=out/'meshpack.blend';audit=out/'meshpack_audit.json';preview=out/'meshpack_preview.png'
    commands=[
        [state['path'],'-b','--factory-startup','-t','2','--python',str(out/'build_scene.py'),'--','--output',str(blend)],
        [state['path'],'-b',str(blend),'-t','2','--python',str(audit_script),'--',
         '--manifest',str(out/'manifest.json'),'--audit',str(audit),'--render',str(preview)]]
    if not render_preview:
        commands[1].extend(['--skip-render','1'])
    runs=[]
    for i,command in enumerate(commands,1):
        try:
            p=run_trusted_blender(command,capture_output=True,text=True,timeout=timeout,cwd=out)
        except subprocess.TimeoutExpired:
            return {'status':'failed','step':i,'reason':'Blender timed out'}
        runs.append({'step':i,'exit_code':p.returncode,'stderr_tail':p.stderr[-2500:],'stdout_tail':p.stdout[-1500:]})
        if p.returncode:
            return {'status':'failed','reason':'Blender meshpack build/audit failed','runs':runs}
    if not audit.exists() or not blend.is_file() or (render_preview and not preview.is_file()):
        return {'status':'failed','reason':'Native Blender outputs missing','runs':runs}
    evidence=json.loads(audit.read_text('utf-8'))
    if not evidence.get('passed'):
        return {'status':'failed','reason':'Mesh geometry did not pass Blender audit','evidence':evidence}
    return {'status':'passed_blender' if render_preview else 'passed_blender_audit_only',
            'blend':str(blend),'preview':str(preview) if render_preview else None,
            'audit':str(audit),'checks':len(evidence['checks']),
            'version':state['version'],'rendered':bool(render_preview)}
