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
            session, capture, "p", "t", recordings=lambda: [{"pcm_chunks": iter((b'\x00\x00',))}],
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


@pytest.mark.parametrize("bad_batch", [[], [None] * 33, (), None])
def test_invalid_batch_still_stops_worker(bad_batch):
    with patch("backend.nvp_filming_host_bridge.LinuxFilmingSession") as S, patch(
        "backend.nvp_filming_host_bridge.NativeSceneSoundCapture") as C:
        session, capture = S(), C()
        session.stop_and_verify.return_value = GOOD
        with pytest.raises(ValueError, match="1..32"):
            finish_linux_recording_and_freeze(
                session, capture, "p", "t", recordings=lambda: bad_batch)
        session.stop_and_verify.assert_called_once()
        capture.capture.assert_not_called()


def test_invalid_recorder_callback_still_stops_worker():
    with patch("backend.nvp_filming_host_bridge.LinuxFilmingSession") as S, patch(
        "backend.nvp_filming_host_bridge.NativeSceneSoundCapture") as C:
        session, capture = S(), C()
        session.stop_and_verify.return_value = GOOD
        with pytest.raises(TypeError, match="supplier"):
            finish_linux_recording_and_freeze(
                session, capture, "p", "t", recordings=None)
        session.stop_and_verify.assert_called_once()
        capture.capture.assert_not_called()


def test_invalid_capture_service_still_stops_worker():
    with patch("backend.nvp_filming_host_bridge.LinuxFilmingSession") as S:
        session = S()
        session.stop_and_verify.return_value = GOOD
        with pytest.raises(TypeError, match="capture service"):
            finish_linux_recording_and_freeze(
                session, object(), "p", "t", recordings=lambda: [])
        session.stop_and_verify.assert_called_once()


def test_shutdown_callback_cannot_rewrite_recording_event_metadata():
    with patch("backend.nvp_filming_host_bridge.LinuxFilmingSession") as S, patch(
        "backend.nvp_filming_host_bridge.NativeSceneSoundCapture") as C:
        session, capture = S(), C()
        event = {"event_id": "original", "pcm_chunks": iter((b'\x00\x00',))}
        def shutdown(**kwargs):
            event["event_id"] = "tampered"
            event["start_tick"] = 999
            return GOOD
        session.stop_and_verify.side_effect = shutdown
        capture.capture.return_value = {"ok": True}
        finish_linux_recording_and_freeze(
            session, capture, "p", "t", recordings=lambda: [event], scene_id="scene")
        forwarded = capture.capture.call_args.kwargs["recordings"]
        assert forwarded[0]["event_id"] == "original"
        assert "start_tick" not in forwarded[0]
        assert forwarded[0] is not event


def test_malformed_recording_event_still_stops_worker():
    with patch("backend.nvp_filming_host_bridge.LinuxFilmingSession") as S, patch(
        "backend.nvp_filming_host_bridge.NativeSceneSoundCapture") as C:
        session, capture = S(), C()
        session.stop_and_verify.return_value = GOOD
        with pytest.raises(ValueError, match="typed dictionaries"):
            finish_linux_recording_and_freeze(
                session, capture, "p", "t", recordings=lambda: [None])
        session.stop_and_verify.assert_called_once()
        capture.capture.assert_not_called()


def test_shutdown_cannot_rewrite_nested_clock_attestation():
    with patch("backend.nvp_filming_host_bridge.LinuxFilmingSession") as S, patch(
        "backend.nvp_filming_host_bridge.NativeSceneSoundCapture") as C:
        session, capture = S(), C()
        pcm = iter((b"\x00\x00",))
        event = {"pcm_chunks": pcm, "source_sync": {"anchors": [{"tick": 42}]},
                 "clock_evidence": {"proof": ["original"]}}
        def shutdown(**kwargs):
            event["source_sync"]["anchors"][0]["tick"] = 999
            event["clock_evidence"]["proof"][0] = "altered"
            return GOOD
        session.stop_and_verify.side_effect = shutdown
        finish_linux_recording_and_freeze(
            session, capture, "p", "t", recordings=lambda: [event])
        forwarded = capture.capture.call_args.kwargs["recordings"][0]
        assert forwarded["source_sync"]["anchors"][0]["tick"] == 42
        assert forwarded["clock_evidence"]["proof"] == ["original"]
        assert list(forwarded["pcm_chunks"]) == [b'\x00\x00']


def test_shutdown_cannot_rewrite_new_nested_metadata_fields():
    with patch("backend.nvp_filming_host_bridge.LinuxFilmingSession") as S, patch(
        "backend.nvp_filming_host_bridge.NativeSceneSoundCapture") as C:
        session, capture = S(), C()
        pcm = iter((b"\x00\x00",))
        event = {"pcm_chunks": pcm, "actor_metadata": {"markers": [{"tick": 17}]},
                 "custom_tags": ["original"]}
        def shutdown(**kwargs):
            event["actor_metadata"]["markers"][0]["tick"] = 1000
            event["custom_tags"].append("altered")
            return GOOD
        session.stop_and_verify.side_effect = shutdown
        finish_linux_recording_and_freeze(
            session, capture, "p", "t", recordings=lambda: [event])
        forwarded = capture.capture.call_args.kwargs["recordings"][0]
        assert forwarded["actor_metadata"]["markers"][0]["tick"] == 17
        assert forwarded["custom_tags"] == ["original"]
        assert list(forwarded["pcm_chunks"]) == [b'\x00\x00']


