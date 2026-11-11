"""DA-03 trusted host publication boundary contract."""
import pytest
from unittest.mock import Mock, patch
from backend.nvp_filming_host_bridge import finish_linux_recording_and_freeze

GOOD = {"process_tree_custody_verified": True, "empty_group_verified": True,
        "worker_exit_verified": True, "scope": "linux-cgroup-v2"}


def test_host_freezes_only_after_verified_shutdown():
    order = []
    with patch("backend.nvp_filming_host_bridge.LinuxFilmingSession") as S, patch(
        "backend.nvp_filming_host_bridge.NativeSceneSoundCapture") as C:
        session = S()
        capture = C()
        session.stop_and_verify.side_effect = lambda **kw: (order.append("stop"), GOOD)[1]
        capture.capture.side_effect = lambda *a, **kw: (order.append("freeze"), {"ok": True})[1]
        assert finish_linux_recording_and_freeze(
            session, capture, "p", "t", recordings=lambda: [{"pcm_chunks": iter(())}],
            scene_id="scene") == {"ok": True}
        assert order == ["stop", "freeze"]


@pytest.mark.parametrize("receipt", [
    {}, {"process_tree_custody_verified": True, "empty_group_verified": True,
         "worker_exit_verified": False, "scope": "linux-cgroup-v2"},
])
def test_host_denies_publication_without_full_custody(receipt):
    with patch("backend.nvp_filming_host_bridge.LinuxFilmingSession") as S, patch(
        "backend.nvp_filming_host_bridge.NativeSceneSoundCapture") as C:
        session, capture = S(), C()
        session.stop_and_verify.return_value = receipt
        with pytest.raises(RuntimeError, match="custody unverified"):
            finish_linux_recording_and_freeze(session, capture, "p", "t", recordings=lambda: [])
        capture.capture.assert_not_called()


def test_recorder_error_still_reaps_worker_without_publishing():
    with patch("backend.nvp_filming_host_bridge.LinuxFilmingSession") as S, patch(
        "backend.nvp_filming_host_bridge.NativeSceneSoundCapture") as C:
        session, capture = S(), C()
        session.stop_and_verify.return_value = GOOD
        def broken():
            raise ValueError("device lost")
        with pytest.raises(ValueError, match="device lost"):
            finish_linux_recording_and_freeze(session, capture, "p", "t", recordings=broken)
        session.stop_and_verify.assert_called_once()
        capture.capture.assert_not_called()


def test_shutdown_failure_denies_publication():
    with patch("backend.nvp_filming_host_bridge.LinuxFilmingSession") as S, patch(
        "backend.nvp_filming_host_bridge.NativeSceneSoundCapture") as C:
        session, capture = S(), C()
        session.stop_and_verify.side_effect = RuntimeError("kernel denied")
        with pytest.raises(RuntimeError, match="kernel denied"):
            finish_linux_recording_and_freeze(session, capture, "p", "t", recordings=lambda: [])
        capture.capture.assert_not_called()
