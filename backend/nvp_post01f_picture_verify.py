"""POST-01F independent host picture frame/PTS/audio verifier.

Executes only SHA-pinned installed FFmpeg/ffprobe at the explicitly permitted
external media boundary. It decodes each picture frame to a checksum, not
merely trusts a container header, frame-count tag, or worker result.json.
No source/master mutation; original PCM is never an input.
"""
from __future__ import annotations

from fractions import Fraction
from pathlib import Path
import re
import subprocess

from backend.nvp_post01f_ltx_native_handoff import MAX_PICTURE, digest_file, _sha
from backend.nvp_w1g_owned_subprocess import run_owned_subprocess
from backend.nvp_post01f_ltx_broker import MAX_PROBE

FRAME_RE = re.compile(r"[0-9a-f]{32}\Z")
MAX_FRAMEMD5 = 768 * 1024


def verify_picture_frames(path: Path, plan: dict, expected_sha256: str, *,
                          ffmpeg: Path, ffmpeg_sha256: str,
                          ffprobe: Path, ffprobe_sha256: str) -> dict:
    source = Path(path)
    if source.is_symlink() or not source.is_file() or digest_file(source, MAX_PICTURE) != _sha(expected_sha256):
        raise PermissionError("Original worker picture changed before independent decode")
    for executable, expected in ((ffmpeg,ffmpeg_sha256),(ffprobe,ffprobe_sha256)):
        if (not Path(executable).is_absolute() or Path(executable).is_symlink() or
            digest_file(Path(executable), 256 * 1024 * 1024) != _sha(expected)):
            raise PermissionError("Independent picture decoder executable is unpinned")
    # This independent verifier runs in the protected desktop host, NOT the
    # SCM-owned model AppContainer. Every ffprobe/ffmpeg process therefore
    # uses W1-G's original Windows Job/release-fence subprocess broker.
    command_probe = [str(ffprobe), '-v', 'error', '-count_frames', '-show_entries',
                     'stream=nb_read_frames,index,codec_type,width,height,avg_frame_rate',
                     '-of', 'json', str(source)]
    checked = run_owned_subprocess(command_probe, cwd=str(source.parent),
                                   stdin=subprocess.DEVNULL, capture_output=True,
                                   timeout=90, check=True)
    if not isinstance(checked.stdout, bytes) or len(checked.stdout) > MAX_PROBE:
        raise PermissionError('Independent pinned native media probe unbounded')
    import json
    value = json.loads(checked.stdout)
    streams = value.get('streams')
    if type(streams) is not list or not streams:
        raise PermissionError('Native media probe returned no streams')
    videos = [v for v in streams if v.get('codec_type') == 'video']
    audio = [v for v in streams if v.get('codec_type') == 'audio']
    if len(videos) != 1 or len(videos) + len(audio) != len(streams):
        raise PermissionError('Native picture has unreviewed streams')
    try:
        from fractions import Fraction
        v = videos[0]
        metadata = {'frames': int(v['nb_read_frames']),
                    'fps': Fraction(v['avg_frame_rate']),
                    'width': v['width'], 'height': v['height'],
                    'audio_streams': len(audio)}
    except (KeyError, ValueError, ZeroDivisionError) as exc:
        raise PermissionError('Native picture probe geometry or FPS missing') from exc
    if (metadata["frames"] != plan["display_frames"] or metadata["fps"] != Fraction(24,1)
        or metadata["width"] != plan["width"] or metadata["height"] != plan["height"]
        or metadata["audio_streams"] != 0):
        raise PermissionError("Native picture geometry, timing or audio streams invalid")
    command = [str(ffmpeg), "-hide_banner", "-v", "error", "-nostdin", "-i", str(source),
               "-map", "0:v:0", "-an", "-sn", "-dn", "-fps_mode", "passthrough",
               "-f", "framemd5", "-"]
    result = run_owned_subprocess(command, cwd=str(source.parent), stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=180, check=True)
    if len(result.stdout) > MAX_FRAMEMD5:
        raise PermissionError("Excessive independent native frame readback")
    lines = [x.strip() for x in result.stdout.decode("ascii").splitlines()]
    timebase = [x for x in lines if x.startswith("#tb 0:")]
    frames = [x for x in lines if x and not x.startswith("#")]
    if len(timebase) != 1 or len(frames) != plan["display_frames"]:
        raise PermissionError("Independent decoder did not return exact expected frames")
    try:
        tb = Fraction(timebase[0].split(":",1)[1].strip())
    except (ValueError, ZeroDivisionError) as exc:
        raise PermissionError("Native decoded frame timebase invalid") from exc
    if tb <= 0:
        raise PermissionError("Non-positive picture frame timebase")
    for idx,row in enumerate(frames):
        fields = [f.strip() for f in row.split(",")]
        if len(fields) != 6 or fields[0] != "0" or not FRAME_RE.fullmatch(fields[5]):
            raise PermissionError("Decoded picture checksum row invalid")
        try:
            pts = int(fields[2])
            frame_bytes = int(fields[4])
        except ValueError as exc:
            raise PermissionError("Native decoded picture PTS invalid") from exc
        if pts * tb != Fraction(idx,24) or frame_bytes <= 0:
            raise PermissionError("Picture frame PTS interval missing/reordered")
    if digest_file(source, MAX_PICTURE) != expected_sha256:
        raise PermissionError("Native picture mutated during independent decode")
    return {
        "independently_decoded": True, "picture_sha256": expected_sha256,
        "presented_frames": len(frames), "fps": 24,
        "pts_verified": True, "audio_streams": 0,
    }
