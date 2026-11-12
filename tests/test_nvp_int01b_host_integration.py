"""INT-01B: canonical host/cgroup source admission into Wave 1.

Focused source tests only. No synthetic test is a kernel-custody, real
microphone, G03 confidentiality or physical-owner acceptance claim.
"""
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from backend.nvp_data_first_filming import NativeSceneSoundCapture
from backend.nvp_filming_cgroup_custody import (
    CgroupCustodyError, LinuxFilmingCgroup)
from backend.nvp_filming_host_bridge import launch_and_finish_linux_recording
from backend.nvp_filming_linux_session import FilmingCustodyInitializationError


def test_filming_service_requires_host_custody_before_capture():
    service = NativeSceneSoundCapture.__new__(NativeSceneSoundCapture)
    owned = object()
    supplied = lambda: []
    receipt = {"take_id": "canonical-film-take"}
    with patch(
        "backend.nvp_filming_host_bridge.finish_linux_recording_and_freeze",
        return_value=receipt,
    ) as finalizer:
        result = service.capture_supervised_linux(
            owned, "project", "take", recordings=supplied, timeout=3.,
            scene_id="scene01", scene_revision=1,
            camera_timeline_id="camera01", camera_timeline_revision=1,
            sound_timeline_id="sound01",
        )
    assert result is receipt
    finalizer.assert_called_once()
    args, kwargs = finalizer.call_args
    assert args == (owned, service, "project", "take")
    assert kwargs["recordings"] is supplied
    assert kwargs["timeout"] == 3.
    assert kwargs["scene_revision"] == 1


def test_filming_service_launches_only_via_trusted_host_entry():
    service = NativeSceneSoundCapture.__new__(NativeSceneSoundCapture)
    producer = lambda: []
    output = object()
    with patch(
        "backend.nvp_filming_host_bridge.launch_and_finish_linux_recording",
        return_value=output,
    ) as launch:
        result = service.launch_and_capture_supervised_linux(
            Path("/delegated"), "/reviewed/worker",
            ["/reviewed/worker", "--original"],
            "project", "take", recordings=producer)
    assert result is output
    launch.assert_called_once()
    assert launch.call_args.args[3] is service
    assert launch.call_args.kwargs["recordings"] is producer


def test_launch_then_finish_preserves_exact_host_worker_and_capture():
    native_session = object()
    capture = object()
    supplier = Mock(return_value=[])
    result = {"source_published": False}
    with patch(
        "backend.nvp_filming_linux_session.launch_linux_filming_session",
        return_value=native_session,
    ) as launcher, patch(
        "backend.nvp_filming_host_bridge.finish_linux_recording_and_freeze",
        return_value=result,
    ) as bridge:
        actual = launch_and_finish_linux_recording(
            Path("/delegated"), "/reviewed/worker",
            ["/reviewed/worker"], capture, "project", "take",
            recordings=supplier, timeout=2.)
    assert actual is result
    launcher.assert_called_once()
    bridge.assert_called_once_with(
        native_session, capture, "project", "take",
        recordings=supplier, timeout=2.)


def test_failed_native_session_admission_reconciles_original_handles_only():
    original_child = Mock()
    error = FilmingCustodyInitializationError(
        Path("/delegated/original"), original_child)
    capture = Mock()
    with patch(
        "backend.nvp_filming_linux_session.launch_linux_filming_session",
        side_effect=error,
    ), patch.object(error, "reconcile_and_stop",
                   return_value={"process_tree_custody_verified": True}
                   ) as recovered:
        with pytest.raises(RuntimeError, match="not admitted"):
            launch_and_finish_linux_recording(
                Path("/delegated"), "/reviewed/worker",
                ["/reviewed/worker"], capture, "project", "take",
                recordings=lambda: [], timeout=4.)
    recovered.assert_called_once_with(Path("/delegated"), timeout=4.)
    capture.capture.assert_not_called()
    assert error.child is original_child


def test_failed_native_admission_with_unverified_tree_never_publishes():
    error = FilmingCustodyInitializationError(
        Path("/delegated/original"), Mock())
    capture = Mock()
    with patch(
        "backend.nvp_filming_linux_session.launch_linux_filming_session",
        side_effect=error,
    ), patch.object(error, "reconcile_and_stop",
                   side_effect=RuntimeError("kernel group still populated")):
        with pytest.raises(RuntimeError, match="lacks verified"):
            launch_and_finish_linux_recording(
                Path("/delegated"), "/reviewed/worker",
                ["/reviewed/worker"], capture, "project", "take",
                recordings=lambda: [])
    capture.capture.assert_not_called()


def test_cached_empty_group_requires_fresh_kernel_state():
    custody = LinuxFilmingCgroup.__new__(LinuxFilmingCgroup)
    custody._consumed = True
    with patch.object(custody, "_verify_group_identity"), patch.object(
        custody, "_read_events", return_value="populated 0\nfrozen 0\n"
    ):
        observed = custody.verify_still_empty()
    assert observed["empty_group_verified"] is True
    assert observed["scope"] == "linux-cgroup-v2"
    with patch.object(custody, "_verify_group_identity"), patch.object(
        custody, "_read_events", return_value="populated 1\nfrozen 0\n"
    ):
        with pytest.raises(CgroupCustodyError, match="no longer empty"):
            custody.verify_still_empty()


def test_unconsumed_cgroup_cannot_claim_empty_tree():
    custody = LinuxFilmingCgroup.__new__(LinuxFilmingCgroup)
    custody._consumed = False
    with pytest.raises(CgroupCustodyError, match="No consumed"):
        custody.verify_still_empty()
