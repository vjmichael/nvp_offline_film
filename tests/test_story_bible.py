"""NVP-WRITE-03: persistent, human-reviewed story bible / scene impact tests."""
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.nvp_studio import Studio
from backend.nvp_story_bible import StoryBible
from backend import nvp_api

SCRIPT = """INT. HOME - NIGHT

MARA
I hid the key.

EXT. ROAD - DAY

MARA
It is gone.
"""


class BibleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'nvp.sqlite3'
        self.studio = Studio(self.path)
        self.bible = StoryBible(self.studio)
        self.project = self.studio.create_project('Last Message', 'Mara returns home')
        self.pid = self.project['id']

    def tearDown(self):
        self.temp.cleanup()

    def character(self):
        return self.bible.create_entity(self.pid, 'character', 'Mara', 'Former paramedic')

    def propose_and_approve(self, entity, key='eye_color', value='brown', scope='global'):
        proposed = self.bible.propose_fact(self.pid, entity['id'], key, value, scope)
        refreshed = self.bible.get_entity(self.pid, entity['id'])
        return self.bible.decide_fact(self.pid, proposed['id'], 'accept', refreshed['revision'])

    def test_entities_have_stable_identity_across_rename_and_restart(self):
        p = self.character()
        renamed = self.bible.rename_entity(self.pid, p['id'], 'Mara Wells', p['revision'])
        self.assertEqual(renamed['id'], p['id'])
        self.assertEqual(renamed['aliases'], ['Mara'])
        reopened = StoryBible(Studio(self.path))
        self.assertEqual(reopened.get_entity(self.pid, p['id'])['name'], 'Mara Wells')
        self.assertEqual(reopened.list_entities(self.pid)[0]['revision'], 1)

    def test_character_prop_location_and_event_are_separate(self):
        for k in ('character','prop','location','event'):
            self.bible.create_entity(self.pid,k,'The Key')
        self.assertEqual(len(self.bible.list_entities(self.pid)),4)
        with self.assertRaisesRegex(RuntimeError,'already belongs'):
            self.bible.create_entity(self.pid,'prop','the key')

    def test_alias_collision_and_optimistic_concurrency(self):
        a = self.character()
        self.bible.add_alias(self.pid,a['id'],'Auntie',a['revision'])
        b = self.bible.create_entity(self.pid,'character','Janice')
        with self.assertRaisesRegex(RuntimeError,'already belongs'):
            self.bible.add_alias(self.pid,b['id'],'AUNTIE',b['revision'])
        with self.assertRaisesRegex(RuntimeError,'changed'):
            self.bible.rename_entity(self.pid,a['id'],'Mara Two',a['revision'])

    def test_facts_proposed_not_canon_and_approval_explicit(self):
        entity=self.character()
        f=self.bible.propose_fact(self.pid,entity['id'],'eye_color','brown',origin='ai_proposal')
        self.assertEqual(f['status'],'proposed')
        self.assertEqual([x for x in self.bible.get_entity(self.pid,entity['id'])['facts'] if x['status']=='accepted'],[])
        with self.assertRaisesRegex(RuntimeError,'changed'):
            self.bible.decide_fact(self.pid,f['id'],'accept',entity['revision'])
        accepted=self.bible.decide_fact(self.pid,f['id'],'accept',entity['revision']+1)
        self.assertEqual(accepted['status'],'accepted')
        self.assertEqual(self.studio.get_project(self.pid)['screenplay'],'')
        with self.assertRaisesRegex(RuntimeError,'already reviewed'):
            self.bible.decide_fact(self.pid,f['id'],'accept',entity['revision']+2)

    def test_conflict_requires_explicit_replacement_and_preserves_history(self):
        e=self.character()
        old=self.propose_and_approve(e,value='brown')
        new=self.bible.propose_fact(self.pid,e['id'],'eye_color','green')
        self.assertTrue(any(i['type']=='proposed_fact_conflict' for i in self.bible.report(self.pid)['issues']))
        refreshed=self.bible.get_entity(self.pid,e['id'])
        with self.assertRaisesRegex(RuntimeError,'explicitly choose'):
            self.bible.decide_fact(self.pid,new['id'],'accept',refreshed['revision'])
        accepted=self.bible.decide_fact(self.pid,new['id'],'accept',refreshed['revision'],old['id'])
        self.assertEqual(accepted['status'],'accepted')
        self.assertEqual(self.bible.get_fact(self.pid,old['id'])['status'],'superseded')
        self.assertEqual(len([x for x in self.bible.get_entity(self.pid,e['id'])['facts'] if x['status']=='accepted']),1)
        self.assertFalse(any(i['type']=='proposed_fact_conflict' for i in self.bible.report(self.pid)['issues']))
        changes=self.bible.report(self.pid)['changes']
        self.assertEqual(changes[-1]['old_fact_id'],old['id'])
        self.assertEqual(changes[-1]['new_fact_id'],new['id'])

    def test_timeline_scopes_do_not_generate_false_conflicts(self):
        e=self.character()
        self.propose_and_approve(e,'whereabouts','hospital','before_crash')
        self.propose_and_approve(e,'whereabouts','warehouse','after_crash')
        self.assertFalse(any(i['type']=='proposed_fact_conflict' for i in self.bible.report(self.pid)['issues']))

    def test_rejected_fact_cannot_replace_approved_fact(self):
        e=self.character()
        old=self.propose_and_approve(e,'vehicle','red van')
        new=self.bible.propose_fact(self.pid,e['id'],'vehicle','blue car')
        rev=self.bible.get_entity(self.pid,e['id'])['revision']
        with self.assertRaises(ValueError):
            self.bible.decide_fact(self.pid,new['id'],'reject',rev,old['id'])
        self.bible.decide_fact(self.pid,new['id'],'reject',rev)
        self.assertEqual(self.bible.get_fact(self.pid,old['id'])['status'],'accepted')
        self.assertEqual(self.bible.get_fact(self.pid,new['id'])['status'],'rejected')

    def test_manual_scene_link_survives_edit_and_flags_changed_scene(self):
        p=self.studio.save_screenplay(self.pid,SCRIPT,0)
        sc=p['scenes'][0]
        e=self.character()
        self.bible.link_scene(self.pid,e['id'],sc['id'],e['revision'],'Mara has the key')
        self.assertFalse(any(x['type'].startswith('scene_') for x in self.bible.report(self.pid)['issues']))
        self.studio.save_screenplay(self.pid,SCRIPT.replace('I hid the key.','The key is missing.'),1)
        issues=[x for x in self.bible.report(self.pid)['issues'] if x['type']=='scene_changed']
        self.assertEqual(len(issues),1)
        self.assertEqual(issues[0]['scene_id'],sc['id'])
        self.assertEqual(issues[0]['entity_id'],e['id'])
        self.bible.link_scene(self.pid,e['id'],sc['id'],self.bible.get_entity(self.pid,e['id'])['revision'],'Reviewed new action')
        self.assertFalse(any(x['type']=='scene_changed' for x in self.bible.report(self.pid)['issues']))

    def test_removed_scene_warns_and_preserves_archived_approved_shots(self):
        p=self.studio.save_screenplay(self.pid,SCRIPT,0)
        sc=p['scenes'][0]
        self.studio.plan_scene(self.pid,sc['id'])
        self.studio.edit_shot(self.pid,sc['id'],'S01',framing='wide',subject='MARA',intent='Show distance',notes='Director approved',approved=True)
        e=self.character()
        self.bible.link_scene(self.pid,e['id'],sc['id'],e['revision'])
        self.studio.save_screenplay(self.pid,'EXT. PLAZA - DAY\n\nSilence.',1)
        impact=[i for i in self.bible.report(self.pid)['issues'] if i['type']=='scene_removed']
        self.assertEqual(len(impact),1)
        self.assertIn('S01',impact[0]['shot_ids'])
        self.assertGreater(self.studio.get_project(self.pid)['archived_shots'],0)

    def test_fact_change_exposes_linked_scene_and_shots_then_can_be_acknowledged(self):
        p=self.studio.save_screenplay(self.pid,SCRIPT,0)
        scene=p['scenes'][0]
        self.studio.plan_scene(self.pid,scene['id'])
        e=self.character()
        self.bible.link_scene(self.pid,e['id'],scene['id'],e['revision'])
        old=self.propose_and_approve(e,'coat','blue')
        new=self.bible.propose_fact(self.pid,e['id'],'coat','red')
        self.bible.decide_fact(self.pid,new['id'],'accept',self.bible.get_entity(self.pid,e['id'])['revision'],old['id'])
        report=self.bible.report(self.pid)
        impacts=[x for x in report['issues'] if x['type']=='canon_change_impact']
        self.assertTrue(impacts)
        self.assertEqual(impacts[-1]['old_fact_id'],old['id'])
        self.assertEqual(impacts[-1]['affected_scenes'][0]['scene_id'],scene['id'])
        self.assertIn('S01',impacts[-1]['affected_scenes'][0]['shot_ids'])
        self.bible.acknowledge_change(self.pid,impacts[-1]['change_id'],report['screenplay_revision'])
        self.assertNotIn(impacts[-1]['change_id'],[x.get('change_id') for x in self.bible.report(self.pid)['issues']])
        self.assertEqual(len(self.bible.report(self.pid)['changes']),2)

    def test_stale_screenplay_revision_refuses_acknowledgment(self):
        e=self.character()
        self.propose_and_approve(e)
        change=self.bible.report(self.pid)['changes'][0]
        self.studio.save_screenplay(self.pid,SCRIPT,0)
        with self.assertRaisesRegex(RuntimeError,'Screenplay changed'):
            self.bible.acknowledge_change(self.pid,change['id'],0)

    def test_scene_links_require_actual_scene(self):
        e=self.character()
        with self.assertRaises(KeyError):
            self.bible.link_scene(self.pid,e['id'],'SC_forged',e['revision'])
        self.assertEqual(self.bible.get_entity(self.pid,e['id'])['scene_links'],[])

    def test_project_isolation_and_nonexistent_project(self):
        e=self.character()
        other=self.studio.create_project('Other','Other idea')
        with self.assertRaises(KeyError):
            self.bible.get_entity(other['id'],e['id'])
        with self.assertRaises(KeyError):
            self.bible.propose_fact(other['id'],e['id'],'color','blue')
        with self.assertRaises(KeyError):
            self.bible.list_entities('not-a-film')
        self.assertEqual(self.bible.list_entities(other['id']),[])

    def test_malformed_inputs_fail_closed(self):
        e=self.character()
        for bad in ('Person Name','..bad','bad/thing',''):
            with self.assertRaises(ValueError):
                self.bible.propose_fact(self.pid,e['id'],bad,'value')
        with self.assertRaises(ValueError):
            self.bible.propose_fact(self.pid,e['id'],'color','')
        with self.assertRaises(ValueError):
            self.bible.propose_fact(self.pid,e['id'],'color','blue',scope='scene/../bad')
        with self.assertRaises(ValueError):
            self.bible.create_entity(self.pid,'alien','Bad')
        with self.assertRaises(RuntimeError):
            self.bible.rename_entity(self.pid,e['id'],'Another Name',999)

    def test_existing_legacy_story_bible_is_unchanged(self):
        # Do not claim parser-derived names are human-approved facts.
        self.studio.save_screenplay(self.pid,SCRIPT,0)
        self.assertIn('MARA',self.studio.get_project(self.pid)['bible']['characters'])
        self.assertEqual(self.bible.list_entities(self.pid),[])


