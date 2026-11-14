"""BENCHMARK REFERENCE ONLY: FFMS2 C-ABI source decode, not shipped in NVP.

C ABI from FFMS2 include/ffms.h (public 2.40+/5.x ABI prefixes). This module is ONLY used in external comparison CI. It is NOT a production
backend, and no FFMS2 library is included in NVP's application or installer.
Run against controlled benchmark files within disposable CI machines.
"""
from __future__ import annotations

import ctypes as C
import hashlib
import os
from pathlib import Path
import struct
import zlib

MAX_FFMS_FRAME = 2**31 - 1
MAX_REVIEW_PIXELS = 3840 * 2160
CHUNK_SIZE = 4 * 1024 * 1024
PNG_SIG = b"\x89PNG\r\n\x1a\n"


class ErrorInfo(C.Structure):
    _fields_ = [("ErrorType", C.c_int), ("SubType", C.c_int),
                ("BufferSize", C.c_int), ("Buffer", C.c_void_p)]


class VideoPropsPrefix(C.Structure):
    _fields_ = [("FPSDenominator", C.c_int), ("FPSNumerator", C.c_int),
                ("RFFDenominator", C.c_int), ("RFFNumerator", C.c_int),
                ("NumFrames", C.c_int)]


class FramePrefix(C.Structure):
    _fields_ = [("Data", C.c_void_p * 4), ("Linesize", C.c_int * 4),
                ("EncodedWidth", C.c_int), ("EncodedHeight", C.c_int),
                ("EncodedPixelFormat", C.c_int), ("ScaledWidth", C.c_int),
                ("ScaledHeight", C.c_int), ("ConvertedPixelFormat", C.c_int),
                ("KeyFrame", C.c_int), ("RepeatPict", C.c_int),
                ("InterlacedFrame", C.c_int), ("TopFieldFirst", C.c_int)]


class FrameInfoPrefix(C.Structure):
    _fields_ = [("PTS", C.c_int64), ("RepeatPict", C.c_int),
                ("KeyFrame", C.c_int)]


class TimeBase(C.Structure):
    _fields_ = [("Num", C.c_int64), ("Den", C.c_int64)]


def sha_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def _path_bytes(path):
    path = Path(path)
    if not path.is_absolute() or path.is_symlink():
        raise PermissionError("FFMS2 source/index paths must be absolute and non-symlinked")
    return os.fsencode(str(path))


def _png_chunk(file, name, payload):
    file.write(struct.pack(">I", len(payload)))
    file.write(name)
    file.write(payload)
    crc = zlib.crc32(payload, zlib.crc32(name)) & 0xffffffff
    file.write(struct.pack(">I", crc))


