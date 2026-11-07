"""WO5: genuine visible installed NVP.exe WebView2 picture + mastered audio.

Invoked only by CLI smoke from a real NSIS-installed Windows binary.
A host-only CI fixture predecodes every JPEG2000/PCM24 block from an
independently validated SMPTE DCP; NVP's REAL FinishedFilmPlaybackPanel
drives the actual installed WebView2 Canvas and WebAudio clock for the
ENTIRE continuous published test timeline. No browser/AI project access,
no synthetic substituted pixels/audio and no phantom FilmIndex consent.

Separate from (1) on-demand decoder throughput, (2) real 30-minute
human authored film, (3) audible calibrated speaker verification.
"""
from __future__ import annotations
from pathlib import Path
import json
import os
import shutil
import tempfile
import time
from threading import Event

from backend.nvp_film_index import FilmIndex
from backend.nvp_wo5_codec_binding import desktop_finished_decoder_provider
from backend.nvp_wo5_desktop_bridge import TrustedDesktopWO5Bridge
from tools.nvp_wo5_visible_finished_fixture import (
    InstalledPublishedDCPFixture, CI_FORMAT, CI_FEATURE)
from tools.nvp_desktop_alpha import create_app, serve


def _native_stage(label):
    """Persist progress even if the installed GUI is killed by CI timeout."""
    path=os.environ.get("NVP_NATIVE_SMOKE_DIAGNOSTICS")
    if not path or not isinstance(label,str) or len(label)>90:
        return
    target=Path(path)
    if (not target.is_absolute() or target.is_symlink() or
            not target.parent.is_dir()):
        return
    with target.open("a",encoding="utf8") as stream:
        stream.write("WO5_VISIBLE_STAGE="+label+"\n")
        stream.flush()
        os.fsync(stream.fileno())

class InstalledRealFinishedCIHost(TrustedDesktopWO5Bridge):
    """Test-only subclass: normal installed NVP does NOT expose descriptor."""

    def __init__(self,index,origin,fixture,project_id):
        super().__init__(index,origin=origin)
        self.fixture=fixture
        self.project_id=project_id

    def wo5_ci_published_mxf_descriptor(self):
        self._wo5_project(self.project_id)
        return {
            "format":CI_FORMAT,
            "source":"REAL_PUBLISHED_DCP_PICTURE_AND_SOUND_MXF",
            "project_id":self.project_id,
            "feature_id":CI_FEATURE,
            "frame_count":self.fixture.total,
            "reel_count":len(self.fixture.reels),
            "cached_decode_source":"PUBLISHED_SMPTE_MXF_NOT_FILMINDEX_ORIGINAL",
            "human_director_grant_obtained":False,
            "production_accepted":False,
        }

    def wo5_film_capabilities(self):
        self._native_window()
        return {
            "format":"nvp.wo5.finished_dcp_pcm24_picture_review.v1",
            "native_finished_mxf_decode_configured":True,
            "native_ci_fixture_only":True,
            "FFmpeg_used":False,
            "source_take_only":False,
            "finished_picture_and_sound_from_published_mxf":True,
            "actual_sustained_24fps_verified":False,
            "installed_codec_bundle_verified":True,
            "production_accepted":False,
        }

    def wo5_film_begin(self,project_id,feature_id):
        self._wo5_project(project_id)
        return self.fixture.begin(project_id,feature_id,self.project_id)

    def wo5_film_window(self,session_id,first_frame,count=4):
        self._native_window()
        return self.fixture.window(session_id,first_frame,count)

    def wo5_film_frame(self,session_id,frame_index):
        self._native_window()
        return self.fixture.window(session_id,frame_index,1)["frames"][0]

    def wo5_film_stop(self,session_id):
        self._native_window()
        return self.fixture.stop(session_id)

    def _close(self):
        self.fixture.close()
        super()._close()


