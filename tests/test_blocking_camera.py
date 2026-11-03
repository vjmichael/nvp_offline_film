"""PROD-04: actor paths, dialogue identities, measured camera placements and cut rules."""
import math
from pathlib import Path
import tempfile
import unittest

from backend.nvp_studio import Studio
from backend.nvp_production_scene import ProductionScene
from backend.nvp_world_state import WorldState
from backend.nvp_blocking_camera import BlockingCamera,solve_camera,route_actor,project,check_180_axis

SCRIPT='''INT. ROOM - NIGHT

MARA
Where is the key?

BOB
I do not know.
'''

class BlockingCameraTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=Path(self.temp.name)/'film.sqlite'
        self.studio=Studio(self.db)
        self.pid=self.studio.create_project('Movie','')['id']
        self.sid=self.studio.save_screenplay(self.pid,SCRIPT,0)['scenes'][0]['id']
        self.prod=ProductionScene(self.studio)
        for name in ('MARA','BOB'):
            self.prod.create_asset(self.pid,{'name':name,'category':'character','dimensions':[.42,.42,1.68]})
        self.plan=self.prod.stage_scene(self.pid,self.sid,[10,8,3])
        self.plan=self.prod.solve_scene(self.pid,self.sid,self.plan['plan_revision'])
        self.plan=self.prod.approve_scene(self.pid,self.sid,self.plan['plan_revision'])
        self.stage=self.prod.export_manifest(self.pid,self.sid)
        self.actors={i['name']:i['instance_id'] for i in self.stage['instances']}
        self.bc=BlockingCamera(self.studio)

    def tearDown(self):self.temp.cleanup()

    def test_dialogue_ids_speaker_and_unresolved_status(self):
        result=self.bc.dialogue(self.pid,self.sid)
        self.assertEqual(len(result['dialogue']),2)
        self.assertEqual(result['unresolved_speakers'],[])
        self.assertEqual(result['dialogue'][0]['actor_instance_id'],self.actors['MARA'])
        self.assertEqual(result['dialogue'][1]['speaker_name'],'BOB')
        self.assertIsNone(result['dialogue'][0]['duration_s'])
        self.assertEqual(result['dialogue'][0]['timing_origin'],'requires_audio_or_director')

    def test_dialogue_duration_only_explicitly_measured(self):
        line=self.bc.dialogue(self.pid,self.sid)['dialogue'][0]
        changed=self.bc.set_dialogue_duration(self.pid,self.sid,line['id'],2.75,'director_measured')
        self.assertEqual(changed['dialogue'][0]['duration_s'],2.75)
        self.assertEqual(changed['dialogue'][0]['timing_origin'],'director_measured')
        reopened=BlockingCamera(Studio(self.db)).dialogue(self.pid,self.sid)
        self.assertEqual(reopened['dialogue'][0]['duration_s'],2.75)

    def test_invalid_timing_is_refused(self):
        line=self.bc.dialogue(self.pid,self.sid)['dialogue'][0]
        for v in (-1,float('nan'),True,500):
            with self.assertRaises(ValueError):
                self.bc.set_dialogue_duration(self.pid,self.sid,line['id'],v)
        with self.assertRaises(KeyError):
            self.bc.set_dialogue_duration(self.pid,self.sid,'no_line',3)

    def test_dialogue_listener_is_explicit_not_assumed(self):
        line=self.bc.dialogue(self.pid,self.sid)['dialogue'][0]
        self.assertEqual(line['listener_instance_ids'],[])
        changed=self.bc.set_listeners(self.pid,self.sid,line['id'],[self.actors['BOB']])
        self.assertEqual(changed['dialogue'][0]['listener_instance_ids'],[self.actors['BOB']])
        with self.assertRaises(ValueError):
            self.bc.set_listeners(self.pid,self.sid,line['id'],[self.actors['MARA']])
        with self.assertRaises(ValueError):
            self.bc.set_listeners(self.pid,self.sid,line['id'],['external'])

    def test_static_actor_reachable_path(self):
        actor=next(i for i in self.stage['instances'] if i['name']=='MARA')
        start=actor['pose']['x'],actor['pose']['y']
        goal=(start[0]+.5,start[1])
        mark=self.bc.add_mark(self.pid,self.sid,self.actors['MARA'],goal,start_s=0,end_s=4)
        self.assertEqual(mark['path']['points'][0],list(start))
        self.assertEqual(mark['path']['points'][-1],list(goal))
        self.assertGreater(mark['path']['distance_m'],0)
        self.assertEqual(len(self.bc.marks(self.pid,self.sid)),1)

    def test_blocking_spatial_collision_rejection(self):
        other=next(i for i in self.stage['instances'] if i['name']=='BOB')
        with self.assertRaises(ValueError):
            self.bc.add_mark(self.pid,self.sid,self.actors['MARA'],
                             [other['pose']['x'],other['pose']['y']])

    def test_second_mark_starts_from_first_and_times_cannot_overlap(self):
        actor=next(i for i in self.stage['instances'] if i['name']=='MARA')
        start=actor['pose']
        g1=[start['x']+.5,start['y']]
        first=self.bc.add_mark(self.pid,self.sid,self.actors['MARA'],g1,start_s=1,end_s=3)
        second=self.bc.add_mark(self.pid,self.sid,self.actors['MARA'],[start['x']+1,start['y']],
                                start_s=3,end_s=7)
        self.assertEqual(second['path']['points'][0],g1)
        with self.assertRaisesRegex(ValueError,'overlap'):
            self.bc.add_mark(self.pid,self.sid,self.actors['MARA'],[start['x']+.5,start['y']],
                             start_s=5,end_s=8)

    def test_move_cannot_teleport_in_impossible_time(self):
        actor=next(i for i in self.stage['instances'] if i['name']=='MARA')
        with self.assertRaisesRegex(ValueError,'unreachable within'):
            self.bc.add_mark(self.pid,self.sid,self.actors['MARA'],
                [actor['pose']['x']+.5,actor['pose']['y']],start_s=0,end_s=.01)

    def test_stand_cannot_move_actor(self):
        actor=next(i for i in self.stage['instances'] if i['name']=='MARA')
        with self.assertRaisesRegex(ValueError,'stationary mark'):
            self.bc.add_mark(self.pid,self.sid,self.actors['MARA'],
                [actor['pose']['x']+.5,actor['pose']['y']],action='stand')

    def test_camera_solution_deterministic_for_same_staging(self):
        a=self.bc.solve_shot(self.pid,self.sid,[self.actors['MARA']])['solution']
        b=self.bc.solve_shot(self.pid,self.sid,[self.actors['MARA']])['solution']
        self.assertEqual(a,b)

    def test_nearby_anchor_relation(self):
        # Add named anchor on actor's *own* asset then reference another character's anchor.
        actor=next(i for i in self.stage['instances'] if i['name']=='MARA')
        other=next(i for i in self.stage['instances'] if i['name']=='BOB')
        with self.assertRaisesRegex(ValueError,'anchor'):
            self.bc.add_mark(self.pid,self.sid,self.actors['MARA'],
                             [actor['pose']['x']+.5,actor['pose']['y']],
                             target_instance_id=self.actors['BOB'],anchor_name='missing')

    def test_camera_single_subject_reports_subpercent_residual(self):
        solution=self.bc.solve_shot(self.pid,self.sid,[self.actors['MARA']])['solution']
        self.assertLess(solution['max_residual'],.015)
        self.assertTrue(solution['fits_all_subjects'])
        self.assertGreater(solution['candidates_evaluated'],0)
        self.assertEqual(len(BlockingCamera(Studio(self.db)).cameras(self.pid,self.sid)),1)

    def test_camera_multiple_subjects_reports_actual_error(self):
        solution=self.bc.solve_shot(self.pid,self.sid,[self.actors['MARA'],self.actors['BOB']],
                                    desired_positions=[[.3,.52],[.7,.52]])['solution']
        self.assertEqual(len(solution['residuals']),2)
        self.assertAlmostEqual(max(solution['residuals']),solution['max_residual'])
        self.assertGreaterEqual(solution['max_residual'],0)

    def test_camera_invalid_parameters_refused(self):
        with self.assertRaises(ValueError):self.bc.solve_shot(self.pid,self.sid,[self.actors['MARA']],lens_mm=float('nan'))
        with self.assertRaises(ValueError):self.bc.solve_shot(self.pid,self.sid,[self.actors['MARA']],shot_size='INVALID')
        with self.assertRaises(KeyError):self.bc.solve_shot(self.pid,self.sid,['unknown'])
        with self.assertRaises(ValueError):self.bc.solve_shot(self.pid,self.sid,[self.actors['MARA'],self.actors['MARA']])

    def test_pinhole_projection_validates_viewpoint(self):
        val=project([0,2,1],[0,0,1],[0,1,1],50)
        self.assertAlmostEqual(val[0],.5)
        self.assertAlmostEqual(val[1],.5)
        self.assertIsNone(project([0,-2,1],[0,0,1],[0,1,1],50))

    def test_cut_crossing_180_axis_detected(self):
        self.assertTrue(check_180_axis([1,1],[5,1],[3,2],[3,0])['crossed'])
        self.assertFalse(check_180_axis([1,1],[5,1],[3,2],[4,2])['crossed'])
        self.assertTrue(check_180_axis([1,1],[5,1],[3,1],[4,2])['ambiguous_on_line'])

    def test_camera_and_marks_become_stale_after_world_change(self):
        actor=next(i for i in self.stage['instances'] if i['name']=='MARA')
        self.bc.add_mark(self.pid,self.sid,self.actors['MARA'],[actor['pose']['x']+.5,actor['pose']['y']])
        self.bc.solve_shot(self.pid,self.sid,[self.actors['MARA']])
        WorldState(self.studio).set_human(self.pid,self.sid,self.actors['MARA'],'visible',False,0)
        self.assertTrue(self.bc.marks(self.pid,self.sid)[0]['stale'])
        self.assertTrue(self.bc.cameras(self.pid,self.sid)[0]['stale'])

    def test_scene_project_isolation(self):
        other=self.studio.create_project('Other','')['id']
        with self.assertRaises(KeyError):self.bc.cameras(other,self.sid)
        with self.assertRaises(KeyError):self.bc.marks(other,self.sid)

    def test_script_change_invalidates_old_blocking(self):
        self.studio.save_screenplay(self.pid,SCRIPT.replace('Where is the key','Where is the book'),1)
        with self.assertRaisesRegex(RuntimeError,'changed'):
            self.bc.dialogue(self.pid,self.sid)

    def test_character_as_non_subject_cannot_be_claimed_as_in_frame(self):
        with self.assertRaises(ValueError):
            self.bc.solve_shot(self.pid,self.sid,[self.actors['MARA']],desired_positions=[[1.1,.5]])

if __name__=='__main__':unittest.main()
