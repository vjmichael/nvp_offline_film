"""Original G09F project lock meets newer W1-G native desktop camera state.

Portable dispatch/negative tests ONLY; not independent Windows WebView, SCM,
physical microphone, EFS, AppContainer or 48 kHz source acceptance.
"""
from __future__ import annotations
from types import SimpleNamespace
import pytest
from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge


def bridge(locked):
    instance=object.__new__(TrustedDesktopCameraBridge)
    instance._project_lock_check=lambda: locked[0]
    instance._closing=False
    instance.origin="http://127.0.0.1:12345"
    instance.window=SimpleNamespace(get_current_url=lambda: instance.origin+"/")
    instance._data_av_controller=None
    instance._original_capture_controller=None
    return instance


def test_protected_film_denies_native_camera_even_with_valid_local_window():
    state=[True]
    b=bridge(state)
    with pytest.raises(PermissionError, match="protected"):
        b._native_window()
    state[0]=False
    assert b._native_window() is b.window


def test_protected_film_stop_never_exposes_pcm_or_authorizes_publication():
    status={"closed":False}
    b=bridge([True])
    b._data_av_controller=SimpleNamespace(close=lambda: status.__setitem__("closed",True))
    assert b.data_av_stop("source-secret") == {
        "status":"STOPPED","source_exposed":False,"original_modified":False}
    assert status["closed"] is True


def test_protected_film_cancel_only_requests_recovery_and_never_claims_reap():
    status={"closed":False}
    b=bridge([True])
    b._original_capture_controller=SimpleNamespace(
        close=lambda:status.__setitem__("closed",True))
    assert b.data_av_capture_cancel()=={
        "status":"CANCELLATION_REQUESTED","terminal_verified":False,
        "source_exposed":False}
    assert status["closed"] is True


def test_untrusted_project_lock_callback_rejected_before_native_authority():
    from backend.nvp_film_index import FilmIndex
    from tempfile import TemporaryDirectory
    from pathlib import Path
    with TemporaryDirectory() as tmp:
        with pytest.raises(TypeError,match="trusted host callback"):
            TrustedDesktopCameraBridge(
                FilmIndex(Path(tmp)),origin="http://127.0.0.1:12345",
                project_lock_check="browser provided")
