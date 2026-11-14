"""Private P1-F Linux worker filesystem and network kernel boundary.

An actual Linux mount/network/user namespace is created by root-owned
bubblewrap, then ALL of bubblewrap, Blender and descendants are launched
inside the existing delegated-cgroup v2 and out-of-tree cgroup.kill guardian.
No filesystem/network isolation is inferred from cgroup membership alone.
Windows AppContainer/WFP custody has no replacement in this module and
MUST FAIL CLOSED until a reviewed native Windows service supports it.

This is an execution *requirement*, not a signed attestation or permission
to render creator film; the renderer still verifies distinct one-use consent.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import stat
import sys

CONTRACT="nvp.private_blender_linux_user_mount_net_ns.v1"
BWRAP=Path("/usr/bin/bwrap")
RO_SYSTEM=("/usr","/lib","/lib64")
RO_ETC=("/etc/fonts","/etc/ld.so.cache","/etc/ssl/certs")


def _pinned_linux_bwrap():
    if sys.platform!="linux" or os.name!="posix":
        raise RuntimeError("Private P1-F worker lacks Windows AppContainer/WFP isolation service")
    if BWRAP.is_symlink() or not BWRAP.is_file():
        raise RuntimeError("Root-owned reviewed bubblewrap binary not provisioned")
    st=BWRAP.stat()
    if st.st_uid!=0 or st.st_mode&(stat.S_IWGRP|stat.S_IWOTH):
        raise RuntimeError("Private namespace executable ownership is unsafe")
    # The trusted host may pin this exact SHA against the installed package;
    # the executable is never selected by a model or read from a scene.
    h=sha256()
    with BWRAP.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def private_os_preflight():
    """Require real kernel isolation infrastructure, not a caller bool."""
    digest=_pinned_linux_bwrap()
    from backend.nvp_worker_linux_cgroup import current_delegated_parent
    parent=current_delegated_parent()
    if not (parent/"cgroup.controllers").is_file():
        raise RuntimeError("Production kernel process custody is not delegated")
    return {"contract":CONTRACT,"namespace_executable_sha256":digest,
            "network_unshared":True,"filesystem_private":True,
            "kernel_cgroup_delegation":True,"actual_worker_launched":False}


def sandbox_command(command,jobdir):
    """Wrap the exact Blender command; no proxy shell and no host home mount."""
    if (type(command) is not list or not command or
            not Path(command[0]).is_absolute()):
        raise ValueError("Absolute pinned Blender executable is required")
    digest=_pinned_linux_bwrap()
    job=Path(jobdir)
    if (not job.is_absolute() or job.is_symlink() or not job.is_dir() or
            str(job)!=str(job.resolve()) or
            any(isinstance(arg,str) and arg.startswith("/") and
                not Path(arg).resolve().is_relative_to(job)
                for arg in command[1:])):
        raise RuntimeError("Private Blender invocation contains unauthorized host path")
    binary=Path(command[0]).resolve()
    if not (binary.is_file() and binary.is_relative_to(Path("/usr"))):
        raise RuntimeError("Private Blender binary must be provisioned under reviewed /usr runtime")
    # Mount ONLY reviewed public runtime and this one job's original-source
    # directory. Nothing at /home, /root, /run or network sockets is exposed.
    cmd=[str(BWRAP),"--die-with-parent","--new-session",
         "--unshare-user","--unshare-pid","--unshare-ipc",
         "--unshare-uts","--unshare-net",
         "--clearenv","--setenv","HOME","/tmp",
         "--setenv","XDG_CACHE_HOME","/tmp",
         "--setenv","XDG_CONFIG_HOME","/tmp",
         "--setenv","PATH","/usr/bin:/bin"]
    for path in RO_SYSTEM:
        p=Path(path)
        if p.is_symlink():
            # Ubuntu merged-/usr images have /lib and /lib64 symlinks.
            # Bind-mounting onto a symlink is neither portable nor safe.
            link=os.readlink(path)
            if (not link or link.startswith("/") or
                    ".." in Path(link).parts):
                raise RuntimeError("Unreviewed runtime symlink in private mount boundary")
            cmd.extend(["--symlink",link,path])
        elif p.is_dir():
            cmd.extend(["--ro-bind",path,path])
    for path in RO_ETC:
        p=Path(path)
        if p.exists():
            cmd.extend(["--ro-bind",path,path])
    # A fresh isolated /tmp is not the host's /tmp. Build only the
    # ancestors required to mount this one approved job directory.
    cmd+=["--dev","/dev","--proc","/proc","--tmpfs","/tmp"]
    parents=list(reversed(job.parents))
    for p in parents:
        if p!=Path("/") and not str(p) in RO_SYSTEM and not any(
                str(p).startswith(ro+"/") for ro in RO_SYSTEM):
            cmd.extend(["--dir",str(p)])
    cmd+=["--bind",str(job),str(job),"--chdir",str(job),
          "--",*command]
    return {"command":cmd,"contract":CONTRACT,
            "bubblewrap_sha256":digest,
            "private_job_root":str(job),
            "no_network":True}
