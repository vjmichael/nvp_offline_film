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


def prove_private_kernel_boundary(supervisor_root):
    """Actually run a zero-media kernel probe *before* staging creator sources.

    This proves a finite local namespace+cgroup launch on this machine at
    this moment; it does not attest Windows, Blender pixels or the later
    worker's release signing. A mere Bubblewrap argv/preflight is not proof.
    """
    import json
    import secrets
    import socket
    import tempfile
    from backend.nvp_worker_containment import launch_contained
    from backend.nvp_worker_linux_cgroup import current_cgroup_relative

    preflight=private_os_preflight()
    root=Path(supervisor_root).resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError("Untrusted NVP kernel-probe workspace")
    binary=Path("/usr/bin/python3")
    if not binary.is_file():
        raise RuntimeError("Reviewed Linux kernel-probe interpreter unavailable")
    parent_net=os.readlink("/proc/self/ns/net")
    parent_mount=os.readlink("/proc/self/ns/mnt")
    parent_cgroup=current_cgroup_relative()
    nonce=secrets.token_hex(16)
    # Entirely public probe bytes. No private project data exists in this
    # temporary directory and no other worker's directory is mounted.
    with tempfile.TemporaryDirectory(prefix="p1f_kernel_probe_",dir=root) as temp:
        tmp=Path(temp).resolve()
        job=tmp/"approved"
        job.mkdir(mode=0o700)
        allowed=job/"input.txt"
        allowed.write_text(nonce,encoding="ascii")
        hidden=tmp/"host_private_sentinel"
        hidden.write_text(nonce,encoding="ascii")
        out_file=job/"probe_stdout.txt"
        err_file=job/"probe_stderr.txt"
        listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        listener.bind(("127.0.0.1",0))
        listener.listen(1)
        listener.settimeout(3)
        port=listener.getsockname()[1]
        # The only worker command is a fixed, local Python -S probe (no shell).
        # A network namespace that accidentally shares the host will be able
        # to connect to the known host-only listener and MUST be rejected.
        script=(
            "import os,json,socket;"
            "from pathlib import Path;"
            f"allowed=Path({str(allowed)!r});"
            f"hidden=Path({str(hidden)!r});"
            "s=socket.socket(socket.AF_INET,socket.SOCK_STREAM);"
            "s.settimeout(1.0);"
            f"net_result=s.connect_ex(('127.0.0.1',{port}));"
            "s.close();"
            "print(json.dumps({"
            "'net':os.readlink('/proc/self/ns/net'),"
            "'mount':os.readlink('/proc/self/ns/mnt'),"
            "'cgroup':Path('/proc/self/cgroup').read_text().split('0::',1)[-1].strip(),"
            "'allowed':allowed.read_text()=="+repr(nonce)+","
            "'hidden':hidden.exists(),"
            "'host_loopback_connected':net_result==0"
            "}),flush=True)"
        )
        proc=None
        try:
            with out_file.open("wb") as out,err_file.open("wb") as err:
                proc=launch_contained(
                    [str(binary),"-S","-c",script],
                    cwd=str(job),stdout=out,stderr=err,memory_mb=1024,
                    linux_cgroup_tree_required=True,
                    private_isolation_required=True)
                worker_leaf=proc.cgroup.resolve(strict=True)
                worker_procs=(worker_leaf/"cgroup.procs").read_text().split()
                if str(proc.pid) not in worker_procs:
                    raise RuntimeError("Kernel failed to place root worker in delegated cgroup")
                guardian=Path(f"/proc/{proc._guardian.pid}/cgroup").read_text()
                if worker_leaf.name in guardian:
                    raise RuntimeError("Private worker guardian incorrectly resides inside worker leaf")
                rc=proc.wait(timeout=15)
            stderr=err_file.read_text("utf8",errors="replace")[-3000:]
            if rc!=0:
                raise RuntimeError("Private kernel namespace probe exited nonzero: "+stderr)
            report=json.loads(out_file.read_text("utf8"))
            expected_cgroup="/"+worker_leaf.relative_to(
                Path("/sys/fs/cgroup")).as_posix()
            if (type(report) is not dict or
                    report.get("net")==parent_net or
                    report.get("mount")==parent_mount or
                    report.get("cgroup")!=expected_cgroup or
                    report.get("allowed") is not True or
                    report.get("hidden") is not False or
                    report.get("host_loopback_connected") is not False):
                raise RuntimeError("Actual private kernel namespaces/cgroup/egress denial not proved")
            proc.close()
            proc=None
            return {
                "contract":"nvp.p1f.real_kernel_boundary_probe.v1",
                "checked":True,
                "namespace_executable_sha256":preflight["namespace_executable_sha256"],
                "host_cgroup":parent_cgroup,
                "worker_cgroup":expected_cgroup,
                "host_network_namespace":parent_net,
                "worker_network_namespace":report["net"],
                "host_mount_namespace":parent_mount,
                "worker_mount_namespace":report["mount"],
                "approved_source_read":True,
                "outside_job_file_hidden":True,
                "host_loopback_denied":True,
                "guardian_outside_worker_leaf":True,
                "private_project_staged":False,
            }
        finally:
            listener.close()
            if proc is not None:
                try:
                    if proc.poll() is None:
                        proc.terminate_tree()
                finally:
                    proc.close()
