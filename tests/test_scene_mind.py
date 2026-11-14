"""WR06: within-scene knowledge, deliberately false statements, human review."""
from pathlib import Path
import tempfile
import unittest
from fastapi.testclient import TestClient

from backend.nvp_studio import Studio
from backend.nvp_story_bible import StoryBible
from backend.nvp_scene_mind import SceneMind
from backend.nvp_idea_pipeline import IdeaPipeline
from backend import nvp_api

SCRIPT = "INT. DINER - NIGHT\n\nMARA\nBob took the key.\n\nBOB\nNo, Alice took it.\n\nMARA\nI saw Alice holding it.\n"


class Writer:
    def __init__(self):
        self.prompt = ""
        self.side_effect = None

    def complete(self, system, user):
        self.prompt = user
        if self.side_effect:
            self.side_effect()
        return "INT. DINER - NIGHT\n\nMARA\nI have proof."


class SceneMindTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "nvp.sqlite"
        self.studio = Studio(self.db)
        self.bible = StoryBible(self.studio)
        self.mind = SceneMind(self.studio)
        self.pid = self.studio.create_project("False Accusation", "Mara follows a secret")['id']
        self.script = self.studio.save_screenplay(self.pid, SCRIPT, 0)
        self.scene = self.script['scenes'][0]['id']
        self.mara = self.bible.create_entity(self.pid, 'character', 'Mara')['id']
        self.bob = self.bible.create_entity(self.pid, 'character', 'Bob')['id']
        self.truth = self.bible.propose_fact(self.pid, self.mara, 'took_key', 'Alice')
        self.bible.decide_fact(self.pid, self.truth['id'], 'accept',
                               self.bible.get_entity(self.pid, self.mara)['revision'])
        self.writer = Writer()
        self.pipeline = IdeaPipeline(self.studio, self.writer)

    def tearDown(self):
        self.temp.cleanup()

    def beat(self, line=4, label='Mara accuses Bob'):
        return self.mind.add_beat(self.pid, self.scene, line, label,
                                  self.mind.revision(self.pid))

    def approve_change(self, beat_id, character_id=None, mode='believe', value='Bob'):
        proposed = self.mind.propose_change(self.pid, beat_id, character_id or self.mara,
                                             self.truth['id'], mode,
                                             value if mode == 'believe' else None)
        return self.mind.decide_change(self.pid, proposed['id'], 'accept',
                                       self.mind.revision(self.pid))

    def approve_statement(self, beat_id, intent='deliberate_deception', text='Bob'):
        p = self.mind.propose_statement(self.pid, beat_id, self.bob, self.mara,
                                        self.truth['id'], text, intent)
        return self.mind.decide_statement(self.pid, p['id'], 'accept',
                                          self.mind.revision(self.pid))

    def test_before_and_after_same_beat_do_not_conflate_knowledge(self):
        beat = self.beat()
        self.approve_change(beat['id'], mode='learn_truth')
        before = self.mind.snapshot(self.pid, self.scene, beat['id'], 'before')
        after = self.mind.snapshot(self.pid, self.scene, beat['id'], 'after')
        self.assertEqual(before['states'], [])
        self.assertEqual(after['states'][0]['state'], 'knows_true')

    def test_mistaken_belief_is_not_canon(self):
        beat = self.beat()
        self.approve_change(beat['id'], mode='believe', value='Bob')
        data = self.mind.snapshot(self.pid, self.scene)
        self.assertEqual(data['states'][0]['state'], 'believes_false')
        self.assertEqual(data['states'][0]['world_value'], 'Alice')
        self.assertEqual(self.bible.get_fact(self.pid, self.truth['id'])['fact_value'], 'Alice')
        issues = self.mind.suggestions(self.pid, self.scene)['suggestions']
        self.assertEqual([x['kind'] for x in issues], ['mistaken_belief'])

    def test_lying_does_not_imply_listener_belief(self):
        beat = self.beat(7, 'Bob lies')
        self.approve_statement(beat['id'])
        data = self.mind.snapshot(self.pid, self.scene)
        self.assertEqual(data['states'], [])
        self.assertEqual(data['statements'][0]['claimed_value'], 'Bob')
        self.assertEqual(data['statements'][0]['intent'], 'deliberate_deception')

    def test_speaker_can_know_truth_and_deliberately_lie(self):
        learned = self.beat(4, 'Bob learns truth')
        deception = self.beat(7, 'Bob misdirects Mara')
        self.approve_change(learned['id'], character_id=self.bob, mode='learn_truth')
        self.approve_statement(deception['id'])
        before = self.mind.snapshot(self.pid, self.scene, deception['id'], 'before')
        state = next(s for s in before['states'] if s['character_id'] == self.bob)
        self.assertEqual(state['state'], 'knows_true')

    def test_truthful_label_conflicting_with_canon_generates_reviewable_suggestion(self):
        beat = self.beat(7, 'Bob claims innocence')
        self.approve_statement(beat['id'], intent='truthful_claim', text='Bob')
        issues = self.mind.suggestions(self.pid, self.scene)['suggestions']
        self.assertEqual(issues[0]['kind'], 'claimed_truth_conflicts_canon')

    def test_deliberate_deception_matching_truth_warns_not_assumed_impossible(self):
        beat = self.beat(7, 'Bob withholds context')
        self.approve_statement(beat['id'], text='Alice')
        issues = self.mind.suggestions(self.pid, self.scene)['suggestions']
        self.assertEqual(issues[0]['kind'], 'deception_matches_canon')

    def test_suggestion_accept_is_review_decision_not_script_mutation(self):
        beat = self.beat()
        self.approve_change(beat['id'])
        issue = self.mind.suggestions(self.pid, self.scene)['suggestions'][0]
        old = self.studio.get_project(self.pid)['screenplay']
        updated = self.mind.decide_suggestion(self.pid, self.scene, issue['id'],
                                               'accept', self.mind.revision(self.pid),
                                               resolution='intentional',
                                               review_note='A purposeful red herring')
        self.assertEqual(updated['suggestions'][0]['status'], 'accept')
        self.assertEqual(updated['suggestions'][0]['resolution'], 'intentional')
        self.assertEqual(self.studio.get_project(self.pid)['screenplay'], old)
        self.assertEqual(self.mind.snapshot(self.pid, self.scene)['states'][0]['state'],
                         'believes_false')
        self.assertEqual(self.mind.suggestions(self.pid, self.scene)['suggestions'][0]['status'], 'accept')

    def test_suggestion_rejection_is_durable_and_not_repeated(self):
        beat = self.beat()
        self.approve_change(beat['id'])
        issue = self.mind.suggestions(self.pid, self.scene)['suggestions'][0]
        self.mind.decide_suggestion(self.pid, self.scene, issue['id'],
                                     'reject', self.mind.revision(self.pid),
                                     review_note='Creator rejects classification')
        with self.assertRaisesRegex(RuntimeError, 'already reviewed'):
            self.mind.decide_suggestion(self.pid, self.scene, issue['id'],
                                         'reject', self.mind.revision(self.pid))
        reopened = SceneMind(Studio(self.db))
        self.assertEqual(reopened.suggestions(self.pid, self.scene)['suggestions'][0]['status'], 'reject')

    def test_stale_suggestion_cannot_be_accepted_after_fact_change(self):
        beat = self.beat()
        self.approve_change(beat['id'])
        issue = self.mind.suggestions(self.pid, self.scene)['suggestions'][0]
        new = self.bible.propose_fact(self.pid, self.mara, 'took_key', 'Bob')
        self.bible.decide_fact(self.pid, new['id'], 'accept',
                               self.bible.get_entity(self.pid, self.mara)['revision'],
                               self.truth['id'])
        with self.assertRaisesRegex(RuntimeError, 'changed'):
            self.mind.decide_suggestion(self.pid, self.scene, issue['id'],
                                         'accept', self.mind.revision(self.pid), resolution='fix_later')

    def test_superseded_fact_never_applied_as_current_knowledge(self):
        beat = self.beat()
        self.approve_change(beat['id'], mode='learn_truth')
        new = self.bible.propose_fact(self.pid, self.mara, 'took_key', 'Bob')
        self.bible.decide_fact(self.pid, new['id'], 'accept',
                               self.bible.get_entity(self.pid, self.mara)['revision'],
                               self.truth['id'])
        data = self.mind.snapshot(self.pid, self.scene)
        self.assertEqual(data['states'], [])
        self.assertEqual(data['changes'][0]['source_state'], 'source_fact_changed')
        self.assertIn('knowledge_source_changed', [x['kind'] for x in
                                                      self.mind.suggestions(self.pid, self.scene)['suggestions']])

    def test_proposed_events_do_not_enter_writing_context(self):
        beat = self.beat()
        self.mind.propose_change(self.pid, beat['id'], self.mara, self.truth['id'],
                                 'believe', 'Bob')
        self.pipeline.generate(self.pid, 'screenplay', scene_id=self.scene)
        self.assertNotIn('[BELIEF: BELIEVES_FALSE]', self.writer.prompt)

    def test_accepted_false_belief_and_deception_are_labeled_in_prompt(self):
        beat = self.beat()
        self.approve_change(beat['id'])
        self.approve_statement(beat['id'])
        self.pipeline.generate(self.pid, 'screenplay', scene_id=self.scene)
        self.assertIn('BELIEVES_FALSE', self.writer.prompt)
        self.assertIn('DELIBERATE_DECEPTION', self.writer.prompt)
        self.assertIn('world canon', self.writer.prompt)

    def test_accepted_scene_knowledge_changes_invalidate_existing_draft(self):
        beat = self.beat()
        draft = self.pipeline.generate(self.pid, 'screenplay', scene_id=self.scene)
        self.approve_change(beat['id'])
        updated = self.pipeline.get(self.pid, draft['id'])
        self.assertEqual(updated['bible_context_status'], 'needs_review')
        with self.assertRaisesRegex(RuntimeError, 'Story Bible canon changed'):
            self.pipeline.decide(self.pid, draft['id'], 'use_as_screenplay', 1)

    def test_mid_generation_knowledge_approval_refuses_draft(self):
        beat = self.beat()
        pending = self.mind.propose_change(self.pid, beat['id'], self.mara, self.truth['id'],
                                            'learn_truth')
        self.writer.side_effect = lambda: self.mind.decide_change(self.pid, pending['id'],
                                                                  'accept', self.mind.revision(self.pid))
        with self.assertRaisesRegex(RuntimeError, 'Story Bible changed'):
            self.pipeline.generate(self.pid, 'screenplay', scene_id=self.scene)
        self.assertEqual(self.pipeline.list(self.pid), [])

    def test_stale_scene_beat_requires_reanchoring(self):
        beat = self.beat()
        self.studio.save_screenplay(self.pid, SCRIPT.replace('Bob took the key', 'Mara found the key'), 1)
        with self.assertRaisesRegex(RuntimeError, 'stale'):
            self.mind.snapshot(self.pid, self.scene)
        with self.assertRaisesRegex(RuntimeError, 'changed'):
            self.mind.propose_change(self.pid, beat['id'], self.mara, self.truth['id'],
                                     'believe', 'Bob')
        self.mind.reanchor_beat(self.pid, beat['id'], 4, self.mind.revision(self.pid))
        self.assertEqual(len(self.mind.snapshot(self.pid, self.scene)['beats']), 1)

    def test_out_of_bounds_and_stale_revision_rejected(self):
        with self.assertRaisesRegex(ValueError, 'inside'):
            self.beat(3000)
        stale = self.mind.revision(self.pid)
        self.beat()
        with self.assertRaisesRegex(RuntimeError, 'changed'):
            self.mind.add_beat(self.pid, self.scene, 7, 'Other', stale)

    def test_cross_project_character_and_fact_refused(self):
        movie2 = self.studio.create_project('Second film', 'Other world')['id']
        person = self.bible.create_entity(movie2, 'character', 'Foreign')['id']
        beat = self.beat()
        with self.assertRaises(KeyError):
            self.mind.propose_change(self.pid, beat['id'], person, self.truth['id'], 'learn_truth')
        with self.assertRaises(KeyError):
            self.mind.propose_statement(self.pid, beat['id'], person, self.mara,
                                         self.truth['id'], 'Bob', 'bluff')

    def test_database_restart_preserves_scene_minds(self):
        beat = self.beat()
        self.approve_change(beat['id'])
        self.approve_statement(beat['id'])
        reopened = SceneMind(Studio(self.db))
        view = reopened.snapshot(self.pid, self.scene)
        self.assertEqual(view['states'][0]['state'], 'believes_false')
        self.assertEqual(len(view['statements']), 1)

    def test_second_beat_can_correct_an_earlier_mistaken_belief(self):
        wrong = self.beat(4, 'Believes Bob')
        correction = self.beat(10, 'Finds real evidence')
        self.approve_change(wrong['id'])
        self.approve_change(correction['id'], mode='learn_truth')
        self.assertEqual(self.mind.snapshot(self.pid, self.scene, correction['id'],
                                            'before')['states'][0]['state'], 'believes_false')
        self.assertEqual(self.mind.snapshot(self.pid, self.scene, correction['id'],
                                            'after')['states'][0]['state'], 'knows_true')

    def test_wrong_belief_and_deception_do_not_force_a_change_to_canon(self):
        beat = self.beat()
        self.approve_change(beat['id'])
        self.approve_statement(beat['id'])
        self.assertEqual(self.bible.get_fact(self.pid, self.truth['id'])['status'], 'accepted')
        self.assertEqual(self.studio.get_project(self.pid)['revision'], 1)
        self.assertEqual(len(self.mind.snapshot(self.pid, self.scene)['states']), 1)

    def test_speaker_knowledge_gap_is_suggestion_not_asserted_lie_error(self):
        beat = self.beat(7, 'Bob misleads')
        self.approve_statement(beat['id'])
        suggestion_types = {r['kind'] for r in self.mind.suggestions(self.pid, self.scene)['suggestions']}
        self.assertIn('deceptive_intent_unverified', suggestion_types)
        earlier = self.beat(4, 'Bob sees evidence')
        self.approve_change(earlier['id'], character_id=self.bob, mode='learn_truth')
        suggestion_types = {r['kind'] for r in self.mind.suggestions(self.pid, self.scene)['suggestions']}
        self.assertNotIn('deceptive_intent_unverified', suggestion_types)

    def test_accepted_review_note_enters_writing_context_and_changes_digest(self):
        beat = self.beat()
        self.approve_change(beat['id'])
        draft = self.pipeline.generate(self.pid, 'screenplay', scene_id=self.scene)
        issue = self.mind.suggestions(self.pid, self.scene)['suggestions'][0]
        self.mind.decide_suggestion(self.pid, self.scene, issue['id'], 'accept',
                                    self.mind.revision(self.pid), resolution='intentional',
                                    review_note='The audience should see Mara is mistaken')
        context = self.pipeline.bible_context(self.pid, self.scene)['scene_mind']['text']
        self.assertIn('The audience should see Mara is mistaken', context)
        self.assertEqual(self.pipeline.get(self.pid, draft['id'])['bible_context_status'],
                         'needs_review')
        self.pipeline.generate(self.pid, 'screenplay', scene_id=self.scene)
        self.assertIn('CREATOR CONTINUITY REVIEW: INTENTIONAL', self.writer.prompt)

    def test_rejected_review_not_sent_to_model(self):
        beat = self.beat()
        self.approve_change(beat['id'])
        issue = self.mind.suggestions(self.pid, self.scene)['suggestions'][0]
        self.mind.decide_suggestion(self.pid, self.scene, issue['id'], 'reject',
                                    self.mind.revision(self.pid),
                                    review_note='TEST SECRET DISMISSED REVIEW')
        self.pipeline.generate(self.pid, 'screenplay', scene_id=self.scene)
        self.assertNotIn('TEST SECRET DISMISSED REVIEW', self.writer.prompt)

    def test_accept_review_requires_explicit_resolution(self):
        beat = self.beat()
        self.approve_change(beat['id'])
        issue = self.mind.suggestions(self.pid, self.scene)['suggestions'][0]
        with self.assertRaisesRegex(ValueError, 'explicit resolution'):
            self.mind.decide_suggestion(self.pid, self.scene, issue['id'], 'accept',
                                        self.mind.revision(self.pid))

    def test_stale_beat_generates_review_suggestion_and_requires_reanchor(self):
        beat = self.beat()
        self.studio.save_screenplay(self.pid, SCRIPT.replace('Bob took the key',
                                                             'Bob took the map'), 1)
        suggestions = self.mind.suggestions(self.pid, self.scene)['suggestions']
        self.assertIn('stale_scene_beat', [r['kind'] for r in suggestions])
        self.assertIn(beat['id'], self.mind.snapshot(self.pid)['stale_beat_ids'])
        self.mind.reanchor_beat(self.pid, beat['id'], 4, self.mind.revision(self.pid))
        self.assertNotIn('stale_scene_beat', [r['kind'] for r in
                                              self.mind.suggestions(self.pid, self.scene)['suggestions']])

    def test_one_approved_transition_per_character_fact_at_same_beat(self):
        beat = self.beat()
        self.approve_change(beat['id'])
        conflict = self.mind.propose_change(self.pid, beat['id'], self.mara,
                                            self.truth['id'], 'learn_truth')
        with self.assertRaisesRegex(RuntimeError, 'already resolved'):
            self.mind.decide_change(self.pid, conflict['id'], 'accept',
                                    self.mind.revision(self.pid))
        self.assertEqual(self.mind.snapshot(self.pid, self.scene)['states'][0]['state'],
                         'believes_false')

    def test_unapproved_deception_does_not_affect_writer_digest(self):
        beat = self.beat()
        draft = self.pipeline.generate(self.pid, 'screenplay', scene_id=self.scene)
        self.mind.propose_statement(self.pid, beat['id'], self.bob, self.mara,
                                    self.truth['id'], 'Bob', 'deliberate_deception')
        self.assertEqual(self.pipeline.get(self.pid, draft['id'])['bible_context_status'], 'current')

    def test_creator_may_reject_proposed_knowledge_without_changing_world(self):
        beat = self.beat()
        p = self.mind.propose_change(self.pid, beat['id'], self.mara,
                                     self.truth['id'], 'believe', 'Bob')
        self.mind.decide_change(self.pid, p['id'], 'reject', self.mind.revision(self.pid))
        self.assertEqual(self.mind.snapshot(self.pid, self.scene)['states'], [])
        self.assertEqual(self.bible.get_fact(self.pid, self.truth['id'])['fact_value'], 'Alice')

    def test_api_end_to_end_proposal_approval_and_suggestion_review(self):
        old = nvp_api.studio
        nvp_api.studio = self.studio
        try:
            with TestClient(nvp_api.app) as client:
                base = f'/api/projects/{self.pid}/scene-mind'
                beat = client.post(base + '/beats', json={
                    'scene_id': self.scene, 'line_number': 4, 'label': 'Mara suspects',
                    'expected_revision': self.mind.revision(self.pid)})
                self.assertEqual(beat.status_code, 201)
                proposed = client.post(base + '/changes', json={
                    'beat_id': beat.json()['id'], 'character_id': self.mara,
                    'fact_id': self.truth['id'], 'mode': 'believe', 'belief_value': 'Bob'})
                self.assertEqual(proposed.status_code, 201)
                accepted = client.post(base + '/changes/' + proposed.json()['id'] + '/decision',
                                       json={'decision': 'accept', 'expected_revision': self.mind.revision(self.pid)})
                self.assertEqual(accepted.status_code, 200)
                issues = client.get(base + '/scenes/' + self.scene + '/suggestions')
                self.assertEqual(issues.status_code, 200)
                review = client.post(base + '/scenes/' + self.scene + '/suggestions/' +
                                     issues.json()['suggestions'][0]['id'] + '/decision',
                                     json={'decision':'accept','expected_revision': self.mind.revision(self.pid),
                                           'resolution':'intentional'})
                self.assertEqual(review.status_code, 200)
                self.assertEqual(review.json()['suggestions'][0]['status'], 'accept')
        finally:
            nvp_api.studio = old


if __name__ == '__main__':
    unittest.main()
