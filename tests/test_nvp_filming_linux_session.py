"""DA-03 host launch/custody composition contracts; not kernel acceptance."""
import subprocess
from unittest.mock import Mock, patch

import pytest

from backend.nvp_filming_linux_session import (
    LinuxFilmingSession, FilmingCustodyInitializationError, launch_linux_filming_session,
)


def test_launch_retains_actual_child_and_custody():
    child = Mock()
    child.poll.return_value = None
    with patch("backend.nvp_filming_linux_session.create_private_group_and_launch",
               return_value=("/sys/fs/cgroup/delegated/leaf", child)) as launch, patch(
               "backend.nvp_filming_linux_session.LinuxFilmingCgroup") as custody:
        session = launch_linux_filming_session(
            "/sys/fs/cgroup/delegated", "/bin/true", ["/bin/true"])
    assert session.child is child
    assert session.custody is custody.return_value
    launch.assert_called_once()
    custody.assert_called_once()


def test_stop_requires_tree_receipt_before_wait():
    child = Mock()
    custody = Mock()
    custody.stop_and_verify.side_effect = RuntimeError("group still populated")
    custody.verify_still_empty.return_value = custody.stop_and_verify.return_value
    session = LinuxFilmingSession("/group", child, custody)
    with pytest.raises(RuntimeError, match="populated"):
        session.stop_and_verify()
    child.wait.assert_not_called()


def test_stop_returns_tree_and_worker_receipts():
    child = Mock(returncode=-9)
    custody = Mock()
    custody.stop_and_verify.return_value = {
        "process_tree_custody_verified": True, "empty_group_verified": True, "scope": "linux-cgroup-v2"}
    custody.verify_still_empty.return_value = custody.stop_and_verify.return_value
    session = LinuxFilmingSession("/group", child, custody)
    result = session.stop_and_verify(timeout=2)
    assert result["process_tree_custody_verified"]
    assert result["worker_exit_verified"]
    assert result["worker_returncode"] == -9
    child.wait.assert_called_once()
    assert 0 <= child.wait.call_args.kwargs["timeout"] <= 2


def test_failed_custody_construction_does_not_claim_success():
    with patch("backend.nvp_filming_linux_session.create_private_group_and_launch",
               return_value=("/group", Mock())), patch(
               "backend.nvp_filming_linux_session.LinuxFilmingCgroup",
               side_effect=RuntimeError("not delegated")):
        with pytest.raises(RuntimeError, match="reconcile"):
            launch_linux_filming_session("/root", "/bin/true", ["/bin/true"])


@pytest.mark.parametrize("receipt", [
    {},
    {"process_tree_custody_verified": False, "empty_group_verified": True, "scope": "linux-cgroup-v2"},
    {"process_tree_custody_verified": True, "empty_group_verified": False, "scope": "linux-cgroup-v2"},
    {"process_tree_custody_verified": True, "empty_group_verified": True, "scope": "untrusted"},
])
def test_incomplete_kernel_receipt_cannot_claim_worker_shutdown(receipt):
    child = Mock(returncode=-9)
    custody = Mock()
    custody.stop_and_verify.return_value = receipt
    with pytest.raises(RuntimeError, match="affirmative Linux"):
        custody.verify_still_empty.return_value = custody.stop_and_verify.return_value
        LinuxFilmingSession("/group", child, custody).stop_and_verify()
    child.wait.assert_not_called()


def test_worker_exit_status_must_be_observed():
    child = Mock(returncode=None)
    custody = Mock()
    custody.stop_and_verify.return_value = {
        "process_tree_custody_verified": True,
        "empty_group_verified": True,
        "scope": "linux-cgroup-v2",
    }
    with pytest.raises(RuntimeError, match="exit status"):
        custody.verify_still_empty.return_value = custody.stop_and_verify.return_value
        LinuxFilmingSession("/group", child, custody).stop_and_verify()
    child.wait.assert_called_once()

def test_failed_custody_exposes_exact_worker_and_group_for_recovery():
    """The host must not lose its live child handle after constructor failure."""
    child = Mock(pid=91234)
    group = "/sys/fs/cgroup/delegated/nvp-film-test"
    with patch("backend.nvp_filming_linux_session.create_private_group_and_launch",
               return_value=(group, child)), patch(
               "backend.nvp_filming_linux_session.LinuxFilmingCgroup",
               side_effect=OSError("kernel denied custody")):
        with pytest.raises(FilmingCustodyInitializationError) as caught:
            launch_linux_filming_session("/sys/fs/cgroup/delegated",
                                         "/bin/true", ["/bin/true"])
    assert caught.value.group == group
    assert caught.value.child is child
    assert isinstance(caught.value.__cause__, OSError)
    child.kill.assert_not_called()
    child.terminate.assert_not_called()


