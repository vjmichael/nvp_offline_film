"""W1-G fail-closed source audit of original production runtime worker launches.

All native desktop backend subprocesses must be routed through the central
launch_contained (Windows Job+release slot). Exception sources are narrow:
the Linux-specific filming cgroup bootstrap, Windows-disabled legacy STT and
FFmpeg color adapters, Windows-contained Blender bridge with Linux-only
legacy source compatibility, and the central launcher itself.

No eval, shell, dynamic imports, direct Popen, asyncio.create_subprocess or
os.spawn is accepted from other production backend files.
This source audit is an ADDITIONAL regression check, never kernel proof.
"""
from __future__ import annotations

import argparse
import ast
from hashlib import sha1, sha256
import json
from pathlib import Path

FORMAT="nvp.w1g.original_runtime_launch_surface_audit.v1"
ALLOWED={
    "backend/nvp_worker_containment.py":{"Popen"},
    "backend/nvp_filming_cgroup_launch.py":{"Popen"},
    "backend/nvp_stt_service.py":{"Popen"},
    "backend/nvp_color_ocio.py":{"run"},
    "backend/nvp_w1g_owned_subprocess.py":{"run"},
    "backend/nvp_native_frame_index.py":{"Popen"},
    "backend/nvp_audio01f_picture_sound.py":{"Popen"},
    "backend/nvp_worker_linux_cgroup.py":{"Popen"},
}
MARKERS={
    "backend/nvp_worker_containment.py":(
        "from backend.nvp_w1g_release_gate import WindowsWorkerLifetimeSlot",
        "CREATE_SUSPENDED",
    ),
    "backend/nvp_filming_cgroup_launch.py":("sys.platform != \"linux\"",),
    "backend/nvp_stt_service.py":(
        "if os.name==\"nt\":",
        "Retired WebM/FFmpeg STT cannot launch a Windows worker",
    ),
    "backend/nvp_color_ocio.py":(
        "if os.name==\"nt\":",
        "Legacy FFmpeg color subprocess is blocked in Windows production",
    ),
    "backend/nvp_w1g_owned_subprocess.py":(
        "if os.name != \"nt\":",
        "from backend.nvp_worker_containment import launch_contained",
        'marker=registration/("original-"',
        "marker.unlink()",
    ),
    "backend/nvp_native_frame_index.py":(
        'if os.name == "nt":', "run_owned_subprocess(", "stream = owned_output",
    ),
    "backend/nvp_audio01f_picture_sound.py":(
        'if os.name == "nt":', "run_owned_subprocess(", "proc=subprocess.Popen(command",
    ),
    "backend/nvp_worker_linux_cgroup.py":(
        'if sys.platform!="linux" or os.name!="posix":', "guardian=subprocess.Popen",
    ),
}
# This historical adapter used a direct Linux subprocess fallback. Its source
# is retained in Git history, never in an executable release graph.
RETIRED_LAUNCHER="backend/nvp_w1g_legacy_blender_launch.py"
# These EXACT two original Windows icacls operations configure and recover
# the host-owned AppContainer ACL, not a renderer/worker subprocess.
# An immutable Git blob attestation prevents extending the exception.
G03_HOST_ACL_MODULE="backend/nvp_g03_windows_appcontainer.py"
G03_REVIEWED_BLOB_SHA1="7f152a1a1c40132193587a2838b740ff068912dd"
G03_ALLOWED_ACL_SITES=(
    "subprocess.run(args, capture_output=True, text=True, errors='replace', timeout=120, check=False)",
    "subprocess.run(['icacls', str(work), '/setintegritylevel', '(OI)(CI)L'], capture_output=True, text=True, timeout=30)",
)
OPS=frozenset(("run","Popen","call","check_output","check_call","getoutput",
               "getstatusoutput"))
ASYNCS=frozenset(("create_subprocess_exec","create_subprocess_shell"))
OS_SPAWN=frozenset(("system","popen","spawnl","spawnle","spawnlp","spawnlpe",
                    "spawnv","spawnve","spawnvp","spawnvpe","startfile","posix_spawn",
                    "posix_spawnp"))


