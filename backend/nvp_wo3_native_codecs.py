"""WO3-02: SHA-pinned native OpenJPEG cinema JPEG2000 encoder adapter.

The installed trusted host supplies an approved OpenJPEG executable and exact
SHA, not browser/AI code or user-selected tools. Input is already-approved
uncompressed DCDM XYZ 12-bit component pixels; film-color mastering is WO4.
No shell, FFmpeg, network, arbitrary CLI arguments or source mutation.

An OpenJPEG process success/header check is NOT independent decoding or DCI
certification. Independent MXF/bitstream QC remains mandatory.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

from backend.nvp_wo3_j2k_audit import inspect_j2k_header,PROFILES

FORMAT="nvp.wo3.native_openjpeg_frame.v1"
MAX_PROCESS_SECONDS=180
MAX_FRAME_BYTES=2048*1080*6


def digest_file(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()


class ApprovedCodecBinary:
    def __init__(self,executable,*,sha256,product):
        file=Path(executable)
        if (not file.is_absolute() or file.is_symlink() or
            not file.is_file() or type(sha256) is not str or
            len(sha256)!=64 or any(c not in "0123456789abcdef" for c in sha256) or
            product not in ("OpenJPEG-opj_compress","ASDCP-asdcp_wrap","ASDCP-asdcp_info")):
            raise PermissionError("Only a registered reviewed native codec binary")
        self.executable=file.resolve(strict=True)
        self.sha256=sha256
        self.product=product
        self.check()

    def check(self):
        if self.executable.is_symlink() or digest_file(self.executable)!=self.sha256:
            raise PermissionError("Native codec license-reviewed binary changed")
        return True

    def run(self,args,*,cwd,timeout=MAX_PROCESS_SECONDS,include_stdout=False):
        self.check()
        root=Path(cwd).resolve(strict=True)
        if not root.is_dir() or type(args) not in (tuple,list) or (
            not all(type(x) is str and 0<len(x)<=240 for x in args)):
            raise PermissionError("Untrusted native encoder execution argument")
        # Set no shell and no ambient source paths; every path comes from
        # private staging created by the host, not from a model.
        result=subprocess.run([str(self.executable),*args],
                              cwd=str(root),shell=False,
                              timeout=timeout,check=False,
                              capture_output=True,stdin=subprocess.DEVNULL,
                              env={"PATH":str(self.executable.parent),
                                   "SYSTEMROOT":os.environ.get("SYSTEMROOT",""),
                                   "HOME":str(root),"TMP":str(root),
                                   "TEMP":str(root)})
        self.check()
        if result.returncode!=0:
            raise RuntimeError("Native licensed cinema codec rejected input")
        receipt={"exit_code":0,
                 "native_codec_sha256":self.sha256,
                 "stdout_sha256":hashlib.sha256(result.stdout).hexdigest(),
                 "stderr_sha256":hashlib.sha256(result.stderr).hexdigest()}
        if include_stdout:receipt["stdout"]=result.stdout[:65536]
        return receipt


def _ppm_xyz12(pixels,profile):
    if profile not in PROFILES:
        raise ValueError("Only original DCI 2K 24Hz presentation profiles")
    width,height,_=PROFILES[profile]
    if type(pixels) is not bytes or len(pixels)!=width*height*6:
        raise ValueError("Source-approved XYZ 12-bit 4:4:4 payload required")
    # PPM maxval 4095 => big-endian 16-bit components holding 0..4095.
    # Validate every pixel's 4 high bits remain zero. No clipping/implicit
    # RGB->XYZ conversion occurs within the codec adapter.
    if any(pixels[i]&0xF0 for i in range(0,len(pixels),2)):
        raise ValueError("Native XYZ component has bits above 12-bit range")
    return (f"P6\n{width} {height}\n4095\n".encode("ascii")+pixels)


def encode_xyz12_frame(codec:ApprovedCodecBinary,xyz12,*,profile,
                       source_presentation_sha256,creator_approved):
    if codec.product!="OpenJPEG-opj_compress":
        raise PermissionError("OpenJPEG executable required for cinema source")
    if creator_approved is not True or (
        type(source_presentation_sha256) is not str or
        len(source_presentation_sha256)!=64 or
        any(x not in "0123456789abcdef" for x in source_presentation_sha256)):
        raise PermissionError("Exact approved source presentation identity required")
    ppm=_ppm_xyz12(xyz12,profile)
    with tempfile.TemporaryDirectory(prefix="nvp-wo3-dci-") as folder:
        root=Path(folder)
        inp=root/"approved_xyz.ppm"
        out=root/"cinema.j2k"
        inp.write_bytes(ppm)
        args=["-i",inp.name,"-o",out.name,
              "-cinema2K","24","-p","CPRL","-mct","0","-I"]
        result=codec.run(args,cwd=root)
        if out.is_symlink() or not out.is_file() or (
            not 80<=out.stat().st_size<=16*1024*1024):
            raise RuntimeError("OpenJPEG did not produce bounded codestream")
        codestream=out.read_bytes()
        header=inspect_j2k_header(codestream,profile)
        return {
            "format":FORMAT,
            "profile":profile,
            "original_approved_presentation_sha256":
                source_presentation_sha256,
            "source_xyz12_sha256":hashlib.sha256(xyz12).hexdigest(),
            "native_codec_sha256":codec.sha256,
            "codec_result":result,
            "codestream":codestream,
            "codestream_sha256":header["raw_codestream_sha256"],
            "independent_header_constraints_verified":True,
            "independent_decoded_pixels_verified":False,
            "dci_certified":False,
            "original_source_modified":False,
            "ffmpeg_used":False,
        }