def test_kernel_phase_consumes_worker_reap_budget():
    """A slow kernel phase must not grant another full worker timeout."""
    child = Mock(returncode=-9)
    custody = Mock()
    custody.stop_and_verify.return_value = {
        "process_tree_custody_verified": True,
        "empty_group_verified": True,
        "scope": "linux-cgroup-v2",
    }
    with patch("backend.nvp_filming_linux_session.time.monotonic",
               side_effect=[100.0, 102.5, 102.6, 102.7]):
        custody.verify_still_empty.return_value = custody.stop_and_verify.return_value
        LinuxFilmingSession("/group", child, custody).stop_and_verify(timeout=3)
    custody.stop_and_verify.assert_called_once_with(timeout=3)
    child.wait.assert_called_once_with(timeout=0.5)


def test_exhausted_kernel_budget_cannot_claim_bounded_shutdown():
    child = Mock(returncode=-9)
    custody = Mock()
    custody.stop_and_verify.return_value = {
        "process_tree_custody_verified": True,
        "empty_group_verified": True,
        "scope": "linux-cgroup-v2",
    }
    with patch("backend.nvp_filming_linux_session.time.monotonic",
               side_effect=[100.0, 105.0]):
        with pytest.raises(RuntimeError, match="exceeded filming shutdown deadline"):
            custody.verify_still_empty.return_value = custody.stop_and_verify.return_value
            LinuxFilmingSession("/group", child, custody).stop_and_verify(timeout=3)
    child.wait.assert_not_called()


@pytest.mark.parametrize("timeout", [0, -1, 61, float("nan"), float("inf"), float("-inf"), True, "5"])
def test_invalid_deadline_refused_before_kernel_custody(timeout):
    child = Mock()
    custody = Mock()
    with pytest.raises(ValueError, match="Bounded positive"):
        custody.verify_still_empty.return_value = custody.stop_and_verify.return_value
        LinuxFilmingSession("/group", child, custody).stop_and_verify(timeout=timeout)
    custody.stop_and_verify.assert_not_called()
    child.wait.assert_not_called()


def test_exited_worker_cannot_be_admitted_as_live_filming_session():
    """A completed bootstrap is not evidence of a running protected worker."""
    child = Mock(pid=91235)
    child.poll.return_value = 0
    group = "/sys/fs/cgroup/delegated/nvp-film-exited"
    with patch("backend.nvp_filming_linux_session.create_private_group_and_launch",
               return_value=(group, child)), patch(
               "backend.nvp_filming_linux_session.LinuxFilmingCgroup"):
        with pytest.raises(FilmingCustodyInitializationError) as caught:
            launch_linux_filming_session("/sys/fs/cgroup/delegated",
                                         "/bin/true", ["/bin/true"])
    assert caught.value.child is child
    assert caught.value.group == group
    child.kill.assert_not_called()
    child.terminate.assert_not_called()

def test_failed_admission_reconciles_same_group_and_worker():
    child = Mock(returncode=-9)
    custody_receipt = {
        "process_tree_custody_verified": True,
        "empty_group_verified": True,
        "scope": "linux-cgroup-v2",
    }
    error = FilmingCustodyInitializationError("/owned/leaf", child)
    with patch("backend.nvp_filming_linux_session.LinuxFilmingCgroup") as factory:
        factory.return_value.stop_and_verify.return_value = custody_receipt
        factory.return_value.verify_still_empty.return_value = custody_receipt
        result = error.reconcile_and_stop('/owned', timeout=2)
    factory.assert_called_once_with(private_group='/owned/leaf', delegated_root='/owned')
    assert result['worker_exit_verified'] is True
    child.wait.assert_called_once()

def test_failed_admission_recovery_denial_never_reaps_child():
    child = Mock()
    error = FilmingCustodyInitializationError("/owned/leaf", child)
    with patch("backend.nvp_filming_linux_session.LinuxFilmingCgroup",
               side_effect=OSError("replaced cgroup")):
        with pytest.raises(OSError, match="replaced cgroup"):
            error.reconcile_and_stop('/owned')
    child.wait.assert_not_called()
    child.kill.assert_not_called()

