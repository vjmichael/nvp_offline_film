"""Real abrupt child exit after encrypted publication, before journal commit."""
import multiprocessing
import os
import unittest
from unittest.mock import patch

from backend import nvp_g07_feature_reels as reels
from test_nvp_perf03g_r6_feature_reels import R6Base

@unittest.skipUnless(os.name=='posix','POSIX fork fixture')
class R6AbruptExit(R6Base,unittest.TestCase):
    def test_child_dies_after_publish_and_parent_explicitly_resumes(self):
        self.seed();f=self.f;first=self.next();publish=reels._publish
        def child():
            def terminate(*a,**kw):
                publish(*a,**kw);os._exit(71)
            with patch.object(reels,'_publish',side_effect=terminate):self.execute(first)
        proc=multiprocessing.get_context('fork').Process(target=child);proc.start();proc.join(45)
        if proc.is_alive():proc.terminate();proc.join();self.fail('Child exceeded bounded fixture')
        self.assertEqual(proc.exitcode,71)
        saved=reels._location(f.folder,f.key,first['job_id'],0)/'body.nvpsealed';ciphertext=saved.read_bytes()
        pending=self.next();self.assertEqual(pending['action'],'resume')
        self.execute(pending);self.assertEqual(saved.read_bytes(),ciphertext);self.assertEqual(self.next()['part'],1)