class FFMS2:
    """Explicit FFMS2 library loaded only inside a trusted native process."""

    def __init__(self, library_path):
        lib_path = Path(library_path)
        if (not lib_path.is_absolute() or lib_path.is_symlink() or
            not lib_path.is_file()):
            raise PermissionError("Native FFMS2 library must be an absolute verified file")
        self.library_path = lib_path
        self.library_sha256 = sha_file(lib_path)
        # Windows Python 3.8+ requires explicit DLL search roots for native
        # dependencies; never mutate process-wide PATH for untrusted media.
        self._dll_directory = os.add_dll_directory(str(lib_path.parent)) if os.name == "nt" else None
        self.api = C.CDLL(str(lib_path))

        def bind(name, result, *args):
            fn = getattr(self.api, name)
            fn.restype = result
            fn.argtypes = list(args)
            return fn

        p = C.c_void_p
        error = C.POINTER(ErrorInfo)
        self.init = bind("FFMS_Init", None, C.c_int, C.c_int)
        self.get_version = bind("FFMS_GetVersion", C.c_int)
        self.create_indexer = bind("FFMS_CreateIndexer", p, C.c_char_p, error)
        self.cancel_indexing = bind("FFMS_CancelIndexing", None, p)
        self.do_indexing = bind("FFMS_DoIndexing2", p, p, C.c_int, error)
        self.destroy_index = bind("FFMS_DestroyIndex", None, p)
        self.write_index = bind("FFMS_WriteIndex", C.c_int, C.c_char_p, p, error)
        self.read_index = bind("FFMS_ReadIndex", p, C.c_char_p, error)
        self.belongs_to_file = bind("FFMS_IndexBelongsToFile", C.c_int,
                                    p, C.c_char_p, error)
        self.first_video = bind("FFMS_GetFirstIndexedTrackOfType",
                                C.c_int, p, C.c_int, error)
        self.track_from_index = bind("FFMS_GetTrackFromIndex", p, p, C.c_int)
        self.num_frames = bind("FFMS_GetNumFrames", C.c_int, p)
        self.frame_info = bind("FFMS_GetFrameInfo",
                               C.POINTER(FrameInfoPrefix), p, C.c_int)
        self.track_from_video = bind("FFMS_GetTrackFromVideo", p, p)
        self.time_base = bind("FFMS_GetTimeBase", C.POINTER(TimeBase), p)
        self.create_video = bind("FFMS_CreateVideoSource", p,
                                 C.c_char_p, C.c_int, p, C.c_int, C.c_int, error)
        self.destroy_video = bind("FFMS_DestroyVideoSource", None, p)
        self.video_props = bind("FFMS_GetVideoProperties",
                                C.POINTER(VideoPropsPrefix), p)
        self.get_frame = bind("FFMS_GetFrame",
                              C.POINTER(FramePrefix), p, C.c_int, error)
        self.get_pixfmt = bind("FFMS_GetPixFmt", C.c_int, C.c_char_p)
        self.set_output = bind("FFMS_SetOutputFormatV2", C.c_int, p,
                               C.POINTER(C.c_int), C.c_int, C.c_int,
                               C.c_int, error)
        self.init(0, 0)
        version = self.get_version() & 0xffffffff
        self.version = version
        major = version >> 24
        if not (2 <= major <= 5):
            raise RuntimeError("Unvalidated FFMS2 library major version")

    @staticmethod
    def _error():
        buffer = C.create_string_buffer(1024)
        err = ErrorInfo(0, 0, 1024, C.cast(buffer, C.c_void_p))
        return err, buffer

    @staticmethod
    def _failure(label, buffer):
        raise RuntimeError(label + ": " + buffer.value.decode("utf-8", "replace")[:400])

    def create_index(self, source, stage_path):
        """Index source once. FFMS2 destroys the indexer during DoIndexing2."""
        src = _path_bytes(source)
        dest = _path_bytes(stage_path)
        err, buf = self._error()
        indexer = self.create_indexer(src, C.byref(err))
        if not indexer:
            self._failure("FFMS2 indexer open failed", buf)
        try:
            index = self.do_indexing(indexer, 2, C.byref(err))
        except BaseException:
            # FFMS2 owns/destroys the indexer once called, including errors.
            raise
        if not index:
            self._failure("FFMS2 indexing failed", buf)
        try:
            if self.belongs_to_file(index, src, C.byref(err)) != 0:
                self._failure("FFMS2 generated index/source mismatch", buf)
            info = self._track_info(index)
            if self.write_index(dest, index, C.byref(err)) != 0:
                self._failure("FFMS2 index write failed", buf)
            return info
        finally:
            self.destroy_index(index)

    def _track_info(self, index):
        err, buf = self._error()
        track_no = self.first_video(index, 0, C.byref(err))
        if track_no < 0:
            self._failure("FFMS2 no indexed video track", buf)
        track = self.track_from_index(index, track_no)
        if not track:
            raise RuntimeError("FFMS2 video track missing from index")
        frames = self.num_frames(track)
        if frames <= 0 or frames > MAX_FFMS_FRAME:
            raise RuntimeError("FFMS2 32-bit frame count unsupported")
        base = self.time_base(track)
        if not base or base.contents.Den <= 0 or base.contents.Num <= 0:
            raise RuntimeError("FFMS2 invalid video timebase")
        return {"track": track_no, "num_frames": frames,
                "time_base_num": base.contents.Num,
                "time_base_den": base.contents.Den}

    def open_video(self, source, index_path, *, track=None):
        index_file = _path_bytes(index_path)
        src = _path_bytes(source)
        err, buf = self._error()
        index = self.read_index(index_file, C.byref(err))
        if not index:
            self._failure("FFMS2 cannot load saved index", buf)
        try:
            if self.belongs_to_file(index, src, C.byref(err)) != 0:
                self._failure("FFMS2 saved index/source mismatch", buf)
            meta = self._track_info(index)
            if track is not None and track != meta["track"]:
                raise RuntimeError("Indexed video track selection changed")
            video = self.create_video(src, meta["track"], index, 1, 1, C.byref(err))
            if not video:
                self._failure("FFMS2 video source open failed", buf)
        finally:
            self.destroy_index(index)
        return IndexedVideo(self, video, meta)