def test_failed_admission_recovery_refuses_incomplete_kernel_receipt():
    child = Mock()
    error = FilmingCustodyInitializationError("/owned/leaf", child)
    with patch("backend.nvp_filming_linux_session.LinuxFilmingCgroup") as factory:
        factory.return_value.stop_and_verify.return_value = {}
        with pytest.raises(RuntimeError, match="affirmative Linux"):
            error.reconcile_and_stop('/owned')
    child.wait.assert_not_called()


def test_exactly_exhausted_kernel_budget_only_allows_nonblocking_reap():
    child = Mock(returncode=-9)
    custody = Mock()
    custody.stop_and_verify.return_value = {
        "process_tree_custody_verified": True, "empty_group_verified": True,
        "scope": "linux-cgroup-v2",
    }
    custody.verify_still_empty.return_value = custody.stop_and_verify.return_value
    with patch("backend.nvp_filming_linux_session.time.monotonic",
               side_effect=[100.0, 103.0, 103.0, 103.0]):
        result = LinuxFilmingSession("/group", child, custody).stop_and_verify(timeout=3)
    child.wait.assert_called_once_with(timeout=0.0)
    assert result["worker_exit_verified"] is True


def test_worker_wait_overrun_refuses_bounded_shutdown_receipt():
    """A late wait return cannot retroactively satisfy the shared deadline."""
    child = Mock(returncode=-9)
    custody = Mock()
    custody.stop_and_verify.return_value = {
        "process_tree_custody_verified": True,
        "empty_group_verified": True,
        "scope": "linux-cgroup-v2",
    }
    with patch("backend.nvp_filming_linux_session.time.monotonic",
               side_effect=[100.0, 101.0, 103.01]):
        with pytest.raises(RuntimeError, match="Worker reaping exceeded"):
            custody.verify_still_empty.return_value = custody.stop_and_verify.return_value
            LinuxFilmingSession("/group", child, custody).stop_and_verify(timeout=3)
    child.wait.assert_called_once_with(timeout=2.0)


def test_worker_wait_exact_deadline_is_not_an_overrun():
    child = Mock(returncode=-9)
    custody = Mock()
    custody.stop_and_verify.return_value = {
        "process_tree_custody_verified": True,
        "empty_group_verified": True,
        "scope": "linux-cgroup-v2",
    }
    custody.verify_still_empty.return_value = custody.stop_and_verify.return_value
    with patch("backend.nvp_filming_linux_session.time.monotonic",
               side_effect=[100.0, 101.0, 103.0, 103.0]):
        result = LinuxFilmingSession("/group", child, custody).stop_and_verify(timeout=3)
    assert result["worker_exit_verified"] is True


def test_reap_timeout_retries_without_reissuing_one_use_kernel_kill():
    """A verified empty cgroup remains verified when child wait times out."""
    child = Mock(returncode=None)
    child.wait.side_effect = [subprocess.TimeoutExpired("worker", 1), 0]
    custody = Mock()
    custody.stop_and_verify.return_value = {
        "process_tree_custody_verified": True,
        "empty_group_verified": True,
        "scope": "linux-cgroup-v2",
    }
    custody.verify_still_empty.return_value = custody.stop_and_verify.return_value
    session = LinuxFilmingSession("/group", child, custody)
    with pytest.raises(RuntimeError, match="worker exit unverified"):
        session.stop_and_verify(timeout=1)
    child.returncode = -9
    receipt = session.stop_and_verify(timeout=1)
    assert receipt["worker_exit_verified"] is True
    assert receipt["worker_returncode"] == -9
    custody.stop_and_verify.assert_called_once()


def test_unverified_kernel_receipt_never_cached_for_recovery():
    child = Mock(returncode=-9)
    custody = Mock()
    custody.stop_and_verify.side_effect = [
        {"process_tree_custody_verified": True, "empty_group_verified": False,
         "scope": "linux-cgroup-v2"},
        {"process_tree_custody_verified": True, "empty_group_verified": True,
         "scope": "linux-cgroup-v2"},
    ]
    custody.verify_still_empty.return_value = {"process_tree_custody_verified": True, "empty_group_verified": True, "scope": "linux-cgroup-v2"}
    session = LinuxFilmingSession("/group", child, custody)
    with pytest.raises(RuntimeError, match="affirmative Linux"):
        session.stop_and_verify()
    assert session._verified_tree_receipt is None
    session.stop_and_verify()
    assert custody.stop_and_verify.call_count == 2