def _native_os_user_click_finished_play(window,title):
    """Genuine OS mouse input into real Windows WebView2, not JS .click().

    Programmatic DOM .click() does NOT grant Chromium transient user
    activation for WebAudio; NVP's real creator button must be clicked
    through the visible OS window. The host-selected UI test owns this
    disposable desktop window. This is not a human creative approval.
    """
    import win32api
    import win32con
    import win32gui
    rectangle=window.evaluate_js(
        "(()=>{const b=[...document.querySelectorAll('button')]"
        ".find(x=>x.textContent.includes('Request native permission and play finished DCP'));"
        "if(!b||b.disabled)return null;"
        "b.scrollIntoView({block:'center'});"
        "const r=b.getBoundingClientRect();"
        "return {x:r.x,y:r.y,w:r.width,h:r.height,"
        "vw:window.innerWidth,vh:window.innerHeight};})()")
    if (not isinstance(rectangle,dict) or
            any(type(rectangle.get(k)) not in (int,float)
                for k in ("x","y","w","h","vw","vh")) or
            rectangle["w"]<20 or rectangle["h"]<10):
        return False
    if (rectangle["x"]<0 or rectangle["y"]<0 or
            rectangle["x"]+rectangle["w"]>rectangle["vw"]+2 or
            rectangle["y"]+rectangle["h"]>rectangle["vh"]+2):
        raise RuntimeError("Actual WebView2 film play button not on screen")
    hwnd=win32gui.FindWindow(None,title)
    if not hwnd:
        raise RuntimeError("Could not find real NVP WebView2 top-level window")
    win32gui.ShowWindow(hwnd,win32con.SW_SHOWNORMAL)
    try:win32gui.SetForegroundWindow(hwnd)
    except Exception:
        # Windows foreground focus policy is outside NVP's control.
        # If the user-gesture click is refused, the WebAudio gate fails.
        pass
    client=win32gui.GetClientRect(hwnd)
    origin=win32gui.ClientToScreen(hwnd,(0,0))
    scale=(client[2]-client[0])/rectangle["vw"]
    if not .7<=scale<=3:
        raise RuntimeError("Native window CSS-pixel/desktop-pixel mapping invalid")
    x=round(origin[0]+(rectangle["x"]+rectangle["w"]/2)*scale)
    y=round(origin[1]+(rectangle["y"]+rectangle["h"]/2)*scale)
    win32api.SetCursorPos((x,y))
    time.sleep(.12)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN,0,0,0,0)
    time.sleep(.09)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP,0,0,0,0)
    return True


