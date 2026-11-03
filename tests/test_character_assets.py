"""PROD-06C: immutable rigged glTF and actor-binding authorisation tests."""
import ast
import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

from backend.nvp_studio import Studio
from backend.nvp_skinning import SkinnedPerformance
from backend.nvp_character_assets import (inspect_rigged_glb,CharacterAssets,
                                            CHARACTER_SCRIPT,CHARACTER_AUDIT_SCRIPT,
                                            run_character_acceptance)
from tests.test_skinning import make_fixture

ROLES=('hips','spine','head','arm_left','arm_right','leg_left','leg_right')


def synthetic_glb(*,external_image=False, wrong_attribute=False, duplicate_name=False,
                  external_buffer=False, require_extension=False, animations=False):
    """Minimal structural fixture. The genuine Blender exporter is tested separately."""
    raw=bytearray()
    views=[];accessors=[]
    def add(data,typ,ctype,count):
        off=len(raw);raw.extend(data)
        while len(raw)%4:raw.append(0)
        idx=len(views);views.append({'buffer':0,'byteOffset':off,'byteLength':len(data)})
        acc=len(accessors);accessors.append({'bufferView':idx,'componentType':ctype,
                                              'count':count,'type':typ});return acc
    pos=add(struct.pack('<9f',0,0,0,1,0,0,0,1,0),'VEC3',5126,3)
    j=add(bytes([0,1,0,0]*3),'VEC4',5121,3)
    w=add(struct.pack('<12f',*([.75,.25,0,0]*3)),'VEC4',5126,3)
    m=add(struct.pack('<'+('f'*16)*7,*([1.0]*112)),'MAT4',5126,7)
    nodes=[{'name':name} for name in ROLES]
    if duplicate_name:nodes[1]['name']='hips'
    nodes.append({'name':'Skinned body','mesh':0,'skin':0})
    doc={'asset':{'version':'2.0'},'buffers':[{'byteLength':len(raw)}],
         'bufferViews':views,'accessors':accessors,'nodes':nodes,
         'skins':[{'joints':list(range(7)),'inverseBindMatrices':m}],
         'meshes':[{'primitives':[{'attributes':{'POSITION':pos,'JOINTS_0':j,
                  'WEIGHTS_0':(pos if wrong_attribute else w)}}]}], 'scenes':[{'nodes':[7]}], 'scene':0}
    if external_image:doc['images']=[{'uri':'https://bad.example/a.png'}]
    if external_buffer:doc['buffers'][0]['uri']='http://example.com/mesh.bin'
    if require_extension:doc['extensionsRequired']=['KHR_unknown']
    if animations:doc['animations']=[{'channels':[],'samplers':[]}]
    data=json.dumps(doc,separators=(',',':')).encode()
    data+=b' ' * (-len(data)%4)
    chunks=struct.pack('<II',len(data),0x4e4f534a)+data+struct.pack('<II',len(raw),0x004e4942)+raw
    return b'glTF'+struct.pack('<II',2,12+len(chunks))+chunks


class CharacterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.studio,self.pid,self.sid,self.actor=make_fixture(self.root)
        skin=SkinnedPerformance(self.studio)
        s=skin.create(self.pid,self.sid)
        skin.approve(self.pid,self.sid,s['revision'])
        self.service=CharacterAssets(self.studio)

    def tearDown(self):self.temp.cleanup()

    def registered(self):return self.service.register(self.pid,synthetic_glb(),'creator_owned')

    def bound(self):
        asset=self.registered();s=self.service.create(self.pid,self.sid)
        s=self.service.bind(self.pid,self.sid,self.actor,asset['asset_id'],{r:r for r in ROLES},s['revision'])
        return self.service.approve(self.pid,self.sid,s['revision'])

    def test_glb_structure_budgets_and_stable_digest(self):
        file=synthetic_glb();i=inspect_rigged_glb(file)
        self.assertEqual(i['skinned_vertices'],3)
        self.assertEqual(i['joint_count'],7)
        self.assertEqual(i['sha256'],hashlib.sha256(file).hexdigest())
        self.assertEqual(inspect_rigged_glb(file),i)

    def test_reject_malformed_and_external_dependencies(self):
        bads=[b'',b'not glb',synthetic_glb()[:-1],synthetic_glb(duplicate_name=True),
              synthetic_glb(external_image=True),synthetic_glb(external_buffer=True),
              synthetic_glb(require_extension=True),synthetic_glb(animations=True),
              synthetic_glb(wrong_attribute=True)]
        for bad in bads:
            with self.subTest(n=len(bad)):
                with self.assertRaises(ValueError):inspect_rigged_glb(bad)

    def test_accessor_out_of_bounds_is_rejected(self):
        b=bytearray(synthetic_glb())
        jlen=struct.unpack_from('<I',b,12)[0]
        doc=json.loads(b[20:20+jlen])
        doc['bufferViews'][0]['byteLength']=123456
        mutated=json.dumps(doc,separators=(',',':')).encode()
        # Need build a new conforming GLB to reach the view check.
        mutated+=b' '*(-len(mutated)%4)
        binary=b[20+jlen+8:]
        chunks=struct.pack('<II',len(mutated),0x4e4f534a)+mutated+struct.pack('<II',len(binary),0x004e4942)+binary
        with self.assertRaisesRegex(ValueError,'bufferView'):
            inspect_rigged_glb(b'glTF'+struct.pack('<II',2,len(chunks)+12)+chunks)

    def test_license_declared_and_immutable_content_storage(self):
        asset=self.registered()
        self.assertFalse(asset['license_verified'])
        same=self.registered();self.assertEqual(asset['asset_id'],same['asset_id'])
        self.assertEqual(len(self.service.list(self.pid)),1)
        self.assertEqual(len(list((self.root/'nvp_rigged_store').glob('*.glb'))),1)
        reopened=CharacterAssets(Studio(self.studio.db_path))
        self.assertEqual(reopened.list(self.pid)[0]['sha256'],asset['sha256'])
        with self.assertRaises(ValueError):self.service.register(self.pid,synthetic_glb(),'unknown_license')
        with self.assertRaises(ValueError):self.service.register(self.pid,synthetic_glb(),'CC-BY-4.0')

    def test_approval_and_roundtrip(self):
        approved=self.bound();self.assertEqual(approved['status'],'approved')
        data=self.service.export(self.pid,self.sid)
        self.assertEqual(data['character']['bindings'][0]['role_map']['arm_left'],'arm_left')
        self.assertEqual(len(self.service.history(self.pid,self.sid)),3)
        self.assertEqual(CharacterAssets(Studio(self.studio.db_path)).export(self.pid,self.sid)['character'],data['character'])
        out=self.service.export_bundle(self.pid,self.sid,self.root/'export')
        self.assertEqual(out['actors'],1)
        self.assertTrue((self.root/'export'/'build_characters.py').is_file())
        self.assertTrue((self.root/'export'/'assets'/ (data['character']['bindings'][0]['sha256']+'.glb')).is_file())
        ast.parse((self.root/'export'/'build_characters.py').read_text())

    def test_stale_revision_and_locked_approval(self):
        asset=self.registered();s=self.service.create(self.pid,self.sid)
        with self.assertRaises(RuntimeError):self.service.export(self.pid,self.sid)
        s=self.service.bind(self.pid,self.sid,self.actor,asset['asset_id'],{r:r for r in ROLES},s['revision'])
        with self.assertRaises(RuntimeError):self.service.bind(self.pid,self.sid,self.actor,asset['asset_id'],{r:r for r in ROLES},0)
        self.service.approve(self.pid,self.sid,s['revision'])
        with self.assertRaises(RuntimeError):self.service.bind(self.pid,self.sid,self.actor,asset['asset_id'],{r:r for r in ROLES},s['revision'])
        with self.assertRaises(RuntimeError):self.service.approve(self.pid,self.sid,s['revision'])

    def test_foreign_asset_and_invalid_map(self):
        asset=self.registered();s=self.service.create(self.pid,self.sid)
        with self.assertRaises(KeyError):self.service.bind(self.pid,self.sid,'not_an_actor',asset['asset_id'],{r:r for r in ROLES},0)
        with self.assertRaises(KeyError):self.service.bind(self.pid,self.sid,self.actor,'CHR_from_other_project',{r:r for r in ROLES},0)
        for wrong in [{}, {r:'hips' for r in ROLES}, {r:r for r in ROLES if r!='head'},
                      {**{r:r for r in ROLES},'tail':'tail'}]:
            with self.assertRaises(ValueError):self.service.bind(self.pid,self.sid,self.actor,asset['asset_id'],wrong,0)
        with self.assertRaises(ValueError):self.service.bind(self.pid,self.sid,self.actor,asset['asset_id'],{**{r:r for r in ROLES},'head':'not_a_bone'},0)
        self.assertEqual(self.service.read(self.pid,self.sid)['revision'],0)

    def test_cross_project_registry_and_scene_scope(self):
        asset=self.registered();other=self.studio.create_project('Second Movie','')['id']
        with self.assertRaises(KeyError):self.service._context(other,self.sid)
        with self.studio._connection() as db:
            with self.assertRaises(KeyError):self.service._asset(db,other,asset['asset_id'])

    def test_tampered_blob_refuses_export(self):
        self.bound();listing=self.service.list(self.pid)
        sha=listing[0]['sha256'];blob=self.root/'nvp_rigged_store'/(sha+'.glb')
        blob.write_bytes(b'corrupt')
        with self.assertRaisesRegex(RuntimeError,'changed'):
            self.service.export(self.pid,self.sid)

    def test_skinning_becoming_stale_blocks_characters(self):
        self.bound()
        from backend.nvp_shot_sequence import ShotSequence
        seq=ShotSequence(self.studio);take=seq.read(self.pid,self.sid)
        seq.new_revision(self.pid,self.sid,take['revision'])
        with self.assertRaises(RuntimeError):self.service.export(self.pid,self.sid)

    def test_generated_blender_scripts_stay_fixed_template(self):
        self.bound();script=self.service.export_bundle(self.pid,self.sid,self.root/'out')
        source=(self.root/'out'/'build_characters.py').read_text()
        ast.parse(source);ast.parse(CHARACTER_SCRIPT);ast.parse(CHARACTER_AUDIT_SCRIPT)
        self.assertIn('bpy.ops.import_scene.gltf',source)
        self.assertIn('from pathlib import Path',CHARACTER_SCRIPT)
        self.assertIn('NVP_CHARACTER_RIG_',source)
        self.assertNotIn('subprocess',source)

    def test_native_absence_truthfully_blocked(self):
        self.bound()
        a=run_character_acceptance(self.service,self.pid,self.sid,self.root/'no_native',executable='blender-NVP-not-installed')
        self.assertEqual(a['status'],'blocked_no_blender')

if __name__=='__main__':unittest.main()