def test_reap_retry_refuses_repopulated_group_without_second_kill():
    child = Mock(returncode=None)
    child.wait.side_effect = subprocess.TimeoutExpired("worker", 1)
    custody = Mock()
    custody.stop_and_verify.return_value = {
        "process_tree_custody_verified": True,
        "empty_group_verified": True, "scope": "linux-cgroup-v2",
    }
    custody.verify_still_empty.return_value = custody.stop_and_verify.return_value
    session = LinuxFilmingSession("/group", child, custody)
    with pytest.raises(RuntimeError, match="worker exit unverified"):
        session.stop_and_verify(timeout=1)
    custody.verify_still_empty.side_effect = RuntimeError("repopulated")
    with pytest.raises(RuntimeError, match="repopulated"):
        session.stop_and_verify(timeout=1)
    custody.stop_and_verify.assert_called_once()
    child.wait.assert_called_once()


def test_reap_retry_rejects_incomplete_fresh_kernel_observation():
    child = Mock(returncode=None)
    child.wait.side_effect = subprocess.TimeoutExpired("worker", 1)
    custody = Mock()
    custody.stop_and_verify.return_value = {
        "process_tree_custody_verified": True,
        "empty_group_verified": True, "scope": "linux-cgroup-v2",
    }
    custody.verify_still_empty.return_value = custody.stop_and_verify.return_value
    session = LinuxFilmingSession("/group", child, custody)
    with pytest.raises(RuntimeError, match="worker exit unverified"):
        session.stop_and_verify(timeout=1)
    custody.verify_still_empty.return_value = {"empty_group_verified": False}
    with pytest.raises(RuntimeError, match="affirmative Linux"):
        session.stop_and_verify(timeout=1)
    custody.stop_and_verify.assert_called_once()
    child.wait.assert_called_once()


def test_failed_admission_recovery_retry_reuses_one_use_kernel_custody():
    """A timed-out reap must never reconstruct custody and kill a second time."""
    child = Mock(returncode=None)
    child.wait.side_effect = [subprocess.TimeoutExpired("worker", 1), 0]
    receipt = {
        "process_tree_custody_verified": True,
        "empty_group_verified": True,
        "scope": "linux-cgroup-v2",
    }
    error = FilmingCustodyInitializationError("/owned/leaf", child)
    with patch("backend.nvp_filming_linux_session.LinuxFilmingCgroup") as factory:
        factory.return_value.stop_and_verify.return_value = receipt
        factory.return_value.verify_still_empty.return_value = receipt
        with pytest.raises(RuntimeError, match="worker exit unverified"):
            error.reconcile_and_stop("/owned", timeout=1)
        child.returncode = -9
        result = error.reconcile_and_stop("/owned", timeout=1)
        assert result["worker_exit_verified"] is True
        factory.assert_called_once()
        factory.return_value.stop_and_verify.assert_called_once()
        assert factory.return_value.verify_still_empty.call_count == 2


def test_failed_admission_recovery_cannot_switch_delegated_root():
    child = Mock(returncode=None)
    child.wait.side_effect = subprocess.TimeoutExpired("worker", 1)
    receipt = {
        "process_tree_custody_verified": True,
        "empty_group_verified": True,
        "scope": "linux-cgroup-v2",
    }
    error = FilmingCustodyInitializationError("/owned/leaf", child)
    with patch("backend.nvp_filming_linux_session.LinuxFilmingCgroup") as factory:
        factory.return_value.stop_and_verify.return_value = receipt
        with pytest.raises(RuntimeError, match="worker exit unverified"):
            error.reconcile_and_stop("/owned", timeout=1)
        with pytest.raises(RuntimeError, match="delegated root changed"):
            error.reconcile_and_stop("/different", timeout=1)
        factory.assert_called_once()


def test_post_reap_repopulation_refuses_success():
    child = Mock(returncode=-9)
    custody = Mock()
    custody.stop_and_verify.return_value = {"process_tree_custody_verified": True, "empty_group_verified": True, "scope": "linux-cgroup-v2"}
    custody.verify_still_empty.side_effect = RuntimeError("repopulated after reap")
    with pytest.raises(RuntimeError, match="repopulated after reap"):
        LinuxFilmingSession("/group", child, custody).stop_and_verify(timeout=2)
    child.wait.assert_called_once()
    custody.stop_and_verify.assert_called_once()


def test_post_reap_incomplete_receipt_refuses_success():
    child = Mock(returncode=-9)
    custody = Mock()
    custody.stop_and_verify.return_value = {"process_tree_custody_verified": True, "empty_group_verified": True, "scope": "linux-cgroup-v2"}
    custody.verify_still_empty.return_value = {"empty_group_verified": False}
    with pytest.raises(RuntimeError, match="Post-reap kernel custody"):
        LinuxFilmingSession("/group", child, custody).stop_and_verify(timeout=2)
    child.wait.assert_called_once()
