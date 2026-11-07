"""WO6 PyInstaller NVP.exe private worker dispatch cannot launch native UI."""
from __future__ import annotations
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_wo6_native_take_action import NativeTakeActionHost
from backend.nvp_wo6_native_shot_action import NativeShotActionHost
from backend.nvp_wo6_native_data_action import NativeFilmDecisionHost
from tools.nvp_desktop_alpha import _run_private_wo6_worker


class InstalledPrivateWorkerEntrypoint(unittest.TestCase):
    def test_only_first_party_worker_types_dispatch_without_creating_gui(self):
        for kind,path in (
            ("take","tools.nvp_wo6_take_worker.main"),
            ("shot","tools.nvp_wo6_shot_worker.main"),
            ("data","tools.nvp_wo6_data_worker.main")):
            with patch(path,return_value=17) as execute:
                self.assertEqual(
                    _run_private_wo6_worker(
                        ["--nvp-wo6-worker",kind,"--spec","task.json"]),17)
                execute.assert_called_once_with(["--spec","task.json"])
        with self.assertRaises(PermissionError):
            _run_private_wo6_worker(
                ["--nvp-wo6-worker","arbitrary_command","--spec","task.json"])
        with self.assertRaises(ValueError):
            _run_private_wo6_worker(["--nvp-wo6-worker","take"])

    def test_frozen_hosts_pin_executable_not_uninstalled_py_script(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            studio=Studio(root/"original.sqlite3")
            index=FilmIndex(studio)
            ledger=TaskLedger(root/"ledger")
            policy=lambda *_: True
            with patch.object(sys,"frozen",True,create=True):
                hosts=[
                    NativeTakeActionHost(
                        index,ledger,(root/"take").absolute(),
                        confirm_creator=policy,authorize_native=policy),
                    NativeShotActionHost(
                        index,ledger,(root/"shot").absolute(),
                        confirm_creator=policy,authorize_native=policy),
                    NativeFilmDecisionHost(
                        index,ledger,(root/"color").absolute(),
                        confirm_creator=policy,authorize_native=policy),
                ]
            for host in hosts:
                self.assertTrue(host.frozen_worker)
                self.assertEqual(host.python,Path(sys.executable).resolve())
                self.assertEqual(host.worker,Path(sys.executable).resolve())


if __name__=="__main__":
    unittest.main()