if __name__ == '__main__':
    unittest.main()

class BibleAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.studio=Studio(Path(self.tmp.name)/'film.db')
        self.prj=self.studio.create_project('API Film','A short drama')
        self.old=nvp_api.studio
        nvp_api.studio=self.studio
        self.api=TestClient(nvp_api.app)
        self.root=f'/api/projects/{self.prj["id"]}/story-bible'

    def tearDown(self):
        nvp_api.studio=self.old
        self.api.close()
        self.tmp.cleanup()

    def test_create_fact_review_and_impact_api(self):
        response=self.api.post(self.root+'/entities',json={'kind':'prop','name':'Silver Key'})
        self.assertEqual(response.status_code,201,response.text)
        entity=response.json()
        fact=self.api.post(self.root+'/entities/'+entity['id']+'/facts',json={
            'key':'owner','value':'Mara','source_note':'Creator notebook'}).json()
        self.assertEqual(fact['status'],'proposed')
        decision=self.api.post(self.root+'/facts/'+fact['id']+'/decision',json={
            'decision':'accept','expected_entity_revision':1})
        self.assertEqual(decision.status_code,200,decision.text)
        self.assertEqual(decision.json()['status'],'accepted')
        bible=self.api.get(self.root).json()
        self.assertEqual(bible['entities'][0]['facts'][0]['fact_value'],'Mara')
        impacts=bible['continuity']['issues']
        self.assertEqual(len([x for x in impacts if x['type']=='canon_change_impact']),1)
        ack=self.api.post(self.root+'/changes/'+impacts[0]['change_id']+'/acknowledge',json={
            'expected_screenplay_revision':0})
        self.assertEqual(ack.status_code,200,ack.text)
        self.assertEqual(self.api.get(self.root+'/continuity').json()['unreviewed_count'],0)

    def test_api_stale_write_and_cross_project_access(self):
        entity=self.api.post(self.root+'/entities',json={'kind':'character','name':'Mara'}).json()
        stale=self.api.put(self.root+'/entities/'+entity['id']+'/name',json={
            'name':'Mara New','expected_revision':999})
        self.assertEqual(stale.status_code,409)
        other=self.studio.create_project('Other','Elsewhere')
        other_path=f'/api/projects/{other["id"]}/story-bible'
        forbidden=self.api.post(other_path+'/entities/'+entity['id']+'/facts',json={
            'key':'eye_color','value':'green'})
        self.assertEqual(forbidden.status_code,404)
        missing=self.api.get('/api/projects/not-found/story-bible')
        self.assertEqual(missing.status_code,404)

    def test_api_link_scene_checks_current_script(self):
        p=self.studio.save_screenplay(self.prj['id'],SCRIPT,0)
        scene_id=p['scenes'][0]['id']
        e=self.api.post(self.root+'/entities',json={'kind':'location','name':'Home'}).json()
        response=self.api.post(self.root+'/entities/'+e['id']+'/scene-links',json={
            'scene_id':scene_id,'expected_entity_revision':e['revision']})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['scene_links'][0]['scene_id'],scene_id)
