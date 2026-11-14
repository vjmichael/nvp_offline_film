"""NVP-WRITE-07: evidence-backed screenplay review (no silent canon edits)."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

from backend.nvp_studio import Studio
from backend.nvp_story_bible import StoryBible
from backend.nvp_scene_mind import SceneMind
from backend.nvp_screenplay_review import ScreenplayContinuityReview
from backend import nvp_api


class ScreenplayReviewTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.db = Path(self.home.name)/'film.sqlite3'
        self.studio = Studio(self.db)
        self.bible = StoryBible(self.studio)
        self.mind = SceneMind(self.studio)
        self.reviewer = ScreenplayContinuityReview(self.studio)
        self.pid = self.studio.create_project('A Quiet Mystery', 'Someone loses a car')['id']
        self.mara = self.bible.create_entity(self.pid,'character','Mara')

    def tearDown(self):
        self.home.cleanup()

    def fact(self, key, value, scope='global', entity=None):
        ent = entity or self.mara
        f = self.bible.propose_fact(self.pid,ent['id'],key,value,scope)
        self.bible.decide_fact(self.pid,f['id'],'accept',
                               self.bible.get_entity(self.pid,ent['id'])['revision'])
        return f

    def replace_fact(self, old, value):
        prop = self.bible.propose_fact(self.pid, self.mara['id'],old['fact_key'],value,old['story_scope'])
        self.bible.decide_fact(self.pid,prop['id'],'accept',
                               self.bible.get_entity(self.pid,self.mara['id'])['revision'], old['id'])
        return prop

    def script(self, body):
        current = self.studio.get_project(self.pid)
        return self.studio.save_screenplay(self.pid,body,current['revision'])['scenes'][0]

    def review(self, scene):
        return self.reviewer.report(self.pid,scene['id'])

    def test_narration_conflicts_with_approved_drive_fact_and_cites_exact_line(self):
        canon = self.fact('cannot_drive','Mara has never learned to drive')
        scene = self.script('INT. GARAGE - NIGHT\n\nMara drives the car into the garage.')
        results = self.review(scene)['suggestions']
        self.assertEqual(len(results),1)
        issue = results[0]
        self.assertEqual(issue['kind'],'narration_canon_mismatch')
        self.assertEqual(issue['canon']['id'],canon['id'])
        self.assertEqual(issue['evidence'][0]['scene_line'],3)
        self.assertEqual(issue['evidence'][0]['screenplay_line'],3)
        self.assertEqual(issue['evidence'][0]['quote'],'Mara drives the car into the garage.')
        self.assertEqual(issue['evidence'][0]['source_kind'],'narration')
        self.assertEqual(self.studio.get_project(self.pid)['screenplay'].count('Mara drives'),1)

    def test_consistent_narration_has_no_issue(self):
        self.fact('can_drive','yes')
        scene = self.script('INT. GARAGE - NIGHT\n\nMara drives the car into the garage.')
        self.assertEqual(self.review(scene)['suggestions'],[])

    def test_dialogue_tension_is_not_treated_as_objective_error(self):
        self.fact('can_drive','false')
        scene = self.script('INT. GARAGE - NIGHT\n\nMARA\nI can drive, believe me.')
        r = self.review(scene)['suggestions']
        self.assertEqual(len(r),1)
        self.assertEqual(r[0]['kind'],'dialogue_canon_tension')
        self.assertEqual(r[0]['evidence'][0]['cue_scene_line'],3)
        self.assertIn('lie',r[0]['explanation'])

    def test_proposed_and_superseded_facts_do_not_create_issues(self):
        self.bible.propose_fact(self.pid,self.mara['id'],'can_drive','no')
        scene = self.script('INT. GARAGE - NIGHT\n\nMara drives the car.')
        self.assertEqual(self.review(scene)['suggestions'],[])
        old = self.fact('can_drive','no')
        self.replace_fact(old,'yes')
        self.assertEqual(self.review(scene)['suggestions'],[])

    def test_mismatched_narration_within_one_scene_is_suggestion(self):
        scene = self.script('EXT. PARK - DAY\n\nMara has blue eyes.\n\nMara has brown eyes.')
        r = self.review(scene)['suggestions']
        self.assertEqual(len(r),1)
        self.assertEqual(r[0]['kind'],'narration_internal_tension')
        self.assertEqual([v['scene_line'] for v in r[0]['evidence']],[3,5])

    def test_dialogue_disagreement_does_not_create_internal_narration_error(self):
        scene = self.script('INT. DINER - NIGHT\n\nMARA\nI can drive.\n\nMARA\nI cannot drive.')
        self.assertEqual(self.review(scene)['suggestions'],[])

    def test_ranged_scope_is_not_assigned_to_unknown_story_time(self):
        self.fact('can_drive','false','before_reveal')
        scene = self.script('EXT. ROAD - DAY\n\nMara drives a truck.')
        self.assertEqual(self.review(scene)['suggestions'],[])
        self.assertIn('relative story scopes',self.review(scene)['limitations'])

    def test_unsupported_semantic_claims_are_not_guessed(self):
        self.fact('owns_key','Bob')
        scene = self.script('INT. ROOM - DAY\n\nMara looks at the key.\n\nMARA\nI know Bob has it.')
        self.assertEqual(self.review(scene)['suggestions'],[])

    def test_hypothetical_and_quotes_are_skipped(self):
        self.fact('can_drive','false')
        scene = self.script('INT. GARAGE - NIGHT\n\nIf Mara drives the car, we lose.\n\n"Mara drives the car", says Bob.')
        self.assertEqual(self.review(scene)['suggestions'],[])

    def test_identical_alias_resolves_one_identity(self):
        self.bible.add_alias(self.pid,self.mara['id'],'M',self.bible.get_entity(self.pid,self.mara['id'])['revision'])
        self.fact('can_drive','false')
        scene = self.script('INT. GARAGE - NIGHT\n\nM drives a car.')
        self.assertEqual(len(self.review(scene)['suggestions']),1)

    def test_facts_are_project_scoped_even_with_same_character_name(self):
        self.fact('can_drive','false')
        second = self.studio.create_project('Other Film','Another character')['id']
        other = self.bible.create_entity(second,'character','Mara')
        f = self.bible.propose_fact(second,other['id'],'can_drive','yes')
        self.bible.decide_fact(second,f['id'],'accept',self.bible.get_entity(second,other['id'])['revision'])
        current = self.studio.get_project(second)
        scene = self.studio.save_screenplay(second,'INT. GARAGE - NIGHT\n\nMara drives the car.',current['revision'])['scenes'][0]
        self.assertEqual(self.reviewer.report(second,scene['id'])['suggestions'],[])

    def test_accept_intentional_is_a_review_only_and_durable(self):
        self.fact('can_drive','no')
        scene = self.script('INT. GARAGE - DAY\n\nMara drives a car.')
        baseline = self.review(scene)
        suggested = baseline['suggestions'][0]
        result = self.reviewer.decide(self.pid,scene['id'],suggested['id'],'accept',
                    baseline['review_revision'], baseline['screenplay_revision'],'intentional','It is a dream.')
        self.assertEqual(result['suggestions'][0]['status'],'accept')
        self.assertEqual(result['suggestions'][0]['resolution'],'intentional')
        self.assertIn('Mara drives',self.studio.get_project(self.pid)['screenplay'])
        self.assertEqual(self.bible.get_entity(self.pid,self.mara['id'])['facts'][0]['status'],'accepted')
        new = ScreenplayContinuityReview(Studio(self.db)).report(self.pid,scene['id'])
        self.assertEqual(new['suggestions'][0]['review_note'],'It is a dream.')
        with self.studio._connection() as db:
            persisted = db.execute('SELECT evidence_json FROM screenplay_review_decisions').fetchone()[0]
            self.assertIn('Mara drives a car',persisted)

    def test_reject_is_distinct_from_accept_and_can_not_auto_fix(self):
        self.fact('can_drive','no')
        scene = self.script('INT. GARAGE - DAY\n\nMara drives a car.')
        r = self.review(scene)
        updated = self.reviewer.decide(self.pid,scene['id'],r['suggestions'][0]['id'],
                         'reject',r['review_revision'],r['screenplay_revision'])
        self.assertEqual(updated['suggestions'][0]['status'],'reject')
        self.assertEqual(updated['counts']['unreviewed'],0)

    def test_duplicate_and_stale_review_revision_fail(self):
        self.fact('can_drive','no')
        scene = self.script('INT. GARAGE - DAY\n\nMara drives a car.')
        r = self.review(scene)
        id = r['suggestions'][0]['id']
        self.reviewer.decide(self.pid,scene['id'],id,'reject',r['review_revision'],r['screenplay_revision'])
        with self.assertRaisesRegex(RuntimeError,'Review changed'):
            self.reviewer.decide(self.pid,scene['id'],id,'reject',r['review_revision'],r['screenplay_revision'])
        again = self.review(scene)
        with self.assertRaisesRegex(RuntimeError,'already reviewed'):
            self.reviewer.decide(self.pid,scene['id'],id,'reject',again['review_revision'],again['screenplay_revision'])

    def test_screenplay_edit_does_not_reuse_previous_review(self):
        self.fact('can_drive','no')
        scene = self.script('EXT. ROAD - DAY\n\nMara drives a car.')
        r = self.review(scene)
        self.reviewer.decide(self.pid,scene['id'],r['suggestions'][0]['id'],'reject',
                             r['review_revision'],r['screenplay_revision'])
        new = self.script('EXT. ROAD - DAY\n\nMara drives the van.')
        suggestion = self.review(new)['suggestions'][0]
        self.assertEqual(suggestion['status'],'proposed')
        self.assertNotEqual(suggestion['id'],r['suggestions'][0]['id'])

    def test_canon_revision_does_not_reuse_old_review(self):
        old = self.fact('can_drive','no')
        scene = self.script('EXT. ROAD - DAY\n\nMara drives a car.')
        first = self.review(scene)
        self.reviewer.decide(self.pid,scene['id'],first['suggestions'][0]['id'],'reject',
                             first['review_revision'],first['screenplay_revision'])
        self.replace_fact(old,'yes')
        self.assertEqual(self.review(scene)['suggestions'],[])
        active = next(x for x in self.bible.get_entity(self.pid,self.mara['id'])['facts'] if x['status']=='accepted')
        self.replace_fact(active,'no')
        latest = self.review(scene)['suggestions'][0]
        self.assertEqual(latest['status'],'proposed')

    def test_rejects_decision_with_invalid_revision_and_resolution(self):
        self.fact('can_drive','no')
        scene=self.script('EXT. ROAD - DAY\n\nMara drives the van.')
        r=self.review(scene)
        args=(self.pid,scene['id'],r['suggestions'][0]['id'])
        with self.assertRaises(ValueError):
            self.reviewer.decide(*args,'accept',0,1)
        with self.assertRaises(ValueError):
            self.reviewer.decide(*args,'reject',0,1,'intentional')
        with self.assertRaises(RuntimeError):
            self.reviewer.decide(*args,'reject',0,100)

    def test_dialogue_is_contextualized_when_deceptive_statement_is_approved(self):
        canon=self.fact('can_drive','no')
        scene=self.script('INT. GARAGE - NIGHT\n\nMARA\nI can drive.')
        snap=self.mind.snapshot(self.pid)
        beat=self.mind.add_beat(self.pid,scene['id'],4,'Mara lies',snap['revision'])
        statement=self.mind.propose_statement(self.pid,beat['id'],self.mara['id'],
                                              self.bible.create_entity(self.pid,'character','Bob')['id'],
                                              canon['id'],'yes','deliberate_deception')
        self.mind.decide_statement(self.pid,statement['id'],'accept',self.mind.snapshot(self.pid)['revision'])
        r=self.review(scene)['suggestions'][0]
        self.assertEqual(r['kind'],'dialogue_canon_tension')
        self.assertIn('deliberate_deception',r['explanation'])

    def test_missing_and_wrong_project_rejected(self):
        self.fact('can_drive','no')
        scene=self.script('EXT. ROAD - DAY\n\nMara drives a van.')
        with self.assertRaises(KeyError):
            self.reviewer.report('nope',scene['id'])
        p2=self.studio.create_project('Second','Something')['id']
        with self.assertRaises(KeyError):
            self.reviewer.report(p2,scene['id'])

    def test_api_listing_decision_errors_and_persistence(self):
        self.fact('can_drive','no')
        scene=self.script('EXT. ROAD - DAY\n\nMara drives a van.')
        old=nvp_api.studio
        nvp_api.studio=self.studio
        try:
            with TestClient(nvp_api.app) as client:
                url=f'/api/projects/{self.pid}/screenplay-review/scenes/{scene["id"]}'
                response=client.get(url)
                self.assertEqual(response.status_code,200)
                body=response.json()
                self.assertEqual(len(body['suggestions']),1)
                suffix='/suggestions/'+body['suggestions'][0]['id']+'/decision'
                invalid=client.post(url+suffix,json={'decision':'accept','expected_review_revision':0,
                    'expected_screenplay_revision':1,'resolution':''})
                self.assertEqual(invalid.status_code,422)
                good=client.post(url+suffix,json={'decision':'accept','expected_review_revision':0,
                    'expected_screenplay_revision':1,'resolution':'fix_later','note':'Change scene staging'})
                self.assertEqual(good.status_code,200)
                self.assertEqual(good.json()['suggestions'][0]['resolution'],'fix_later')
                self.assertEqual(client.get(url).json()['suggestions'][0]['status'],'accept')
        finally:
            nvp_api.studio=old


if __name__=='__main__':
    unittest.main()

class ReviewHistoryTests(unittest.TestCase):
    # Reuse setup/helpers, not the original test methods.
    setUp = ScreenplayReviewTests.setUp
    tearDown = ScreenplayReviewTests.tearDown
    fact = ScreenplayReviewTests.fact
    script = ScreenplayReviewTests.script
    review = ScreenplayReviewTests.review
    def test_history_retains_original_quote_after_scene_changes(self):
        self.fact('can_drive','no')
        old=self.script('EXT. ROAD - DAY\n\nMara drives a car.')
        baseline=self.review(old)
        self.reviewer.decide(self.pid,old['id'],baseline['suggestions'][0]['id'],
                             'accept',0,1,'fix_later','Repair staging')
        self.script('EXT. ROAD - DAY\n\nMara walks to the station.')
        history=self.reviewer.history(self.pid,old['id'])['history']
        self.assertEqual(len(history),1)
        self.assertFalse(history[0]['is_current_evidence'])
        self.assertIn('Mara drives a car',str(history[0]['evidence']))
        self.assertEqual(history[0]['note'],'Repair staging')

    def test_history_of_removed_scene_remains_accessible(self):
        self.fact('can_drive','no')
        scene=self.script('EXT. ROAD - DAY\n\nMara drives a car.')
        r=self.review(scene)
        self.reviewer.decide(self.pid,scene['id'],r['suggestions'][0]['id'],'reject',0,1)
        self.script('INT. HOUSE - NIGHT\n\nMara rests.')
        entry=self.reviewer.history(self.pid,scene['id'])['history'][0]
        self.assertFalse(entry['is_current_evidence'])

    def test_history_has_project_scope_and_size_limits(self):
        self.fact('can_drive','no')
        scene=self.script('EXT. ROAD - DAY\n\nMara drives a car.')
        r=self.review(scene)
        self.reviewer.decide(self.pid,scene['id'],r['suggestions'][0]['id'],'reject',0,1)
        self.assertEqual(len(self.reviewer.history(self.pid,limit=1)['history']),1)
        with self.assertRaises(ValueError): self.reviewer.history(self.pid,limit=0)
        with self.assertRaises(KeyError): self.reviewer.history('another-project')

class ReviewerEdgeCases(unittest.TestCase):
    setUp = ScreenplayReviewTests.setUp
    tearDown = ScreenplayReviewTests.tearDown
    fact = ScreenplayReviewTests.fact
    script = ScreenplayReviewTests.script
    review = ScreenplayReviewTests.review

    def test_second_scene_uses_absolute_screenplay_line_numbers(self):
        self.fact('eye_color','brown')
        project = self.studio.save_screenplay(self.pid,
            'INT. OFFICE - DAY\n\nMara looks at a postcard.\n\n'
            'EXT. LAKE - DAWN\n\nMara has blue eyes.',0)
        second = project['scenes'][1]
        issues = self.review(second)['suggestions']
        self.assertEqual(len(issues),1)
        self.assertEqual(issues[0]['evidence'][0]['scene_line'],3)
        self.assertEqual(issues[0]['evidence'][0]['screenplay_line'],7)

    def test_eye_colour_and_alive_patterns_are_exact(self):
        self.fact('eye_color','green')
        self.fact('alive','true')
        scene=self.script('INT. HOSPITAL - NIGHT\n\nMara has blue eyes.\n\nMara is dead.')
        issues=self.review(scene)['suggestions']
        self.assertEqual(len(issues),2)
        self.assertEqual(set(x['canon']['fact_key'] for x in issues),{'eye_color','alive'})

    def test_canon_fact_values_from_unrelated_slots_are_not_coerced(self):
        self.fact('alive','can drive')
        scene=self.script('INT. HOSPITAL - NIGHT\n\nMara is dead.')
        self.assertEqual(self.review(scene)['suggestions'],[])

    def test_quoted_narration_does_not_become_factual_evidence(self):
        self.fact('eye_color','green')
        scene=self.script('INT. HALLWAY - DAY\n\n"Mara has blue eyes" is written on the wall.')
        self.assertEqual(self.review(scene)['suggestions'],[])

    def test_review_id_does_not_cross_project_boundary(self):
        p2=self.studio.create_project('Another film','Other script')['id']
        self.bible.create_entity(p2,'character','Mara')
        same='INT. ROOM - NIGHT\n\nMara has green eyes.\n\nMara has blue eyes.'
        first=self.script(same)
        second=self.studio.save_screenplay(p2,same,0)['scenes'][0]
        r1=self.review(first)['suggestions'][0]
        r2=self.reviewer.report(p2,second['id'])['suggestions'][0]
        self.assertNotEqual(r1['id'],r2['id'])

    def test_source_changing_in_unrelated_scene_preserves_current_review(self):
        self.fact('can_drive','no')
        project=self.studio.save_screenplay(self.pid,
            'INT. GARAGE - NIGHT\n\nMara drives a car.\n\n'
            'EXT. YARD - NIGHT\n\nThe moon shines.',0)
        first=project['scenes'][0]
        r=self.review(first)
        self.reviewer.decide(self.pid,first['id'],r['suggestions'][0]['id'],'accept',0,1,'intentional')
        # Scene identity and text are unchanged even though the whole script revision changes.
        self.studio.save_screenplay(self.pid,
            'INT. GARAGE - NIGHT\n\nMara drives a car.\n\n'
            'EXT. YARD - NIGHT\n\nThe moon disappears.',1)
        report=self.review(first)
        self.assertEqual(report['suggestions'][0]['status'],'accept')
        self.assertEqual(report['suggestions'][0]['id'],r['suggestions'][0]['id'])

    def test_rejects_unknown_or_expired_suggestion_id(self):
        self.fact('can_drive','no')
        scene=self.script('INT. GARAGE - NIGHT\n\nMara drives a car.')
        r=self.review(scene)
        with self.assertRaisesRegex(RuntimeError,'Evidence or approved canon changed'):
            self.reviewer.decide(self.pid,scene['id'],'nonexistent','reject',
                                 r['review_revision'],r['screenplay_revision'])
