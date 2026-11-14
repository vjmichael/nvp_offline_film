"""DA-05: original, immutable imported music/FX without FFmpeg.

Unlike captured 3D sound events, imported MP3/FLAC/WAV/Ogg are independent
creator-added media sources. They remain unchanged in FilmIndex. A native
miniaudio (dr_mp3/dr_flac/dr_wav/stb_vorbis) decoder yields <=4096 transient
48-kHz stereo PCM frames for audition/assembly: no persistent conversion,
flattened source, FFmpeg subprocess, video file or full-media RAM load.

ONLY a trusted OS picker/caller may supply source_path to register().
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

from backend.nvp_film_index import FilmIndex,_id,_require_pid,_sha
from backend.nvp_temporal_ledger import _int

FORMAT="nvp.imported_original_sound.v1"
SUPPORTED={".wav":"audio/wav",".mp3":"audio/mpeg",
           ".flac":"audio/flac",".ogg":"audio/ogg"}
MAX_SOURCE_BYTES=2*1024**3
MAX_DECODE_FRAMES=4096
OUTPUT_SAMPLE_RATE=48000


class OriginalAudioImport:
    def __init__(self,index:FilmIndex,*,trusted_native_picker):
        if not isinstance(index,FilmIndex) or not callable(trusted_native_picker):
            raise TypeError("Media import requires actual FilmIndex and a trusted native picker")
        self.index=index
        self.picker=trusted_native_picker

    def register_from_picker(self,project_id,source_id):
        _require_pid(project_id)
        _id(source_id,"original imported sound")
        # No browser/user-provided path crosses the API. The native OS
        # file-picker callback performs explicit creator interaction.
        filename=self.picker()
        if not isinstance(filename,(str,Path)) or not str(filename):
            raise PermissionError("No original sound file selected")
        original=Path(filename)
        if (original.is_symlink() or not original.is_file() or
            original.suffix.lower() not in SUPPORTED):
            raise ValueError("Selected file is not a supported original sound")
        codec=original.suffix.lower().lstrip(".")
        if original.stat().st_size>MAX_SOURCE_BYTES:
            raise ValueError("Original sound exceeds approved on-disk import budget")
        try:
            import miniaudio
        except ImportError as exc:
            raise RuntimeError("Standalone miniaudio codec not bundled") from exc
        info=miniaudio.get_file_info(str(original))
        if (type(info.nchannels) is not int or not 1<=info.nchannels<=8 or
            type(info.sample_rate) is not int or not 8000<=info.sample_rate<=384000
            or info.num_frames<=0):
            raise ValueError("Decoder could not verify original audio metadata")
        stored=self.index.put_media_file(project_id,original,
            media_type=SUPPORTED[original.suffix.lower()],
            max_bytes=MAX_SOURCE_BYTES)
        # FilmIndex hashes the original bytes and atomically indexes a
        # private, project-owned read-only copy before any source revision.
        manifest={
            "format":FORMAT,"original_codec":codec,
            "source_media_sha256":stored["sha256"],
            "source_media_type":stored["media_type"],
            "source_bytes":stored["size_bytes"],
            "native_sample_rate":info.sample_rate,
            "native_channels":info.nchannels,
            "native_frame_count":int(info.num_frames),
            "converted_soundtrack":False,
            "original_modified":False,
            "decoder":"standalone_miniaudio",
            "ffmpeg_used":False,
        }
        return self.index.register_revision(
            project_id,source_id,"audio",manifest,
            expected_revision=0)

    def describe(self,project_id,source_id,revision):
        source=self.index.read_revision(project_id,source_id,revision)
        data=source["data"]
        if (source["kind"]!="audio" or data.get("format")!=FORMAT or
            data.get("original_codec") not in ("wav","mp3","flac","ogg") or
            data.get("source_media_type") not in SUPPORTED.values() or
            data.get("converted_soundtrack") is not False):
            raise RuntimeError("Not an immutable user-imported original audio asset")
        return source

    def read_window(self,project_id,source_id,revision,first_sample,count):
        _int(first_sample,"imported playback sample")
        _int(count,"small external audio read",minimum=1,
             maximum=MAX_DECODE_FRAMES)
        manifest=self.describe(project_id,source_id,revision)["data"]
        sha=manifest["source_media_sha256"]
        _sha(sha)
        source=self.index.verify_media_file(
            project_id,sha,manifest["source_media_type"])
        if source["size_bytes"]!=manifest["source_bytes"]:
            raise RuntimeError("Imported original sound file changed")
        try:
            import miniaudio
        except ImportError as exc:
            raise RuntimeError("Non-FFmpeg native miniaudio decoder unavailable") from exc
        # Miniaudio stream_file streams/drains <=4096 decoded frames per
        # request, even when the untouched source contains hours of sound.
        stream=miniaudio.stream_file(
            source["path"],output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=2,sample_rate=OUTPUT_SAMPLE_RATE,
            frames_to_read=count,seek_frame=first_sample)
        expected=count*2*2
        out=bytearray()
        try:
            for samples in stream:
                if not samples:
                    continue
                chunk=samples.tobytes()
                if sys.byteorder!="little":
                    samples.byteswap()
                    chunk=samples.tobytes()
                if len(out)+len(chunk)>expected:
                    raise RuntimeError("Standalone audio decoder exceeded requested budget")
                out.extend(chunk)
                if len(out)==expected:
                    break
        finally:
            stream.close()
        if len(out)!=expected:
            raise ValueError("Original media does not cover requested audio interval")
        raw=bytes(out)
        return {"format":"nvp.imported_sound_pcm_window.v1",
                "status":"READY",
                "source_id":source_id,"source_revision":revision,
                "original_media_sha256":sha,
                "start_sample":first_sample,"sample_count":count,
                "sample_rate":OUTPUT_SAMPLE_RATE,"channels":2,
                "pcm_sha256":hashlib.sha256(raw).hexdigest(),
                "pcm":raw,"original_modified":False,
                "soundtrack_flattened":False,"ffmpeg_used":False}
