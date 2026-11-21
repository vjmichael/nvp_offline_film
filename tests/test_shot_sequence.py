"""NVP-PROD-05 director-approved shot timing, editable cut warnings, Blender proxy footage."""
from pathlib import Path
import json
import tempfile
import unittest

from backend.nvp_studio import Studio
from backend.nvp_production_scene import ProductionScene
from backend.nvp_world_state import WorldState
from backend.nvp_blocking_camera import BlockingCamera
from backend.nvp_shot_sequence import ShotSequence, follow_route, actor_xy_at, line_frames, animated_blender_script

SCRIPT='''INT. KITCHEN - NIGHT

MARA
Where is the key?

BOB
I don't know.
'''

class ShotSequenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Path(self.temp.name)/'film.sqlite'
        self.studio=Studio(self.db)
        self.pid=self.studio.create_project('Film','')['id']
        self.sid=self.studio.save_screenplay(self.pid,SCRIPT,0)['scenes'][0]['id']
        self.prod=ProductionScene(self.studio)
        for name in ('MARA','BOB'):
            self.prod.create_asset(self.pid,{'name':name,'category':'character','dimensions':[.40,.40,1.68]})
        p=self.prod.stage_scene(self.pid,self.sid,[10,8,3]);p=self.prod.solve_scene(self.pid,self.sid,p['plan_revision']);self.prod.approve_scene(self.pid,self.sid,p['plan_revision'])
        self.bc=BlockingCamera(self.studio)
        self.actors={a['name']:a for a in self.prod.export_manifest(self.pid,self.sid)['instances']}
        self.camera=self.bc.solve_shot(self.pid,self.sid,[self.actors['MARA']['instance_id']])
        self.lines=self.bc.dialogue(self.pid,self.sid)['dialogue']
        for line in self.lines:
            self.bc.set_dialogue_duration(self.pid,self.sid,line['id'],1.5)
        self.seq=ShotSequence(self.studio)
        self.seq.create(self.pid,self.sid)

    def tearDown(self):self.temp.cleanup()

    def add_shot(self,frames=120,camera_id=None,pattern='single'):
        before=self.seq.read(self.pid,self.sid)
        return self.seq.add_shot(self.pid,self.sid,camera_id or self.camera['id'],frames,pattern,before['revision'])

    def cues(self):
        self.seq.place_cue(self.pid,self.sid,self.lines[0]['id'],1,self.seq.read(self.pid,self.sid)['revision'])
        return self.seq.place_cue(self.pid,self.sid,self.lines[1]['id'],40,self.seq.read(self.pid,self.sid)['revision'])

    def approve(self):
        state=self.seq.read(self.pid,self.sid)
        assert not state['review']['errors'],state['review']
        if state['review']['warnings']:
            state=self.seq.acknowledge(self.pid,self.sid,[w['code'] for w in state['review']['warnings']],state['revision'])
        return self.seq.approve(self.pid,self.sid,state['revision'])

    def test_requires_explicit_approval_and_measured_dialogue(self):
        with self.assertRaises(RuntimeError):self.seq.export(self.pid,self.sid)
        self.add_shot();self.cues()
        self.assertEqual(self.approve()['status'],'approved')
        manifest=self.seq.export(self.pid,self.sid)
        self.assertEqual(manifest['take']['dialogue'][0]['duration_frames'],36)
        self.assertEqual(manifest['take']['shots'][0]['start_frame'],1)
        self.assertEqual(manifest['take']['shots'][0]['stop_frame'],121)

    def test_approval_requires_all_dialogue_not_just_a_camera(self):
        self.add_shot()
        with self.assertRaisesRegex(RuntimeError,'Resolve sequence errors'):
            self.seq.approve(self.pid,self.sid,self.seq.read(self.pid,self.sid)['revision'])
        self.assertEqual(len(self.seq.read(self.pid,self.sid)['review']['errors']),2)

    def test_dialogue_cannot_overrun_or_overlap(self):
        self.add_shot(60)
        with self.assertRaises(ValueError):
            self.seq.place_cue(self.pid,self.sid,self.lines[0]['id'],50,self.seq.read(self.pid,self.sid)['revision'])
        self.seq.place_cue(self.pid,self.sid,self.lines[0]['id'],1,self.seq.read(self.pid,self.sid)['revision'])
        self.seq.place_cue(self.pid,self.sid,self.lines[1]['id'],25,self.seq.read(self.pid,self.sid)['revision'])
        self.assertTrue(any('Concurrent dialogue' in e for e in self.seq.read(self.pid,self.sid)['review']['errors']))

    def test_shot_frames_are_contiguous_and_duration_is_exact(self):
        a=self.add_shot(32)
        b=self.add_shot(48)
        self.assertEqual(b['plan']['shots'][1]['start_frame'],33)
        self.assertEqual(b['review']['total_frames'],80)
        self.assertAlmostEqual(b['review']['duration_s'],80/24,places=5)
        self.assertEqual(b['plan']['shots'][1]['stop_frame'],81)

    def test_invalid_camera_id_and_frame_parameters(self):
        for frames in (0,-1,True,1.4):
            with self.assertRaises(ValueError):self.add_shot(frames)
        with self.assertRaises(ValueError):self.add_shot(10,'CM_unknown')
        with self.assertRaises(ValueError):self.add_shot(10,pattern='AI GENERATED 20 CAMERA MOVES')

    def test_cross_project_camera_and_sequence_isolation(self):
        other=self.studio.create_project('Other','')['id']
        with self.assertRaises(KeyError):ShotSequence(self.studio).read(other,self.sid)
        with self.assertRaises(KeyError):ShotSequence(self.studio).create(other,self.sid)

    def test_stale_on_world_change_cannot_export(self):
        self.add_shot();self.cues();self.approve()
        WorldState(self.studio).set_human(self.pid,self.sid,self.actors['MARA']['instance_id'],'visible',False,0)
        old=self.seq.read(self.pid,self.sid)
        self.assertTrue(old['stale'])
        with self.assertRaises(RuntimeError):self.seq.export(self.pid,self.sid)

    def test_stale_on_dialogue_retiming_and_new_camera(self):
        self.add_shot();self.cues();self.approve()
        self.bc.set_dialogue_duration(self.pid,self.sid,self.lines[0]['id'],2.0)
        self.assertTrue(self.seq.read(self.pid,self.sid)['stale'])
        other=ShotSequence(self.studio)
        with self.assertRaises(RuntimeError):other.export(self.pid,self.sid)

    def test_stale_on_new_blocking_path(self):
        self.add_shot();self.cues();self.approve()
        a=self.actors['MARA']
        self.bc.add_mark(self.pid,self.sid,a['instance_id'],[a['pose']['x']+.5,a['pose']['y']],start_s=0,end_s=2)
        self.assertTrue(self.seq.read(self.pid,self.sid)['stale'])

    def test_director_approval_and_fork_preserve_audit(self):
        self.add_shot();self.cues();original=self.approve()
        with self.assertRaises(RuntimeError):self.add_shot()
        revised=self.seq.new_revision(self.pid,self.sid,original['revision'])
        self.assertEqual(revised['status'],'draft')
        self.assertEqual(len(self.seq.history(self.pid,self.sid)),7)
        self.assertEqual(self.seq.history(self.pid,self.sid)[-1]['action'],'begin_revision')

    def test_revision_conflicts_and_reopen(self):
        self.add_shot()
        with self.assertRaisesRegex(RuntimeError,'changed elsewhere'):
            self.seq.add_shot(self.pid,self.sid,self.camera['id'],10,'single',0)
        state=ShotSequence(Studio(self.db)).read(self.pid,self.sid)
        self.assertEqual(len(state['plan']['shots']),1)

    def test_missing_measured_duration_is_rejected(self):
        self.add_shot()
        self.bc.set_dialogue_duration(self.pid,self.sid,self.lines[1]['id'],.2)
        with self.assertRaises(RuntimeError):self.seq.place_cue(self.pid,self.sid,self.lines[0]['id'],5,1)
        self.assertEqual(line_frames(1.5),36)
        for value in (None,False,float('nan'),-1):
            with self.assertRaises(ValueError):line_frames(value)

    def test_director_must_acknowledge_cut_warnings(self):
        self.add_shot(60)
        self.add_shot(60)
        self.cues()
        review=self.seq.read(self.pid,self.sid)['review']
        self.assertTrue(any(w['code'].startswith('near_identical_cut:') for w in review['warnings']))
        with self.assertRaises(RuntimeError):self.seq.approve(self.pid,self.sid,self.seq.read(self.pid,self.sid)['revision'])
        with self.assertRaises(ValueError):self.seq.acknowledge(self.pid,self.sid,['invented_warning'],self.seq.read(self.pid,self.sid)['revision'])
        self.approve()

    def test_blender_script_is_data_only_and_has_cut_markers(self):
        self.add_shot(120);self.cues();self.approve()
        source=self.seq.blender_script(self.pid,self.sid)
        compile(source,'<nvp blender export>','exec')
        self.assertIn('timeline_markers.new',source)
        self.assertIn('sc.render.fps',source)
        self.assertIn('keyframe_insert',source)
        self.assertIn('nvp_take_sha',source)

    def test_distance_parametrization_follows_right_angle_turn(self):
        path={'points':[[0,0],[2,0],[2,2]]}
        self.assertEqual(follow_route(path,.25),[1.,0.])
        self.assertEqual(follow_route(path,.75),[2.,1.])
        self.assertEqual(follow_route(path,1),[2.,2.])
        self.assertEqual(actor_xy_at({'pose':{'x':0,'y':0}},[{'id':'a','mark':{'start_s':2,'end_s':4,'target_xy_m':[2,2]},'path':path}],3),[2.,0.])

    def test_remove_shot_and_cue_then_reset_retain_history(self):
        self.add_shot(40)
        self.add_shot(40)
        self.seq.place_cue(self.pid,self.sid,self.lines[0]['id'],1,self.seq.read(self.pid,self.sid)['revision'])
        self.seq.place_cue(self.pid,self.sid,self.lines[1]['id'],44,self.seq.read(self.pid,self.sid)['revision'])
        old=self.seq.read(self.pid,self.sid)
        after=self.seq.remove_last_shot(self.pid,self.sid,old['revision'])
        self.assertEqual(len(after['plan']['shots']),1)
        self.assertEqual(len(after['plan']['cues']),1)
        cleared=self.seq.clear_cue(self.pid,self.sid,self.lines[0]['id'],after['revision'])
        self.assertFalse(cleared['plan']['cues'])
        reset=self.seq.reset_draft(self.pid,self.sid,cleared['revision'])
        self.assertFalse(reset['plan']['shots'])
        self.assertEqual(self.seq.history(self.pid,self.sid)[-1]['action'],'reset_draft')

    def test_approved_edit_requires_explicit_fork_then_reset(self):
        self.add_shot();self.cues();old=self.approve()
        with self.assertRaises(RuntimeError):self.seq.reset_draft(self.pid,self.sid,old['revision'])
        draft=self.seq.new_revision(self.pid,self.sid,old['revision'])
        empty=self.seq.reset_draft(self.pid,self.sid,draft['revision'])
        self.assertEqual(empty['status'],'draft')
        self.assertFalse(empty['plan']['shots'])
        self.assertEqual(self.seq.history(self.pid,self.sid)[-2]['action'],'begin_revision')

    def test_approval_proof_invalid_after_external_db_tamper(self):
        self.add_shot();self.cues();self.approve()
        with self.studio._connection() as db:
            row=db.execute('SELECT sequence_json FROM prod_shot_sequences WHERE project_id=? AND scene_id=?',
                           (self.pid,self.sid)).fetchone()
            payload=json.loads(row['sequence_json']);payload['shots'][0]['pattern']='tracking'
            db.execute('UPDATE prod_shot_sequences SET sequence_json=? WHERE project_id=? AND scene_id=?',
                       (json.dumps(payload),self.pid,self.sid))
        self.assertTrue(self.seq.read(self.pid,self.sid)['stale'])
        with self.assertRaises(RuntimeError):self.seq.export(self.pid,self.sid)

if __name__=='__main__':unittest.main()
