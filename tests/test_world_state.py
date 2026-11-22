"""PROD-02: creator-authored per-attribute world edits and AI proposal isolation."""
import tempfile
import unittest
from pathlib import Path

from backend.nvp_studio import Studio
from backend.nvp_production_scene import ProductionScene
from backend.nvp_world_state import WorldState

SCREEN='INT. ROOM - DAY\n\nMARA\nI am here.\n'

class WorldTests(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory(); self.path=Path(self.dir.name)/'db.sqlite'
        self.studio=Studio(self.path)
        self.pid=self.studio.create_project('Test','') ['id']
        scene=self.studio.save_screenplay(self.pid,SCREEN,0)
        self.sid=scene['scenes'][0]['id']
        self.prod=ProductionScene(self.studio)
        asset=self.prod.create_asset(self.pid,{'name':'Crate','category':'prop','dimensions':[.4,.4,.4]})
        plan=self.prod.stage_scene(self.pid,self.sid,[8,6,3]);plan=self.prod.add_instance(self.pid,self.sid,asset['asset_id'],'crate',plan['plan_revision'])
        plan=self.prod.solve_scene(self.pid,self.sid,plan['plan_revision']);self.prod.approve_scene(self.pid,self.sid,plan['plan_revision'])
        self.ws=WorldState(self.studio)
        self.base=self.ws.read(self.pid,self.sid)
        self.x=self.base['manifest']['instances'][0]['pose']['x']

    def tearDown(self): self.dir.cleanup()

    def test_initial_world_has_approved_base_and_empty_overlay(self):
        self.assertEqual(self.base['revision'],0)
        self.assertEqual(self.base['fields'],{})
        self.assertFalse(self.base['stale'])

    def test_human_ownership_and_lock_persist_across_restarts(self):
        edited=self.ws.set_human(self.pid,self.sid,'crate','visible',False,0)
        self.assertEqual(edited['revision'],1)
        self.assertEqual(edited['fields']['crate']['visible']['author'],'human')
        self.assertTrue(edited['fields']['crate']['visible']['locked'])
        self.assertFalse(WorldState(Studio(self.path)).export_manifest(self.pid,self.sid)['instances'][0]['visible'])
        self.assertEqual(self.prod.export_manifest(self.pid,self.sid)['instances'][0].get('visible'),None)

    def test_concurrent_edit_revision_refused(self):
        self.ws.set_human(self.pid,self.sid,'crate','visible',False,0)
        with self.assertRaisesRegex(RuntimeError,'changed elsewhere'):
            self.ws.set_human(self.pid,self.sid,'crate','visible',True,0)

    def test_ai_proposal_does_not_change_effective_scene(self):
        proposal=self.ws.propose_ai(self.pid,self.sid,'crate','visible',False,0)
        self.assertEqual(proposal['status'],'proposed')
        self.assertNotIn('visible',self.ws.export_manifest(self.pid,self.sid)['instances'][0])
        self.ws.decide(self.pid,self.sid,proposal['proposal_id'],'reject',0)
        self.assertNotIn('visible',self.ws.export_manifest(self.pid,self.sid)['instances'][0])

    def test_ai_accepted_with_explicit_decision_and_undo(self):
        proposal=self.ws.propose_ai(self.pid,self.sid,'crate','visible',False,0)
        accepted=self.ws.decide(self.pid,self.sid,proposal['proposal_id'],'accept',0)
        self.assertEqual(accepted['fields']['crate']['visible']['author'],'accepted_ai')
        self.assertEqual(accepted['revision'],1)
        undone=self.ws.undo(self.pid,self.sid,1)
        self.assertEqual(undone['fields'],{})
        self.assertEqual(undone['revision'],2)
        self.assertEqual(len(self.ws.journal(self.pid,self.sid)),2)

    def test_ai_cannot_override_locked_human(self):
        self.ws.set_human(self.pid,self.sid,'crate','visible',False,0)
        p=self.ws.propose_ai(self.pid,self.sid,'crate','visible',True,1)
        with self.assertRaisesRegex(RuntimeError,'Human-locked'):
            self.ws.decide(self.pid,self.sid,p['proposal_id'],'accept',1)
        self.assertFalse(self.ws.read(self.pid,self.sid)['manifest']['instances'][0]['visible'])
        self.ws.set_lock(self.pid,self.sid,'crate','visible',False,1)
        # Previously proposed value is stale after human unlock, so it must be re-proposed.
        with self.assertRaisesRegex(RuntimeError,'outdated'):
            self.ws.decide(self.pid,self.sid,p['proposal_id'],'accept',2)
        self.assertEqual(self.ws.propose_ai(self.pid,self.sid,'crate','visible',True,2)['status'],'proposed')

    def test_bad_human_edit_cannot_invalidate_layout(self):
        with self.assertRaises(ValueError):
            self.ws.set_human(self.pid,self.sid,'crate','pose.x',-10,0)
        self.assertEqual(self.ws.read(self.pid,self.sid)['revision'],0)

    def test_pose_edits_keep_base_unchanged_and_pass_validator(self):
        # The instance is small enough for a simple cardinal rotation.
        edited=self.ws.set_human(self.pid,self.sid,'crate','pose.rotation',90,0)
        self.assertEqual(edited['manifest']['instances'][0]['pose']['rotation'],90)
        self.assertEqual(self.prod.export_manifest(self.pid,self.sid)['instances'][0]['pose']['rotation'],0)
        self.assertIn('NVP_', self.ws.export_blender_script(self.pid,self.sid))

    def test_wrong_types_and_nonfinite_values_rejected(self):
        for v in (True,float('nan'),float('inf'),1e20):
            with self.assertRaises(ValueError):
                self.ws.set_human(self.pid,self.sid,'crate','pose.x',v,0)
        with self.assertRaises(ValueError):
            self.ws.set_human(self.pid,self.sid,'crate','pose.rotation',45,0)
        with self.assertRaises(ValueError):
            self.ws.set_human(self.pid,self.sid,'crate','dangerous.script','x',0)

    def test_project_isolation_and_unknown_instance(self):
        other=self.studio.create_project('Other','')['id']
        with self.assertRaises(KeyError):
            self.ws.read(other,self.sid)
        with self.assertRaises(KeyError):
            self.ws.set_human(self.pid,self.sid,'unknown','visible',False,0)

    def test_explicit_rebase_retains_compatible_human_edit(self):
        self.ws.set_human(self.pid,self.sid,'crate','visible',False,0)
        plan=self.prod.get_plan(self.pid,self.sid)
        plan=self.prod.resync_scene(self.pid,self.sid,plan['plan_revision'])
        plan=self.prod.solve_scene(self.pid,self.sid,plan['plan_revision'])
        plan=self.prod.approve_scene(self.pid,self.sid,plan['plan_revision'])
        self.assertTrue(self.ws.read(self.pid,self.sid)['stale'])
        with self.assertRaisesRegex(RuntimeError,'rebase'):
            self.ws.export_manifest(self.pid,self.sid)
        new=self.ws.rebase(self.pid,self.sid,1)
        self.assertFalse(new['stale'])
        self.assertFalse(new['manifest']['instances'][0]['visible'])

    def test_no_rebase_without_matching_instance(self):
        self.ws.set_human(self.pid,self.sid,'crate','visible',False,0)
        plan=self.prod.get_plan(self.pid,self.sid)
        plan=self.prod.resync_scene(self.pid,self.sid,plan['plan_revision'])
        # Remove the instance directly to simulate an approved fresh stage, with valid digest recomputation.
        # A missing field target causes explicit failure in the inheritance check.
        from backend.nvp_world_state import WorldState
        manifest=self.prod.export_manifest if False else None
        with self.studio._connection() as db:
            db.execute('UPDATE prod_plans SET instances_json=?,approval_state=? WHERE project_id=? AND scene_id=?',('[]','proposed',self.pid,self.sid))
        plan=self.prod.get_plan(self.pid,self.sid)
        plan=self.prod.solve_scene(self.pid,self.sid,plan['plan_revision'])
        self.prod.approve_scene(self.pid,self.sid,plan['plan_revision'])
        with self.assertRaisesRegex(RuntimeError,'no longer present'):
            self.ws.rebase(self.pid,self.sid,1)

if __name__=='__main__': unittest.main()