def audit_release_launch_surface(root:Path):
    root=Path(root)
    backend=root/"backend"
    if not backend.is_dir() or backend.is_symlink():
        raise RuntimeError("Original runtime source tree is absent or linked")
    retired=root/RETIRED_LAUNCHER
    if retired.exists() or retired.is_symlink():
        raise PermissionError("Retired uncontrolled Blender launcher is not admissible")
    sources=sorted(backend.glob("nvp_*.py"))
    if len(sources)<100:
        raise RuntimeError("Incomplete original production source tree")
    seen={}
    hashes=[]
    unregistered=[]
    for file in sources:
        if file.is_symlink() or not file.is_file():
            raise RuntimeError("Linked runtime module cannot be reviewed")
        key="backend/"+file.name
        source=file.read_text("utf8")
        raw=source.encode("utf8")
        hashes.append(key+":"+sha256(raw).hexdigest())
        if key==G03_HOST_ACL_MODULE:
            # Pin whole original source bytes, not merely an easily preserved
            # marker, before exempting any host-only ACL command.
            blob=b"blob "+str(len(raw)).encode("ascii")+b"\0"+raw
            if sha1(blob).hexdigest()!=G03_REVIEWED_BLOB_SHA1:
                raise PermissionError("Unreviewed original AppContainer ACL host source")
        tree=ast.parse(source,filename=str(file))
        g03_host_sites=[]
        aliases={"subprocess":"subprocess","asyncio":"asyncio","os":"os"}
        from_calls={}
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                for a in node.names:
                    if a.name in aliases:
                        aliases[a.asname or a.name]=a.name
            if isinstance(node,ast.ImportFrom):
                if node.module in ("subprocess","asyncio","os"):
                    for a in node.names:
                        from_calls[a.asname or a.name]=(node.module,a.name)
        for node in ast.walk(tree):
            if not isinstance(node,ast.Call):
                continue
            operation=None
            fn=node.func
            if (isinstance(fn,ast.Attribute) and isinstance(fn.value,ast.Name)
                    and fn.value.id in aliases):
                operation=(aliases[fn.value.id],fn.attr)
            if isinstance(fn,ast.Name) and fn.id in from_calls:
                operation=from_calls[fn.id]
            if not operation:
                continue
            module,action=operation
            external=(module=="subprocess" and action in OPS) or (
                module=="asyncio" and action in ASYNCS) or (
                module=="os" and action in OS_SPAWN)
            if not external:
                continue
            if key==G03_HOST_ACL_MODULE and module=="subprocess" and action=="run":
                # Not a general allowlist: full source blob and the exact two
                # original call ASTs must match this reviewed host ACL fixture.
                g03_host_sites.append(ast.unparse(node))
                continue
            if module!="subprocess" or action not in ALLOWED.get(key,set()):
                unregistered.append(key+":"+str(node.lineno)+":"+module+"."+action)
                continue
            seen.setdefault(key,set()).add(action)
        if key==G03_HOST_ACL_MODULE and tuple(sorted(g03_host_sites))!=tuple(sorted(G03_ALLOWED_ACL_SITES)):
            raise PermissionError("Unreviewed original AppContainer ACL host launch sites")
    # Fail if an allowed source disappeared, was renamed or lost its explicit
    # platform-level non-Windows boundary; otherwise new Popen would slip in.
    for key,operations in ALLOWED.items():
        file=root/key
        if key not in seen or seen[key]!=operations:
            raise RuntimeError("Original reviewed launch roster incomplete: "+key)
        code=file.read_text("utf8")
        if any(marker not in code for marker in MARKERS[key]):
            raise RuntimeError("Original launch boundary markers changed: "+key)
    if unregistered:
        raise PermissionError(
            "Unregistered original runtime process-launch bypasses: "+
            "; ".join(sorted(unregistered)))
    return {
        "format":FORMAT,
        "status":"NO_UNREVIEWED_BACKEND_PROCESS_LAUNCH_SITE",
        "source_modules_audited":len(sources),
        "reviewed_legacy_launch_modules":sorted(ALLOWED),
        "runtime_source_tree_sha256":sha256("\n".join(hashes).encode("ascii")).hexdigest(),
        "kernel_execution_verified":False,
        "physical_windows_accepted":False,
    }


def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,default=Path("."))
    ap.add_argument("--receipt",type=Path)
    args=ap.parse_args(argv)
    receipt=audit_release_launch_surface(args.root)
    if args.receipt:
        if args.receipt.exists() or args.receipt.is_symlink():
            raise RuntimeError("Source launch surface receipt already exists")
        args.receipt.write_text(json.dumps(receipt,sort_keys=True,indent=2)+"\n",
                                encoding="utf8")
    print(json.dumps(receipt,sort_keys=True,indent=2))


if __name__=="__main__":
    main()
