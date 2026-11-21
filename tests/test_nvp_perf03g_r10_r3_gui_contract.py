"""Portable regression for the installed test's exact fixture receipt contract."""
import unittest
from tools import nvp_perf03g_production_gui_smoke as smoke


class ResumeReceipt(unittest.TestCase):
    def setUp(self):
        self.receipt = dict(project_id='p', revision=2, active_digest='d',
                            operation_id='new', state='complete', saved_frames=1524,
                            total_frames=1524, final_movie_exported=False)

    def check(self, receipt=None, status=200, ui=True):
        return smoke._resume_complete(dict(status=status, receipt=receipt,
                                           verified_ui=ui), 'p', 2, 'd', 'old')

    def test_full_fixture_and_pending_ui(self):
        self.assertEqual((smoke.FIXTURE_TAKES, smoke.FIXTURE_FRAMES,
                          smoke.FIXTURE_REELS, smoke.FIXTURE_SECONDS), (32, 1524, 7, 63.5))
        self.assertFalse(self.check(status=None))
        self.assertFalse(self.check())
        self.assertFalse(self.check(self.receipt, ui=False))
        self.assertTrue(self.check(self.receipt))

    def test_old_fixture_and_incomplete_receipts_fail_immediately(self):
        for fields in (dict(saved_frames=756, total_frames=756),
                       dict(saved_frames=756), dict(total_frames=756),
                       dict(state='stopped'), dict(state='refused'),
                       dict(final_movie_exported=True), dict(operation_id='old'),
                       dict(project_id='foreign'), dict(revision=3),
                       dict(active_digest='changed')):
            with self.subTest(fields=fields), self.assertRaises(RuntimeError):
                self.check(dict(self.receipt, **fields))
        with self.assertRaisesRegex(RuntimeError, 'HTTP failure'):
            self.check(status=500)
