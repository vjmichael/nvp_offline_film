"""PROD-06E2A: identity, anatomy and refusal tests (no fabricated native passes)."""
import ast
import json
import struct
import tempfile
import unittest
from pathlib import Path

from backend.nvp_leg_chains import (
    LegChainIdentity, LEGCHAIN_PROBE_SCRIPT, analyze_anatomy_snapshot,
    validate_leg_mapping)
from backend.nvp_character_assets import CharacterAssets
from backend.nvp_retarget import RetargetCalibration
from backend.nvp_skinning import SkinnedPerformance
from backend.nvp_studio import Studio
from tests.test_skinning import make_fixture
from tests.test_character_assets import synthetic_glb, ROLES


MAP = {
    'left': {'hip':'leg_left','knee':'left_knee','ankle':'left_ankle','toe':'left_toe'},
    'right':{'hip':'leg_right','knee':'right_knee','ankle':'right_ankle','toe':'right_toe'},
}
ROLE_MAP={r:r for r in ROLES}
JOINTS=list(ROLES)+['left_knee','left_ankle','left_toe','right_knee','right_ankle','right_toe']
IDENTITY=[1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.]


def synthetic_anatomy_glb():
    """A GLB structural fixture; does NOT stand in for native Blender evidence."""
    original=synthetic_glb()
    length,typ=struct.unpack_from('<II',original,12)
    doc=json.loads(original[20:20+length].rstrip(b' \x00'))
    offset=20+length
    binlen,binkind=struct.unpack_from('<II',original,offset)
    binary=original[offset+8:offset+8+binlen]
    doc['skins'][0]['joints']=list(range(7))+list(range(8,14))
    del doc['skins'][0]['inverseBindMatrices']
    for name in JOINTS[7:]:
        doc['nodes'].append({'name':name})
    doc['nodes'][5]['children']=[8]
    doc['nodes'][8]['children']=[9]
    doc['nodes'][9]['children']=[10]
    doc['nodes'][6]['children']=[11]
    doc['nodes'][11]['children']=[12]
    doc['nodes'][12]['children']=[13]
    raw=json.dumps(doc,separators=(',',':')).encode()
    raw+=b' ' * (-len(raw)%4)
    pieces=(struct.pack('<II',len(raw),0x4e4f534a)+raw+
            struct.pack('<II',len(binary),0x004e4942)+binary)
    return b'glTF'+struct.pack('<II',2,12+len(pieces))+pieces


def observation():
    bones=[]
    for side, x in (('left',-.18),('right',.18)):
        for part,parent,z,y in [
            ('hip',None,1.0,0),('knee','hip',.55,0),
            ('ankle','knee',.11,0),('toe','ankle',.08,.14)
        ]:
            bones.append({'name':MAP[side][part],
                'parent':MAP[side][parent] if parent else None,
                'head_world_m':[x,y,z],
                'tail_world_m':[x,y,z+.03],
                'rest_matrix_world':IDENTITY,'rest_matrix_local':IDENTITY})
    return {'format':'nvp.legchain.observation.v1','asset_sha256':'a'*64,
            'armature_count':1,'skinned_mesh_count':1,
            'blender_version':'synthetic-fixture-not-native','bones':bones}


class AnatomicalGeometryTests(unittest.TestCase):
    def test_authoritative_roles_and_unique_distinct_eight_bones(self):
        self.assertEqual(validate_leg_mapping(MAP,ROLE_MAP,JOINTS),MAP)
        for bad in [
            {'left':MAP['left']}, {**MAP,'right':{**MAP['right'],'ankle':'left_ankle'}},
            {**MAP,'left':{**MAP['left'],'hip':'leg_right'}},
            {**MAP,'left':{**MAP['left'],'knee':'missing'}},
            {**MAP,'left':{**MAP['left'],'optional_extra':'unexpected'}}
        ]:
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                validate_leg_mapping(bad,ROLE_MAP,JOINTS)

    def test_native_report_analyzes_exact_rest_hierarchy(self):
        result=analyze_anatomy_snapshot(observation(),MAP,asset_sha256='a'*64,actor_id='actor')
        self.assertEqual(result['format'],'nvp.legchain.anatomy.v1')
        self.assertEqual(result['rest_lengths_m']['left']['upper_m'],.45)
        self.assertEqual(result['rest_lengths_m']['right']['lower_m'],.44)
        self.assertEqual(result['chains'],MAP)
        self.assertFalse(result['ik_authorized'])
        self.assertEqual(result['warnings'],[])

    def test_refuse_changed_source_duplicate_or_missing_bones(self):
        for change in ('bad_sha','missing_bone','duplicate_bone','wrong_rig_count','missing_skin'):
            report=observation()
            if change=='bad_sha':report['asset_sha256']='b'*64
            if change=='missing_bone':report['bones'].pop()
            if change=='duplicate_bone':report['bones'][-1]['name']=report['bones'][0]['name']
            if change=='wrong_rig_count':report['armature_count']=2
            if change=='missing_skin':report['skinned_mesh_count']=0
            with self.subTest(change=change),self.assertRaises(ValueError):
                analyze_anatomy_snapshot(report,MAP,asset_sha256='a'*64,actor_id='actor')

    def test_refuse_incorrect_parentage_short_segments_and_singular_matrix(self):
        for change in ('knee_parent','ankle_coincident','toe_coincident','singular','nonfinite'):
            report=observation()
            if change=='knee_parent':report['bones'][1]['parent']='right_knee'
            if change=='ankle_coincident':report['bones'][2]['head_world_m']=report['bones'][1]['head_world_m']
            if change=='toe_coincident':report['bones'][3]['head_world_m']=report['bones'][2]['head_world_m']
            if change=='singular':report['bones'][1]['rest_matrix_world']=[0.0]*16
            if change=='nonfinite':report['bones'][2]['head_world_m'][0]=float('nan')
            with self.subTest(change=change),self.assertRaises(ValueError):
                analyze_anatomy_snapshot(report,MAP,asset_sha256='a'*64,actor_id='actor')

    def test_unknown_crossing_marks_review_not_silent_side_inference(self):
        report=observation()
        for b in report['bones']:
            if b['name']=='right_ankle':b['head_world_m'][0]=-.40
            if b['name']=='right_toe':b['head_world_m'][0]=-.40
        outcome=analyze_anatomy_snapshot(report,MAP,asset_sha256='a'*64,actor_id='a')
        self.assertTrue(outcome['warnings'])

    def test_fixed_blender_probe_is_parseable_and_read_only(self):
        ast.parse(LEGCHAIN_PROBE_SCRIPT)
        self.assertIn('bone.matrix_local',LEGCHAIN_PROBE_SCRIPT)
        self.assertIn('hashlib.sha256',LEGCHAIN_PROBE_SCRIPT)
        self.assertNotIn('keyframe_insert(',LEGCHAIN_PROBE_SCRIPT)
        self.assertNotIn('bpy.ops.wm.save_as_mainfile',LEGCHAIN_PROBE_SCRIPT)


class LegChainApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.studio,self.pid,self.sid,self.actor=make_fixture(self.root)
        skin=SkinnedPerformance(self.studio)
        sk=skin.create(self.pid,self.sid)
        skin.approve(self.pid,self.sid,sk['revision'])
        char=CharacterAssets(self.studio)
        asset=char.register(self.pid,synthetic_anatomy_glb(),'creator_owned')
        c=char.create(self.pid,self.sid)
        c=char.bind(self.pid,self.sid,self.actor,asset['asset_id'],ROLE_MAP,c['revision'])
        char.approve(self.pid,self.sid,c['revision'])
        r=RetargetCalibration(self.studio)
        approved=r.create(self.pid,self.sid)
        r.approve(self.pid,self.sid,approved['revision'])
        self.service=LegChainIdentity(self.studio)

    def tearDown(self):self.tmp.cleanup()

    def test_draft_requires_authored_mapping_and_genuine_inspection(self):
        s=self.service.create(self.pid,self.sid)
        self.assertEqual(s['status'],'draft')
        with self.assertRaisesRegex(ValueError,'explicit authored'):
            self.service.inspect_native(self.pid,self.sid,self.root/'native')
        with self.assertRaisesRegex(RuntimeError,'Missing independent'):
            self.service.approve(self.pid,self.sid,s['revision'])
        s=self.service.configure(self.pid,self.sid,self.actor,MAP,s['revision'])
        self.assertEqual(s['actors'][0]['mapping'],MAP)
        with self.assertRaisesRegex(RuntimeError,'Missing independent'):
            self.service.approve(self.pid,self.sid,s['revision'])
        self.assertEqual(self.service.read(self.pid,self.sid)['inspected_actors'],[])

    def test_revision_isolation_and_blender_missing_blocks_instead_of_approving(self):
        s=self.service.create(self.pid,self.sid)
        s=self.service.configure(self.pid,self.sid,self.actor,MAP,s['revision'])
        with self.assertRaises(RuntimeError):
            self.service.configure(self.pid,self.sid,self.actor,MAP,0)
        outcome=self.service.inspect_native(self.pid,self.sid,self.root/'audit',executable='definitely-no-blender')
        self.assertEqual(outcome['status'],'blocked_no_blender')
        with self.assertRaises(RuntimeError):self.service.export(self.pid,self.sid)
        self.assertEqual(self.service.read(self.pid,self.sid)['revision'],1)
        recovered=LegChainIdentity(Studio(self.studio.db_path))
        self.assertEqual(recovered.read(self.pid,self.sid)['actors'],s['actors'])

    def test_other_project_and_stale_retarget_cannot_be_substituted(self):
        self.service.create(self.pid,self.sid)
        other=self.studio.create_project('Different film','')['id']
        with self.assertRaises(KeyError):self.service.read(other,self.sid)
        with self.assertRaises(KeyError):
            self.service.configure(self.pid,self.sid,'foreign actor',MAP,0)
        from backend.nvp_shot_sequence import ShotSequence
        seq=ShotSequence(self.studio)
        current=seq.read(self.pid,self.sid)
        seq.new_revision(self.pid,self.sid,current['revision'])
        with self.assertRaises(RuntimeError):self.service.export(self.pid,self.sid)

if __name__=='__main__':unittest.main()
