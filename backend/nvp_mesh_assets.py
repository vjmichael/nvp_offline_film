"""NVP-PROD-03: offline, provenance-aware GLB asset registry and portable Blender packs.

Only self-contained GLB files are accepted. Files are content-addressed, never
loaded by executing artist-supplied Python. Imported geometry is checked against
its immutable proxy asset's declared dimensions, then atomically stored.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
import hashlib
import json
import math
import os
import shutil
import struct

from backend.nvp_production_scene import ProductionScene, compact, digest
from backend.nvp_world_state import WorldState
from backend.nvp_studio import Studio

MAX_GLB=32*1024*1024
MAX_GEOMETRIES=128
MAX_FACES=200_000
LICENSES={'CC0-1.0','CC-BY-4.0','creator_owned','commercial_licensed','evaluation_only'}


def inspect_glb(payload: bytes) -> dict:
    """Untrusted file is parsed under strict size/complexity budgets.

    Production deployments should run parsing in an OS-contained worker.
    No external URI references are ever fetched by this importer.
    """
    if not isinstance(payload,bytes) or len(payload)<20 or len(payload)>MAX_GLB:
        raise ValueError('GLB must be a nonempty local binary under 32 MiB')
    if payload[:4]!=b'glTF' or struct.unpack('<I',payload[4:8])[0]!=2 or struct.unpack('<I',payload[8:12])[0]!=len(payload):
        raise ValueError('Invalid GLB 2.0 header or length')
    import trimesh
    try:
        scene=trimesh.load(BytesIO(payload),file_type='glb',force='scene',process=False)
        if not isinstance(scene,trimesh.Scene):
            raise ValueError('GLB did not contain a 3D scene')
        geometry=list(scene.geometry.values())
        if not geometry or len(geometry)>MAX_GEOMETRIES:
            raise ValueError('GLB has no meshes or too many geometry objects')
        total_faces=sum(len(g.faces) for g in geometry if isinstance(g,trimesh.Trimesh))
        total_vertices=sum(len(g.vertices) for g in geometry if isinstance(g,trimesh.Trimesh))
        if total_faces<=0 or total_faces>MAX_FACES or total_vertices>MAX_FACES*3:
            raise ValueError('GLB geometry complexity exceeds 200,000 triangles')
        if len(scene.graph.nodes_geometry)>MAX_GEOMETRIES:
            raise ValueError('GLB has too many scene geometry nodes')
        low,high=scene.bounds
        if not all(math.isfinite(float(x)) for x in (*low,*high)):
            raise ValueError('Non-finite mesh bounds')
        dims=[round(float(b-a),4) for a,b in zip(low,high)]
        if not all(.001<=d<=40 for d in dims):
            raise ValueError('GLB bounding dimensions invalid in metres')
        return {'dimensions_m':dims,'bounds_min_m':[round(float(x),4) for x in low],
                'bounds_max_m':[round(float(x),4) for x in high],
                'faces':total_faces,'vertices':total_vertices,
                'mesh_count':len(geometry),'sha256':hashlib.sha256(payload).hexdigest(),
                'limitations':'Bounding-box validation only; no manifoldness, skinning or animation proof'}
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('Cannot parse self-contained GLB geometry') from exc


def validate_license(code, attribution, source):
    if code not in LICENSES:
        raise ValueError('Explicit asset license classification required')
    if not isinstance(attribution,str) or len(attribution)>500 or '\x00' in attribution:
        raise ValueError('Invalid asset attribution')
    if not isinstance(source,str) or len(source)>700 or '\x00' in source:
        raise ValueError('Invalid asset source')
    if code not in {'CC0-1.0','creator_owned'} and (not attribution.strip() or not source.strip()):
        raise ValueError('Licensed external assets require source and attribution')


class MeshAssets:
    def __init__(self, studio:Studio):
        self.studio=studio
        self.production=ProductionScene(studio)
        self.world=WorldState(studio)
        self.root=(studio.db_path.parent/'nvp_mesh_store').resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        with studio._connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS prod_mesh_bindings (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                asset_id TEXT NOT NULL, sha256 TEXT NOT NULL, info_json TEXT NOT NULL,
                license TEXT NOT NULL, attribution TEXT NOT NULL, source TEXT NOT NULL,
                PRIMARY KEY(project_id,asset_id))""")

    def register(self,project_id,asset_id,payload:bytes,license_code,attribution='',source=''):
        validate_license(license_code,attribution,source)
        info=inspect_glb(payload)
        assets={a['asset_id']:a for a in self.production.list_assets(project_id)}
        if asset_id not in assets:
            raise KeyError('Cannot attach mesh to an asset outside this film')
        expected=assets[asset_id]['dimensions']
        if any(abs(a-b)>max(.015, .02*b) for a,b in zip(info['dimensions_m'],expected)):
            raise ValueError('GLB geometry differs from immutable proxy dimensions: register a new measured asset')
        with self.studio._connection() as db:
            old=db.execute('SELECT sha256,license,attribution,source FROM prod_mesh_bindings WHERE project_id=? AND asset_id=?',
                           (project_id,asset_id)).fetchone()
        if old:
            if old['sha256']!=info['sha256']:
                raise RuntimeError('Asset geometry identity is immutable; create a new asset ID for new geometry')
            if (old['license'],old['attribution'],old['source']) != (license_code,attribution,source):
                raise RuntimeError('Asset provenance is immutable; register a new asset for a different rights record')
            return {'asset_id':asset_id,'status':'already_registered',**info}
        blob=self.root/(info['sha256']+'.glb')
        if not blob.exists():
            with NamedTemporaryFile(dir=self.root,prefix='.import_',suffix='.glb',delete=False) as tmp:
                tmp.write(payload);tmp.flush();os.fsync(tmp.fileno());temp=Path(tmp.name)
            os.replace(temp,blob)
        if hashlib.sha256(blob.read_bytes()).hexdigest()!=info['sha256']:
            raise RuntimeError('Content-addressed mesh file digest mismatch')
        with self.studio._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT sha256 FROM prod_mesh_bindings WHERE project_id=? AND asset_id=?',
                           (project_id,asset_id)).fetchone()
            if old:
                raise RuntimeError('Concurrent mesh binding changed; reload asset before retrying')
            db.execute('INSERT INTO prod_mesh_bindings VALUES (?,?,?,?,?,?,?)',
                       (project_id,asset_id,info['sha256'],compact(info),license_code,attribution,source))
        return {'asset_id':asset_id,'status':'registered',**info}

    def list(self,project_id):
        self.studio.get_project(project_id)
        with self.studio._connection() as db:
            rows=db.execute('SELECT * FROM prod_mesh_bindings WHERE project_id=? ORDER BY asset_id',(project_id,))
            return [{'asset_id':r['asset_id'],'sha256':r['sha256'],'license':r['license'],
                     'attribution':r['attribution'],'source':r['source'],**json.loads(r['info_json'])} for r in rows]

    def _package_manifest(self,project_id,scene_id):
        base=self.world.export_manifest(project_id,scene_id)
        result=json.loads(compact(base))
        with self.studio._connection() as db:
            binds={r['asset_id']:dict(r) for r in db.execute(
                'SELECT * FROM prod_mesh_bindings WHERE project_id=?',(project_id,))}
        licenses=[];needed={}
        for item in result['instances']:
            row=binds.get(item['asset_id'])
            if not row:
                item['mesh']=None
                continue
            sha=row['sha256'];path=self.root/(sha+'.glb')
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:
                raise RuntimeError('Mesh missing or corrupted; refuse to export')
            meta=json.loads(row['info_json'])
            item['mesh']={'path':'assets/'+sha+'.glb','sha256':sha,
                          'bounds_min_m':meta['bounds_min_m']}
            needed[sha]=path
            licenses.append({'asset_id':item['asset_id'],'name':item['name'],
                             'license':row['license'],'attribution':row['attribution'],
                             'source':row['source'],'sha256':sha})
        result['format']='nvp.production.meshpack.v1'
        result['rights_status']=('evaluation_or_unverified_rights' if any(item['license']=='evaluation_only'
                                 for item in licenses) else 'creator_declared_rights_not_independently_verified')
        result['package_sha256']=digest({'scene_sha':result['source_scene_sha256'],
                                         'world_digest':result['world_digest_sha256'],
                                         'licenses':licenses})
        return result,needed,licenses

    def export_bundle(self,project_id,scene_id,directory):
        """Export a Blender-ready directory, never execute Blender or a source asset."""
        manifest,needed,licenses=self._package_manifest(project_id,scene_id)
        out=Path(directory).resolve()
        out.mkdir(parents=True,exist_ok=True)
        assets_out=out/'assets';assets_out.mkdir(exist_ok=True)
        for sha,path in needed.items():
            target=assets_out/(sha+'.glb')
            if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==sha:
                continue
            shutil.copyfile(path,target)
        (out/'manifest.json').write_text(compact(manifest),'utf-8')
        (out/'licenses.json').write_text(json.dumps(licenses,indent=2,ensure_ascii=False),'utf-8')
        (out/'build_scene.py').write_text(blender_mesh_script(manifest),'utf-8')
        return {'status':'exported_unverified_in_blender','directory':str(out),
                'meshes':len(needed),'instances':len(manifest['instances']),
                'license_entries':len(licenses),'manifest':manifest}


