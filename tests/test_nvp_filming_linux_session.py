"""DA-03 host launch/custody composition contracts; not kernel acceptance."""
from unittest.mock import Mock, patch

import pytest

from backend.nvp_filming_linux_session import (
    LinuxFilmingSession, launch_linux_filming_session,
)


def test_launch_retains_actual_child_and_custody():
    child = Mock()
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
    session = LinuxFilmingSession("/group", child, custody)
    with pytest.raises(RuntimeError, match="populated"):
        session.stop_and_verify()
    child.wait.assert_not_called()


def test_stop_returns_tree_and_worker_receipts():
    child = Mock(returncode=-9)
    custody = Mock()
    custody.stop_and_verify.return_value = {
        "process_tree_custody_verified": True, "empty_group_verified": True}
    session = LinuxFilmingSession("/group", child, custody)
    result = session.stop_and_verify(timeout=2)
    assert result["process_tree_custody_verified"]
    assert result["worker_exit_verified"]
    assert result["worker_returncode"] == -9
    child.wait.assert_called_once_with(timeout=2)


def test_failed_custody_construction_does_not_claim_success():
    with patch("backend.nvp_filming_linux_session.create_private_group_and_launch",
               return_value=("/group", Mock())), patch(
               "backend.nvp_filming_linux_session.LinuxFilmingCgroup",
               side_effect=RuntimeError("not delegated")):
        with pytest.raises(RuntimeError, match="reconcile"):
            launch_linux_filming_session("/root", "/bin/true", ["/bin/true"])