def test_unsnapshotable_metadata_still_reaps_and_denies_take():
    class Uncopyable:
        def __deepcopy__(self, memo):
            raise ValueError("metadata cannot be frozen")
    with patch("backend.nvp_filming_host_bridge.LinuxFilmingSession") as S, patch(
        "backend.nvp_filming_host_bridge.NativeSceneSoundCapture") as C:
        session, capture = S(), C()
        session.stop_and_verify.return_value = GOOD
        with pytest.raises(ValueError, match="cannot be frozen"):
            finish_linux_recording_and_freeze(
                session, capture, "p", "t", recordings=lambda: [
                    {"pcm_chunks": iter((b'\x00\x00',)), "custom": Uncopyable()}])
        session.stop_and_verify.assert_called_once()
        capture.capture.assert_not_called()


def test_shutdown_cannot_expand_capture_source_consent_or_options():
    with patch("backend.nvp_filming_host_bridge.LinuxFilmingSession") as S, patch(
        "backend.nvp_filming_host_bridge.NativeSceneSoundCapture") as C:
        session, capture = S(), C()
        options = {"allowed_sources": ["microphone-A"], "consent": {"scope": ["scene-1"]}}
        def shutdown(**kwargs):
            options["allowed_sources"].append("microphone-B")
            options["consent"]["scope"].append("scene-2")
            return GOOD
        session.stop_and_verify.side_effect = shutdown
        finish_linux_recording_and_freeze(
            session, capture, "p", "t",
            recordings=lambda: [{"pcm_chunks": iter((b'\x00\x00',))}], **options)
        forwarded = capture.capture.call_args.kwargs
        assert forwarded["allowed_sources"] == ["microphone-A"]
        assert forwarded["consent"] == {"scope": ["scene-1"]}


def test_unsnapshotable_capture_options_still_reap_and_deny_take():
    class Uncopyable:
        def __deepcopy__(self, memo):
            raise ValueError("consent snapshot failed")
    with patch("backend.nvp_filming_host_bridge.LinuxFilmingSession") as S, patch(
        "backend.nvp_filming_host_bridge.NativeSceneSoundCapture") as C:
        session, capture = S(), C()
        session.stop_and_verify.return_value = GOOD
        with pytest.raises(ValueError, match="consent snapshot failed"):
            finish_linux_recording_and_freeze(
                session, capture, "p", "t",
                recordings=lambda: [{"pcm_chunks": iter((b'\x00\x00',))}],
                consent=Uncopyable())
        session.stop_and_verify.assert_called_once()
        capture.capture.assert_not_called()


def test_pcm_is_drained_before_worker_shutdown():
    with patch("backend.nvp_filming_host_bridge.LinuxFilmingSession") as S, patch(
        "backend.nvp_filming_host_bridge.NativeSceneSoundCapture") as C:
        session, capture = S(), C()
        live = {"worker": True}
        def pcm():
            assert live["worker"], "Original PCM consumed after worker termination"
            yield b"\x00\x00"
        def shutdown(**kwargs):
            live["worker"] = False
            return GOOD
        session.stop_and_verify.side_effect = shutdown
        finish_linux_recording_and_freeze(session, capture, "p", "t",
            recordings=lambda: [{"pcm_chunks": pcm()}])
        forwarded = capture.capture.call_args.kwargs["recordings"][0]
        assert list(forwarded["pcm_chunks"]) == [b"\x00\x00"]


def test_invalid_pcm_still_stops_worker_and_denies_publication():
    with patch("backend.nvp_filming_host_bridge.LinuxFilmingSession") as S, patch(
        "backend.nvp_filming_host_bridge.NativeSceneSoundCapture") as C:
        session, capture = S(), C()
        session.stop_and_verify.return_value = GOOD
        with pytest.raises(ValueError, match="PCM16LE"):
            finish_linux_recording_and_freeze(session, capture, "p", "t",
                recordings=lambda: [{"pcm_chunks": iter((b"\x00",))}])
        session.stop_and_verify.assert_called_once()
        capture.capture.assert_not_called()


def test_shutdown_spool_tampering_denies_publication_before_capture():
    import tempfile
    real_spool = tempfile.SpooledTemporaryFile
    opened = []
    def spool_factory(**kwargs):
        stream = real_spool(**kwargs)
        opened.append(stream)
        return stream
    with patch("backend.nvp_filming_host_bridge.LinuxFilmingSession") as S, patch(
        "backend.nvp_filming_host_bridge.NativeSceneSoundCapture") as C, patch(
        "backend.nvp_filming_host_bridge.tempfile.SpooledTemporaryFile",
        side_effect=spool_factory):
        session, capture = S(), C()
        def shutdown(**kwargs):
            assert len(opened) == 1
            opened[0].seek(4)
            opened[0].write(b"\\x01\\x01")
            return GOOD
        session.stop_and_verify.side_effect = shutdown
        with pytest.raises(RuntimeError, match="spool integrity"):
            finish_linux_recording_and_freeze(
                session, capture, "p", "t",
                recordings=lambda: [{"pcm_chunks": iter((b"\\x00\\x00",))}])
        session.stop_and_verify.assert_called_once()
        capture.capture.assert_not_called()
        assert opened[0].closed