def run_installed_visible_finished_smoke(bundle_root):
    import webview
    folder=os.environ.get("NVP_WO5_SMOKE_DCP_DIR")
    if not folder:
        raise RuntimeError("CI must provide actual already published SMPTE DCP")
    provider=desktop_finished_decoder_provider(bundle_root)
    if not callable(provider):
        raise RuntimeError("NVP.exe does not contain the compiled legal codec pin")
    artifact=os.environ.get("NVP_WO5_VISIBLE_AV_REPORT")
    target=Path(artifact) if artifact else None
    if target and (not target.is_absolute() or target.exists() or
                   target.is_symlink() or not target.parent.is_dir()):
        raise PermissionError("Visible test must use new trusted CI report file")
    root=Path(tempfile.mkdtemp(prefix="nvp-wo5-visible-real-mxf-"))
    old_home=os.environ.get("NVP_HOME")
    os.environ["NVP_HOME"]=str(root/"Projects")
    result={
        "format":"nvp.wo5.installed_visible_webview_real_final_av.v1",
        "status":"FAILED_BEFORE_VISIBLE_PLAYBACK",
        "real_installed_exe":True,
        "real_published_dcp_picture_sound":False,
        "uninterrupted_webview2_canvas_web_audio":False,
        "real_audio_device_speaker_audibly_verified":False,
        "original_source_filminindex_approved":False,
        "director_creative_review_accepted":False,
        "production_accepted":False,
        "ffmpeg_used":False,
    }
    fixture=None;bridge=None;server=None;worker=None;sock=None
    try:
        _native_stage("fixture_initializing")
        fixture=InstalledPublishedDCPFixture(
            Path(folder),provider,max_frames=720)
        _native_stage("fixture_predecode_start")
        rehearsal=fixture.prepare()
        _native_stage("fixture_predecode_complete")
        result["native_fixture"]=rehearsal
        result["real_published_dcp_picture_sound"]=True
        _native_stage("native_app_create")
        app=create_app()
        from backend.nvp_api import studio
        project=studio.create_project(
            "NVP Installed Published DCP AV Test",
            "Native original video/audio fixture not a director movie")
        server,worker,port,sock=serve(app)
        base=f"http://127.0.0.1:{port}"
        bridge=InstalledRealFinishedCIHost(
            FilmIndex(studio),base,fixture,project["id"])
        window=webview.create_window(
            "NVP Installed — Published MXF Picture and Audio Device Clock",
            base+"/",
            width=1280,height=800,min_size=(960,600),
            js_api=bridge)
        bridge._attach_window(window)
        _native_stage("webview2_window_created")
        ready=Event()
        window.events.loaded += lambda:ready.set()
        progress={"painted_positions":[],"states":[]}
        def inspect():
            try:
                if not ready.wait(timeout=45):
                    raise RuntimeError("Real installed WebView2 page did not load")
                until=time.monotonic()+40
                mounted=False
                while time.monotonic()<until:
                    mounted=window.evaluate_js(
                        "Boolean(document.querySelector("
                        "'main[aria-label=\"Installed native finished DCP visual and WebAudio verification\"]') "
                        "&& document.querySelector('canvas[aria-label=\"Decoded finished DCP picture at its audio-clock Film Time\"]'))")
                    if mounted:
                        break
                    time.sleep(.15)
                if not mounted:
                    raise RuntimeError("Actual finished film React panel not mounted in installed WebView2")
                _native_stage("react_finished_player_mounted")
                result["real_react_finished_player_mounted"]=True
                until=time.monotonic()+30
                clicked=False
                while time.monotonic()<until:
                    clicked=_native_os_user_click_finished_play(
                        window,"NVP Installed — Published MXF Picture and Audio Device Clock")
                    if clicked:
                        break
                    time.sleep(.15)
                if not clicked:
                    raise RuntimeError("Installed real film player not enabled after native codec admission")
                _native_stage("real_os_mouse_play_clicked")
                result["real_player_button_invoked_in_visible_window"]=True
                result["os_native_mouse_user_gesture_not_programmatic_dom_click"]=True
                # NVP's actual WebAudio clock drives all presented film
                # positions. This checks continuous real Canvas draw count,
                # not elapsed wall time or just native decoding speed.
                start=time.monotonic()
                limit=start+max(75,fixture.total/24+65)
                state=""
                while time.monotonic()<limit:
                    event=window.evaluate_js(
                        "(()=>{const s=document.querySelector("
                        "'[aria-label=\"Finished film playback state\"]');"
                        "const o=document.querySelector('output[data-nvp-film-av-receipt]');"
                        "const e=document.querySelector('p[role=\"alert\"]');"
                        "return {state:s?s.textContent:'',"
                        "output:o?o.getAttribute('data-nvp-film-av-receipt'):null,"
                        "error:e?e.textContent:null, "
                        "frame:(document.body.textContent.match(/Output frame:\\s*(\\d+)/)||[])[1]||null};})()")
                    if not isinstance(event,dict):
                        raise RuntimeError("WebView2 JS runtime returned no native playback state")
                    state=event.get("state") or ""
                    if state and state not in progress["states"]:
                        progress["states"].append(state)
                    pos=event.get("frame")
                    if pos is not None:
                        progress["painted_positions"].append(int(pos))
                    if state.startswith("State: FAILED") or (
                            event.get("error") and
                            "WebView2" not in event["error"]):
                        raise RuntimeError("Native WebAudio/canvas player failed: "+
                                           str(event.get("error") or state))
                    if event.get("output"):
                        receipt=json.loads(event["output"])
                        result["presentation_receipt"]=receipt
                        break
                    time.sleep(.12)
                else:
                    raise RuntimeError("Visible installed final movie failed to complete before deadline: "+state)
                _native_stage("native_web_audio_canvas_receipt_created")
                receipt=result["presentation_receipt"]
                if (receipt["canvasFramesDrawn"]!=fixture.total or
                    receipt["masteredPcmWindowsQueued"]!=fixture.total or
                    receipt["first"]!=0 or
                    receipt["last"]!=fixture.total-1 or
                    receipt["continuousCanvasTimeline"] is not True or
                    receipt["webAudioNonSilentRenderCallbacks"]<1 or
                    receipt["maxPictureAudioOffsetMs"]>100 or
                    receipt["audioContextElapsedSeconds"]<
                        fixture.total/24-0.002 or
                    receipt["audibleSpeakersIndependentlyVerified"] is not False or
                    receipt["originalFilmAccepted"] is not False):
                    raise RuntimeError("Real WebView2 native clock receipt lacks full published frame/sound continuity")
                pixels=window.evaluate_js(
                    "(()=>{const c=document.querySelector('canvas[aria-label="
                    "\"Decoded finished DCP picture at its audio-clock Film Time\"]');"
                    "if(!c||c.width<1||c.height<1)return null;"
                    "return [...c.getContext('2d').getImageData("
                    "Math.floor(c.width/2),Math.floor(c.height/2),1,1).data];})()")
                if not isinstance(pixels,list) or len(pixels)!=4 or pixels[3]!=255:
                    raise RuntimeError("No real final image pixels painted to WebView2 canvas")
                result.update({
                    "status":"VISIBLE_INSTALLED_PUBLISHED_DCP_CANVAS_AUDIO_CLOCK_PASSED",
                    "uninterrupted_webview2_canvas_web_audio":True,
                    "actual_webview2_canvas_center_rgba":pixels,
                    "actual_presentation_wall_seconds":round(time.monotonic()-start,3),
                    "real_scene_and_audio_untouched":True,
                    "verified_human_audible_speakers":False,
                    "real_time_native_decode_during_play":False,
                    "real_installed_sustained_24fps_picture_sound_display":True,
                    "independently_observed_physical_cinema_av":False,
                })
            except Exception as error:
                _native_stage("visible_playback_failed")
                result["status"]="FAILED_VISIBLE_INSTALLED_AV"
                result["failure"]=str(error)
            finally:
                try:window.destroy()
                except Exception:pass
        _native_stage("webview2_message_loop_start")
        webview.start(func=inspect,gui="edgechromium",debug=False)
        _native_stage("webview2_message_loop_returned")
        result["observed_states"]=progress["states"]
        result["position_sample_count"]=len(progress["painted_positions"])
    finally:
        if bridge:
            try:bridge._close()
            except Exception as error:result["cleanup_error"]=str(error)
        elif fixture:
            fixture.close()
        if server:
            server.should_exit=True
        if worker:
            worker.join(timeout=15)
        if sock:
            sock.close()
        if old_home is None:os.environ.pop("NVP_HOME",None)
        else:os.environ["NVP_HOME"]=old_home
        shutil.rmtree(root,ignore_errors=True)
        report=json.dumps(result,indent=2,sort_keys=True)+"\n"
        # Real installed NVP.exe is a windowed PyInstaller executable,
        # where sys.stdout can be None. Never let diagnostic printing
        # prevent an independently inspectable JSON acceptance receipt.
        import sys
        if sys.stdout is not None:
            print("NVP_WO5_VISIBLE_INSTALLED_AV_EVIDENCE="+report,flush=True)
        if target:
            target.write_text(report,encoding="utf8")
        _native_stage("visible_smoke_report_written")
    if result["status"]!="VISIBLE_INSTALLED_PUBLISHED_DCP_CANVAS_AUDIO_CLOCK_PASSED":
        raise RuntimeError(result.get("failure","Native visible NVP.exe film playback was not proven"))
    return 0