class IndexedVideo:
    def __init__(self, ffms, handle, meta):
        self.ffms, self.handle, self.meta = ffms, handle, meta
        self._configured = None

    def close(self):
        if self.handle:
            self.ffms.destroy_video(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _frame(self, frame_zero):
        if not self.handle or type(frame_zero) is not int or not 0 <= frame_zero < self.meta["num_frames"]:
            raise ValueError("FFMS2 frame is outside indexed 32-bit range")
        err, buf = self.ffms._error()
        frame = self.ffms.get_frame(self.handle, frame_zero, C.byref(err))
        if not frame:
            self.ffms._failure("FFMS2 exact frame decode failed", buf)
        return frame.contents

    def frame_metadata(self, frame_zero):
        """Exact integer PTS, keyframe flag and independent frame index."""
        if type(frame_zero) is not int or not 0 <= frame_zero < self.meta["num_frames"]:
            raise ValueError("Frame outside validated FFMS2 index")
        track = self.ffms.track_from_video(self.handle)
        if not track:
            raise RuntimeError("FFMS2 video-owned frame index unavailable")
        details = self.ffms.frame_info(track, frame_zero)
        if not details:
            raise RuntimeError("FFMS2 exact frame metadata unavailable")
        f = self._frame(frame_zero)
        return {"frame_zero": frame_zero, "pts": details.contents.PTS,
                "time_base_num": self.meta["time_base_num"],
                "time_base_den": self.meta["time_base_den"],
                "keyframe": bool(details.contents.KeyFrame),
                "width": f.EncodedWidth, "height": f.EncodedHeight}

    def save_png(self, frame_zero, output, *, max_pixels=MAX_REVIEW_PIXELS):
        """Decode one frame as 8-bit RGB review PNG (NOT high-bit-depth master).

        C-owned frame memory is copied *before* the next FFMS2 call. PNG rows
        are streamed to disk with stdlib zlib; no whole-film memory expansion.
        """
        first = self._frame(frame_zero)
        src_w, src_h = first.EncodedWidth, first.EncodedHeight
        if not 1 <= src_w <= 65536 or not 1 <= src_h <= 65536:
            raise RuntimeError("Invalid indexed source dimensions")
        if type(max_pixels) is not int or not 1 <= max_pixels <= MAX_REVIEW_PIXELS:
            raise ValueError("Invalid review frame pixel budget")
        # Bound frame RAM by scaling proportionally, no implicit full-res load.
        scale = min(1.0, (max_pixels / (src_w * src_h)) ** 0.5)
        width, height = max(1, int(src_w * scale)), max(1, int(src_h * scale))
        if self._configured != (width, height):
            fmt = self.ffms.get_pixfmt(b"rgb24")
            if fmt < 0:
                raise RuntimeError("Native FFMS2 does not support RGB24 review output")
            fmts = (C.c_int * 2)(fmt, -1)
            err, buf = self.ffms._error()
            if self.ffms.set_output(self.handle, fmts, width, height, 4,
                                    C.byref(err)) != 0:
                self.ffms._failure("FFMS2 RGB24 conversion failed", buf)
            self._configured = (width, height)
        frame = self._frame(frame_zero)
        if (frame.ScaledWidth != width or frame.ScaledHeight != height or
            not frame.Data[0] or abs(frame.Linesize[0]) < width * 3):
            raise RuntimeError("Unexpected FFMS2 output stride or format")
        if not Path(output).is_absolute() or Path(output).is_symlink() or Path(output).exists():
            raise PermissionError("Native review PNG destination must be new and absolute")
        with Path(output).open("xb") as fp:
            fp.write(PNG_SIG)
            _png_chunk(fp, b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            compressor = zlib.compressobj(level=3)
            pointer, pitch = frame.Data[0], frame.Linesize[0]
            for y in range(height):
                # FFMS2 plane pointers may have negative line strides.
                offset = y * pitch
                row = C.string_at(pointer + offset, width * 3)
                payload = compressor.compress(b"\x00" + row)
                if payload:
                    _png_chunk(fp, b"IDAT", payload)
            tail = compressor.flush()
            if tail:
                _png_chunk(fp, b"IDAT", tail)
            _png_chunk(fp, b"IEND", b"")
            fp.flush()
            os.fsync(fp.fileno())
        return {"frame_zero": frame_zero, "width": width, "height": height,
                "sha256": sha_file(output), "size_bytes": Path(output).stat().st_size,
                "review_only": True, "decoder": "ffms2"}
