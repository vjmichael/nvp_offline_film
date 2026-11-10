"""DA-03 filming worker: source and journal fail-closed contract tests.

These use a simulated OS process only for negative code-path coverage.
The independent tools.nvp_plan03_filming_native_witness runs the real
Win32 Job Object / delegated Linux cgroup and detached heartbeat.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_filming_publication_journal import FilmingPublicationJournal
from backend.nvp_filming_native_supervisor import (
    NativeFilmingTreeWorker, FilmingWorkerCustodyError, sha_file,
)


class FakeOwnedKernelWorker:
    pid = 41200
    def __init__(self, fail_close=False):
        self.terminated = 0
        self.closed = 0
        self.fail_close = fail_close

    def poll(self):
        return -9 if self.terminated else None

    def terminate_tree(self):
        self.terminated += 1

    def close(self):
        self.closed += 1
        if self.fail_close:
            raise RuntimeError("Kernel child-tree cleanup cannot be attested")


class NativeFilmingWorkerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="nvp-native-filming-test-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.studio = Studio(self.root/"studio.sqlite3")
        self.pid = self.studio.create_project("worker", "cancel")["id"]
        self.journal = FilmingPublicationJournal(FilmIndex(self.studio))
        self.journal.begin(self.pid,"FilmTake","FilmSound",["FilmPCM"])
        self.binary = self.root/"tool.py"
        self.binary.write_text("pass",encoding="utf8")
        self.workspace = self.root/"work"
        self.calls=[]
        self.kernel=FakeOwnedKernelWorker()

    def host(self, consent=True):
        def ask(scope):
            self.calls.append(scope)
            return consent
        return NativeFilmingTreeWorker(
            journal=self.journal,workspace=self.workspace,
            ask_native=ask,memory_mb=1024)

    def launch(self, host):
        return host.launch(
            self.pid,"FilmTake",executable=self.binary,
            executable_sha256=sha_file(self.binary),args=("--worker",))

    def test_no_native_consent_prevents_process_launch(self):
        host=self.host(consent=False)
        with patch("backend.nvp_filming_native_supervisor.launch_contained") as launcher:
            with self.assertRaises(PermissionError):
                self.launch(host)
            launcher.assert_not_called()
        self.assertEqual(self.journal.unresolved(self.pid)[0]["state"],"PREPARING")
        self.assertFalse(self.calls[0]["original_or_export_publication_authorized"])
        with self.assertRaises(FilmingWorkerCustodyError):
            host.launch(self.pid,"FilmTake",executable=self.binary,
                        executable_sha256=sha_file(self.binary),args=("--worker",))

    def test_hash_and_missing_job_refuse_before_native_dialog(self):
        host=self.host()
        with self.assertRaises(PermissionError):
            host.launch(self.pid,"FilmTake",executable=self.binary,
                        executable_sha256="0"*64,args=("--worker",))
        with self.assertRaises(PermissionError):
            host.launch(self.pid,"OtherTake",executable=self.binary,
                        executable_sha256=sha_file(self.binary))
        self.assertEqual(self.calls, [])

    def test_os_verified_one_use_stop_precedes_interrupt_and_blocks_replay(self):
        host=self.host()
        with patch("backend.nvp_filming_native_supervisor.launch_contained",
                   return_value=self.kernel) as launcher:
            started=self.launch(host)
        self.assertEqual(started["status"],"OS_CONTAINED_PREPARING_NOT_PUBLISHED")
        self.assertFalse(started["original_take_published"])
        self.assertEqual(launcher.call_args.kwargs["linux_cgroup_tree_required"],
                         __import__("sys").platform=="linux")
        with self.assertRaises(FilmingWorkerCustodyError):
            self.launch(host)
        finished=host.stop_and_interrupt()
        self.assertTrue(finished["worker_process_tree_custody_verified"])
        self.assertEqual(finished["state"],"INTERRUPTED")
        self.assertEqual(self.kernel.terminated,1)
        self.assertEqual(self.kernel.closed,1)
        with self.assertRaises(FilmingWorkerCustodyError):
            host.stop_and_interrupt()
        self.assertFalse(host.inventory_after_restart(self.pid)["automatic_replay_authorized"])

    def test_ambiguous_kernel_cleanup_never_interrupts_journal(self):
        self.kernel=FakeOwnedKernelWorker(fail_close=True)
        host=self.host()
        with patch("backend.nvp_filming_native_supervisor.launch_contained",
                   return_value=self.kernel):
            self.launch(host)
        with self.assertRaisesRegex(FilmingWorkerCustodyError,"unverified"):
            host.stop_and_interrupt()
        self.assertEqual(self.journal.unresolved(self.pid)[0]["state"],"PREPARING")
        with self.assertRaises(FilmingWorkerCustodyError):
            host.stop_and_interrupt()

    def test_changed_journal_during_os_consent_refuses_launch(self):
        def change(scope):
            self.calls.append(scope)
            self.journal.finish(self.pid,"FilmTake",completed=False)
            return True
        host=NativeFilmingTreeWorker(
            journal=self.journal,workspace=self.workspace,ask_native=change)
        with patch("backend.nvp_filming_native_supervisor.launch_contained") as launcher:
            with self.assertRaises(PermissionError):
                self.launch(host)
            launcher.assert_not_called()
        self.assertEqual(self.journal.unresolved(self.pid)[0]["state"],"INTERRUPTED")


if __name__=="__main__":
    unittest.main()
