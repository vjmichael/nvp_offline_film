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
import json
import re
import secrets
import threading
import time
from contextlib import contextmanager
from backend.nvp_worker_containment import launch_contained
from backend.nvp_w1g_encrypted_source import require_efs_stage,verify_efs_inputs
from backend.nvp_wo3_dcp_structure import _linked_entry,_safe_leaf
from backend.nvp_wo3_codec_bundle_provenance import verify_native_codec_bundle

from backend.nvp_wo3_j2k_audit import inspect_j2k_header,PROFILES

FORMAT="nvp.wo3.native_openjpeg_frame.v1"
MAX_PROCESS_SECONDS=180
MAX_FRAME_BYTES=4096*2160*6


def digest_file(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()


ROLES={
    "OpenJPEG-opj_compress":"openjpeg-encoder",
    "OpenJPEG-opj_decompress":"openjpeg-decoder",
    "ASDCP-asdcp_wrap":"asdcp-wrap",
    "ASDCP-asdcp_info":"asdcp-info",
    "ASDCP-asdcp_unwrap":"asdcp-unwrap",
}
SHA=re.compile(r"[0-9a-f]{64}\Z")
MAX_STAGE_BYTES=2*1024*1024*1024
MAX_LOG_BYTES=1024*1024


def _sha(value):
    if type(value) is not str or not SHA.fullmatch(value):
        raise PermissionError("Exact SHA-256 source identity required")
    return value


def _playback_range(args):
    """Exact bounded historical CineCert range grammar, fixed staged names."""
    a=list(args)
    def integer(value):
        return (type(value) is str and bool(re.fullmatch(r"0|[1-9][0-9]{0,3}",value)))
    if (len(a) not in (6,8) or a[0]!="-f" or a[2]!="-d" or
            not integer(a[1]) or not integer(a[3])):
        return None
    first,count=int(a[1]),int(a[3])
    if not 0<=first<7200 or first+count>7200:
        return None
    if len(a)==8 and a[4:]==["-b",str(16*1024*1024),"picture.mxf","p_"] and 1<=count<=4:
        return "picture.mxf",first,count
    if len(a)==6 and a[4:]==["sound.mxf","audio"] and 1<=count<=24:
        return "sound.mxf",first,count
    return None


def _approved_arguments(product,args):
    """Finite original WO3 CLI grammars, not an arbitrary codec command API."""
    if (type(args) not in (list,tuple) or
        any(type(x) is not str or not 1<=len(x)<=240 for x in args)):
        raise PermissionError("Untrusted codec command")
    a=list(args)
    def leaf(x,suffix):
        return _safe_leaf(x) and x.lower().endswith(suffix)
    def count(x):
        return x.isascii() and x.isdecimal() and 1<=int(x)<=144000
    valid=False
    if product=="OpenJPEG-opj_compress":
        valid=a in (["-i","approved_xyz.ppm","-o","cinema.j2k",
                     "-cinema2K","24","-p","CPRL","-mct","0","-I"],
                    ["-i","approved_xyz.ppm","-o","cinema.j2k",
                     "-cinema4K","-p","CPRL","-mct","0","-I"])
    elif product=="OpenJPEG-opj_decompress":
        valid=(len(a)==4 and a[0]=="-i" and a[2]=="-o" and
               ((a[1]=="image.j2k" and a[3]=="decoded.ppm") or
                (bool(re.fullmatch(r"p_[0-9]{6}\.j2c",a[1])) and
                 a[3]=="xyz_"+a[1][2:8]+".ppm")))
    elif product=="ASDCP-asdcp_info":
        valid=len(a)==3 and a[:2]==["-i","-d"] and a[2] in ("picture.mxf","sound.mxf")
    elif product=="ASDCP-asdcp_wrap":
        valid=(len(a)==9 and a[:2]==["-L","-a"] and
               bool(re.fullmatch(r"[0-9a-f]{32}",a[2])) and
               a[3:6]==["-p","24","-d"] and count(a[6]) and
               a[7:] in (["source_j2c","picture.mxf"],["source.wav","sound.mxf"]))
    elif product=="ASDCP-asdcp_unwrap":
        valid=((len(a)==4 and a[0]=="-d" and count(a[1]) and
               a[2:] in (["picture.mxf","p_"],["sound.mxf","audio"])) or
               _playback_range(a) is not None)
    if not valid:
        raise PermissionError("Only finite historical WO3 codec arguments")
    return a


class ProtectedCodecAuthority:
    """Native host only; pinned installed roster plus fresh scoped approval.
    No public/model/HTTP constructor, environment-derived authority or
    fallback to a plain subprocess. Non-Windows protected jobs fail closed.
    """
    def __init__(self,bundle,manifest,*,manifest_sha256,runtime,project_id,
                 authorize_stage,authorize_execution,check_cancel):
        if os.name!="nt":
            raise PermissionError("WO3 protected execution requires Windows EFS/AppContainer")
        if (not all(callable(x) for x in
                    (authorize_stage,authorize_execution,check_cancel)) or
            type(project_id) is not str or not 1<=len(project_id)<=120):
            raise PermissionError("Trusted host project and native approvals required")
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion") as key:
            program=Path(winreg.QueryValueEx(key,"ProgramFilesDir")[0]).resolve(strict=True)
        self.bundle=Path(bundle)
        self.runtime=Path(runtime)
        if (not self.bundle.is_absolute() or _linked_entry(self.bundle) or
            not self.runtime.is_absolute() or _linked_entry(self.runtime) or
            not self.runtime.is_dir()):
            raise PermissionError("Installed codec root and existing private runtime required")
        self.bundle=self.bundle.resolve(strict=True)
        self.runtime=self.runtime.resolve(strict=True)
        if (self.bundle==program or not self.bundle.is_relative_to(program) or
            self.runtime.is_relative_to(program) or self.bundle.is_relative_to(self.runtime)):
            raise PermissionError("Codec bundle must be disjoint and below HKLM Program Files")
        self.manifest=json.loads(json.dumps(manifest,allow_nan=False))
        self.pin=_sha(manifest_sha256)
        self.project_id=project_id
        self.approve_stage=authorize_stage
        self.approve_execute=authorize_execution
        self.cancel=check_cancel
        self._guard=threading.RLock()
        self._stages={}
        self._verify_bundle()

    def _verify_bundle(self):
        raw=json.dumps(self.manifest,sort_keys=True,separators=(",",":"),
                       ensure_ascii=True).encode("ascii")
        if hashlib.sha256(raw).hexdigest()!=self.pin:
            raise PermissionError("Codec manifest differs from independent build pin")
        records=verify_native_codec_bundle(self.bundle,self.manifest)["tools"]
        allowed={"nvp-codec-manifest.json"}
        for item in self.manifest["tools"].values():
            allowed.update((item["filename"],item["license_notice"]))
        manifest_path=self.bundle/"nvp-codec-manifest.json"
        if ({p.name for p in self.bundle.iterdir()}!=allowed or
            any(_linked_entry(p) or not p.is_file() for p in self.bundle.iterdir()) or
            manifest_path.read_bytes()!=raw):
            raise PermissionError("Unreviewed codec dependency or manifest bytes")
        return records

    def verify_codec(self,codec):
        item=self._verify_bundle()[ROLES[codec.product]]
        if (codec.executable!=self.bundle/item["filename"] or
            codec.sha256!=item["binary_sha256"]):
            raise PermissionError("Codec is not in the reviewed installed roster")

    @contextmanager
    def stage(self,source_sha,*,playback_inputs=None):
        source_sha=_sha(source_sha)
        if playback_inputs is not None:
            if (type(playback_inputs) is not dict or set(playback_inputs)!={"picture.mxf","sound.mxf","frames","picture_sha256"} or
                type(playback_inputs["frames"]) is not int or not 3<=playback_inputs["frames"]<=7200):
                raise PermissionError("Exact bounded approved playback inputs required")
            if (type(playback_inputs["picture_sha256"]) not in (tuple,list) or
                    len(playback_inputs["picture_sha256"])!=playback_inputs["frames"]):
                raise PermissionError("Complete exact playback frame ledger required")
            playback_inputs={"picture.mxf":_sha(playback_inputs["picture.mxf"]),
                             "sound.mxf":_sha(playback_inputs["sound.mxf"]),
                             "frames":playback_inputs["frames"],
                             "picture_sha256":[_sha(x) for x in playback_inputs["picture_sha256"]]}
        job="wo3_"+secrets.token_hex(16)
        root=self.runtime/job
        scope={"operation":"nvp.wo3.protected_stage.v1","job_id":job,
               "project_id":self.project_id,"source_sha256":source_sha,
               "codec_manifest_sha256":self.pin}
        if playback_inputs is not None:
            scope["playback_inputs"]=playback_inputs
        if self.cancel() or self.approve_stage(json.loads(json.dumps(scope))) is not True:
            raise PermissionError("Independent source staging approval refused")
        root.mkdir(mode=0o700)
        require_efs_stage(root)
        journal=root/"stage_journal.json"
        def record(state):
            raw=json.dumps({**scope,"state":state},sort_keys=True,
                           separators=(",",":"),ensure_ascii=True).encode("ascii")
            temporary=root/"stage_journal.new"
            with temporary.open("xb") as out:
                out.write(raw);out.flush();os.fsync(out.fileno())
            os.replace(temporary,journal)
            verify_efs_inputs(root,("stage_journal.json",))
        record("PREPARED")
        lock=threading.RLock()
        with self._guard:
            self._stages[root]=(scope,lock)
        try:
            yield root
        except BaseException:
            with lock:
                with self._guard:
                    self._stages.pop(root,None)
                record("FAILED_UNVERIFIED")
            raise
        else:
            with lock:
                with self._guard:
                    self._stages.pop(root,None)
                record("STAGE_COMPLETE_NOT_PRODUCTION_ACCEPTANCE")
        # Retain encrypted stages for host recovery. Never delete an
        # uncertain worker's evidence or replay its unique job ID.

    def _snapshot(self,root):
        if (_linked_entry(root) or root.parent!=self.runtime or
                root.resolve(strict=True)!=root):
            raise PermissionError("Protected codec job directory changed")
        files={}
        total=0
        for item in root.rglob("*"):
            if _linked_entry(item):
                raise PermissionError("Linked codec stage entry")
            if item.is_dir():
                if item!=root/"source_j2c":
                    raise PermissionError("Unexpected native codec directory")
                continue
            if not item.is_file():
                raise PermissionError("Nonregular codec stage entry")
            relative=item.relative_to(root).as_posix()
            if (any(not _safe_leaf(p) for p in Path(relative).parts) or
                not re.fullmatch(r"(?:stage_journal\.json|approved_xyz\.ppm|cinema\.j2k|"
                    r"source\.wav|picture\.mxf|sound\.mxf|image\.j2k|decoded\.ppm|audio|"
                    r"source_j2c/[0-9]{6}\.j2c|p_[0-9]{6}\.j2c|xyz_[0-9]{6}\.ppm|"
                    r"(?:stdout|stderr)_[0-9a-f]{32}\.log)",relative)):
                raise PermissionError("Unreviewed codec stage entry")
            total+=item.stat().st_size
            if total>MAX_STAGE_BYTES or len(files)>=144010:
                raise RuntimeError("Historical bounded codec stage exceeds budget")
            files[relative]=digest_file(item)
        verify_efs_inputs(root,tuple(files))
        return files

    def execute(self,codec,args,root,timeout,include_stdout):
        # Recheck the full finite contract at the actual launch boundary,
        # including direct calls from trusted native host adapter code.
        if (not isinstance(codec,ApprovedCodecBinary) or codec.authority is not self or
            type(timeout) is not int or not 1<=timeout<=3600 or
            type(include_stdout) is not bool):
            raise PermissionError("Exact protected codec authority required")
        args=_approved_arguments(codec.product,args)
        root=Path(root)
        if not root.is_absolute() or _linked_entry(root):
            raise PermissionError("Protected native codec cwd required")
        self.verify_codec(codec)
        identity=(codec.product,codec.executable,codec.sha256)
        with self._guard:
            registration=self._stages.get(root)
        if registration is None:
            raise PermissionError("Only live host-owned EFS staging may execute codecs")
        scope,lock=registration
        with lock:
            with self._guard:
                if self._stages.get(root)!=registration:
                    raise PermissionError("Codec staging authority expired")
            before=self._snapshot(root)
            selected=_playback_range(args) if codec.product=="ASDCP-asdcp_unwrap" else None
            sealed=scope.get("playback_inputs")
            if selected is not None and (sealed is None or selected[1]+selected[2]>sealed["frames"]):
                raise PermissionError("Bounded seek needs live exact indexed playback scope")
            if sealed is not None:
                if (any(before.get(name)!=sealed[name] for name in ("picture.mxf","sound.mxf")) or
                    (selected is None and codec.product!="OpenJPEG-opj_decompress")):
                    raise PermissionError("Sealed playback inputs changed or operation not read-only")
                if codec.product=="OpenJPEG-opj_decompress":
                    match=re.fullmatch(r"p_([0-9]{6})\.j2c",args[1])
                    if (match is None or int(match[1])>=sealed["frames"] or
                        before.get(args[1])!=sealed["picture_sha256"][int(match[1])]):
                        raise PermissionError("Playback decode input differs from indexed frame")
            # Reject output collisions before any native write, including
            # conservative case-insensitive names on Windows.
            names={name.casefold() for name in before}
            if codec.product in ("OpenJPEG-opj_compress","OpenJPEG-opj_decompress"):
                expected={args[3]}
            elif codec.product=="ASDCP-asdcp_wrap":
                expected={args[-1]}
            elif codec.product=="ASDCP-asdcp_unwrap":
                first,count=(selected[1],selected[2]) if selected is not None else (0,int(args[1]))
                expected=({"p_%06d.j2c"%i for i in range(first,first+count)}
                          if args[-1]=="p_" else {"audio"})
            else:
                expected=set()
            if any(name.casefold() in names or (root/name).exists() or
                   _linked_entry(root/name) for name in expected):
                raise PermissionError("Native codec must not overwrite staged files")
            call=secrets.token_hex(16)
            auth={**scope,"operation":"nvp.wo3.native_codec.execute.v1",
                  "invocation_id":call,"product":codec.product,
                  "binary_sha256":codec.sha256,"argv":list(args),
                  "input_sha256":before,"timeout_seconds":timeout}
            if self.cancel() or self.approve_execute(json.loads(json.dumps(auth))) is not True:
                raise PermissionError("Fresh exact native execution approval refused")
            if self._snapshot(root)!=before:
                raise PermissionError("Codec inputs changed during approval")
            self.verify_codec(codec)
            if (codec.product,codec.executable,codec.sha256)!=identity:
                raise PermissionError("Native codec authority changed during approval")
            out=root/("stdout_"+call+".log")
            err=root/("stderr_"+call+".log")
            proc=None
            with (open(os.devnull,"rb") as inp,out.open("xb") as stdout,
                  err.open("xb") as stderr):
                try:
                    proc=launch_contained([str(identity[1]),*args],cwd=str(root),
                        stdin=inp,stdout=stdout,stderr=stderr,memory_mb=4096,
                        windows_appcontainer_required=True,
                        appcontainer_code_roots=(str(self.bundle),))
                    if getattr(proc,"sandbox_identity",None)!=(
                            "windows-appcontainer-with-zero-network-capabilities"):
                        raise RuntimeError("Native codec isolation not proved")
                    deadline=time.monotonic()+timeout
                    while proc.poll() is None:
                        if self.cancel() or time.monotonic()>=deadline:
                            raise InterruptedError("Native codec cancelled or timed out")
                        if any(os.fstat(f.fileno()).st_size>MAX_LOG_BYTES
                               for f in (stdout,stderr)):
                            raise RuntimeError("Native codec diagnostics exceeded budget")
                        time.sleep(.05)
                    rc=proc.wait(timeout=10)
                except BaseException:
                    if proc is not None:
                        proc.terminate_tree()
                    raise
                finally:
                    if proc is not None:
                        proc.close()
            if self.cancel() or rc:
                raise RuntimeError("Protected native codec failed or cancelled")
            self.verify_codec(codec)
            if (codec.product,codec.executable,codec.sha256)!=identity:
                raise PermissionError("Native codec identity changed during execution")
            after=self._snapshot(root)
            if any(after.get(name)!=value for name,value in before.items()):
                raise RuntimeError("Native codec mutated sealed inputs")
            if selected is not None and selected[0]=="picture.mxf" and any(
                after.get("p_%06d.j2c"%n)!=sealed["picture_sha256"][n]
                for n in range(selected[1],selected[1]+selected[2])):
                raise PermissionError("Unwrapped native picture differs from indexed frame ledger")
            if set(after)-set(before)!=expected|{out.name,err.name}:
                raise RuntimeError("Native codec omitted or added unapproved stage outputs")
            if max(out.stat().st_size,err.stat().st_size)>MAX_LOG_BYTES:
                raise RuntimeError("Native codec diagnostics exceeded budget")
            raw=out.read_bytes()
            if include_stdout and len(raw)>65536:
                raise RuntimeError("Native metadata exceeded bounded read")
            return {"exit_code":0,"native_codec_sha256":codec.sha256,
                    "stdout_sha256":after[out.name],"stderr_sha256":after[err.name],
                    "process_tree_custody_verified":True,"efs_verified":True,
                    "no_network_appcontainer":True,
                    "execution_scope_sha256":hashlib.sha256(json.dumps(
                        auth,sort_keys=True,separators=(",",":")).encode()).hexdigest(),
                    **({"stdout":raw} if include_stdout else {})}


class ApprovedCodecBinary:
    def __init__(self,executable,*,sha256,product,authority=None):
        file=Path(executable)
        if (not file.is_absolute() or _linked_entry(file) or not file.is_file()
            or product not in ROLES):
            raise PermissionError("Only a registered reviewed native codec binary")
        self.executable=file.resolve(strict=True)
        self.sha256=_sha(sha256)
        self.product=product
        self.authority=authority
        self.check()

    def check(self):
        if _linked_entry(self.executable) or digest_file(self.executable)!=self.sha256:
            raise PermissionError("Native codec license-reviewed binary changed")
        return True

    def stage(self,source_sha,*,playback_inputs=None):
        if not isinstance(self.authority,ProtectedCodecAuthority):
            raise PermissionError("Trusted protected codec authority required")
        self.authority.verify_codec(self)
        return self.authority.stage(source_sha,playback_inputs=playback_inputs)

    def run(self,args,*,cwd,timeout=MAX_PROCESS_SECONDS,include_stdout=False):
        self.check()
        args=_approved_arguments(self.product,args)
        if (not isinstance(self.authority,ProtectedCodecAuthority) or
            type(timeout) is not int or not 1<=timeout<=3600 or
            type(include_stdout) is not bool):
            raise PermissionError("Trusted finite protected codec invocation required")
        root=Path(cwd)
        if not root.is_absolute() or _linked_entry(root):
            raise PermissionError("Protected native codec cwd required")
        return self.authority.execute(self,args,root,timeout,include_stdout)


def common_codec_authority(*codecs):
    if (not codecs or not all(isinstance(c,ApprovedCodecBinary) for c in codecs)
        or not isinstance(codecs[0].authority,ProtectedCodecAuthority)
        or any(c.authority is not codecs[0].authority for c in codecs)):
        raise PermissionError("All codecs require one protected native host authority")
    for codec in codecs:
        codec.authority.verify_codec(codec)
    return codecs[0].authority


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
    with codec.stage(source_presentation_sha256) as root:
        inp=root/"approved_xyz.ppm"
        out=root/"cinema.j2k"
        with inp.open("xb") as stream:
            stream.write(ppm)
        cinema_flags=(["-cinema4K"] if profile.startswith("4K_")
                      else ["-cinema2K","24"])
        args=["-i",inp.name,"-o",out.name,*cinema_flags,
              "-p","CPRL","-mct","0","-I"]
        result=codec.run(args,cwd=root)
        if _linked_entry(out) or not out.is_file() or (
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
