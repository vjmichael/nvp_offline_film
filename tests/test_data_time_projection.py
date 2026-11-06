"""Check exact temporal output conversions."""
import unittest
from backend.nvp_temporal_ledger import TICKS_PER_SECOND, tick_from_frame

class TimeTests(unittest.TestCase):
    def test_24fps(self):
        self.assertEqual(tick_from_frame(24,24,1), TICKS_PER_SECOND)