def blender_mesh_script(manifest):
    """Build real GLB-linked assets in Blender; allowed paths come from verified hashes.

    The script is pure template plus JSON data, never user-provided Python.
    """
    data=repr(compact(manifest))
    return '''# NVP PROD-03 Blender meshpack. Offline, no arbitrary code execution from prompts.
import bpy, sys, json, math
from pathlib import Path
from mathutils import Vector
manifest=json.loads('''+data+''')
assert manifest['format']=='nvp.production.meshpack.v1'
folder=Path(__file__).resolve().parent
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)

def cube(name,dimensions,location):
    bpy.ops.mesh.primitive_cube_add(size=1,location=location)
    obj=bpy.context.object;obj.name=name;obj.dimensions=dimensions
    return obj
room=manifest['room_m']
floor=cube('NVP_FLOOR',[room[0],room[1],.10],[room[0]/2,room[1]/2,-.05])
floor['nvp_floor']=True
for item in manifest['instances']:
    pose=item['pose'];height=item['dimensions'][2]
    label='NVP_'+item['instance_id'];mesh_info=item.get('mesh')
    if mesh_info:
        if not mesh_info['path'].startswith('assets/') or '/' in mesh_info['path'][7:] or '..' in mesh_info['path']:
            raise ValueError('Invalid packaged asset path')
        target=folder/mesh_info['path']
        import hashlib
        if hashlib.sha256(target.read_bytes()).hexdigest()!=mesh_info['sha256']:
            raise ValueError('Packaged mesh checksum mismatch')
        before=set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(target))
        imported=set(bpy.data.objects)-before
        for obj in list(imported):
            if obj.type in {'CAMERA','LIGHT'}:
                bpy.data.objects.remove(obj,do_unlink=True)
        imported=set(bpy.data.objects)-before
        root=bpy.data.objects.new(label,None);bpy.context.collection.objects.link(root)
        root.empty_display_type='CUBE';root.empty_display_size=.3
        offset=bpy.data.objects.new(label+'_MESH_OFFSET',None);bpy.context.collection.objects.link(offset)
        offset.parent=root
        # NVP's validated asset bounds use Z-up metres. Blender's glTF importer
        # applies the glTF Y-up -> Blender Z-up basis rotation; cancel it for
        # the explicitly Z-up local asset contract before positioning anchors.
        offset.rotation_euler.x=-math.pi/2
        low=mesh_info['bounds_min_m'];dim=item['dimensions']
        offset.location=(-low[0]-dim[0]/2,-low[1]-dim[1]/2,-low[2])
        for obj in imported:
            if obj.parent is None:
                obj.parent=offset
    else:
        root=cube(label,item['dimensions'],[0,0,height/2])
    root['nvp_asset_id']=item['asset_id'];root['nvp_instance_id']=item['instance_id']
    root['nvp_mesh_sha']=mesh_info['sha256'] if mesh_info else 'procedural_proxy'
    root.location=(pose['x'],pose['y'],height/2 if not mesh_info else 0.0)
    root.rotation_euler.z=math.radians(pose['rotation'])
    if item.get('visible') is False:
        root.hide_render=True
        if mesh_info:
            for obj in imported:obj.hide_render=True
    for anchor_name,xyz in item['anchors'].items():
        marker=bpy.data.objects.new('ANCHOR_'+item['instance_id']+'_'+anchor_name,None)
        bpy.context.collection.objects.link(marker)
        marker.parent=root
        marker.empty_display_type='SPHERE';marker.empty_display_size=.10
        marker.location=(xyz[0],xyz[1],xyz[2]-(height/2 if not mesh_info else 0))
        marker['nvp_spatial_anchor']=anchor_name
cam_data=bpy.data.cameras.new('NVP_PreviewCam')
cam=bpy.data.objects.new('NVP_PreviewCam',cam_data);bpy.context.collection.objects.link(cam)
cam.location=(room[0]/2,-room[1]*1.4,room[2]*1.8)
cam.rotation_euler=(Vector((room[0]/2,room[1]/2,room[2]*.35))-cam.location).to_track_quat('-Z','Y').to_euler()
bpy.context.scene.camera=cam
light_data=bpy.data.lights.new('NVP_Key','AREA');light_data.energy=1200
light=bpy.data.objects.new('NVP_Key',light_data);bpy.context.collection.objects.link(light)
light.location=(room[0]/2,room[1]/2,room[2]*.9)
bpy.context.scene['nvp_package_sha']=manifest['package_sha256']
bpy.context.scene['nvp_source_sha']=manifest['source_scene_sha256']
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
if '--output' in args:
    idx=args.index('--output');target=Path(args[idx+1]);
    if target.suffix.lower()!='.blend':raise ValueError('Output must be a .blend file')
    bpy.ops.wm.save_as_mainfile(filepath=str(target))
'''
