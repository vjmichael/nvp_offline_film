"""Original-source fixture adapter for the EXISTING trusted native PNG path.

This test-only OS picker and confirmation substitutes for an installed window,
NOT for FilmIndex, real USD, exact source revisions or PNG verification.
It never grants generic asset publishing or external renderer authority.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import sys

from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge


def original_png_approved_from_native_window(index,pid,aid,source,png,*,
                                             channel="baseColor"):
    assert channel in ("baseColor","roughness")
    assert type(png) is bytes and png.startswith(b"\x89PNG\r\n\x1a\n")
    exact={
        "project_id":pid,"asset_id":aid,
        "source_revision":source["revision"],
        "source_document_sha256":source["document_sha256"]}
    with TemporaryDirectory(prefix="nvp-real-original-native-picker-") as temp:
        file=Path(temp)/"native-source.png"
        file.write_bytes(png)
        shown=[]
        selection=[]
        window=SimpleNamespace(
            get_current_url=lambda:"http://127.0.0.1:19991/",
            create_file_dialog=lambda *a,**k:
                (selection.append((a,k)) or [str(file)]),
            create_confirmation_dialog=lambda title,message:
                (shown.append((title,message)) or True))
        bridge=object.__new__(TrustedDesktopCameraBridge)
        bridge.index=index
        bridge.origin="http://127.0.0.1:19991"
        bridge.window=window
        bridge._project_lock_check=lambda:False
        bridge._closing=False
        fake_webview=SimpleNamespace(
            FileDialog=SimpleNamespace(OPEN="trusted-test-only-native-OPEN"))
        with patch.dict(sys.modules,{"webview":fake_webview}):
            receipt=(bridge.data_av_import_original_mesh_texture(exact)
                     if channel=="baseColor" else
                     bridge.data_av_import_original_mesh_roughness(exact))
        assert len(selection)==1, "No forged/replayed OS file picker"
        assert len(shown)==1, "Exactly one native original source confirmation"
        assert source["document_sha256"] in shown[0][1]
        assert receipt["status"] in (
            "ORIGINAL_SOURCE_TEXTURE_BOUND","ORIGINAL_ROUGHNESS_SOURCE_BOUND")
        assert receipt["source_asset_sha256"]==source["document_sha256"]
        assert receipt["source_revision"]==source["revision"]
        assert receipt["revision"]==source["revision"]+1
        assert receipt["native_source_reopened"] is True
        assert receipt["original_modified"] is False
        assert receipt["film_master_approved"] is False
    return index.read_revision(pid,aid,receipt["revision"])
