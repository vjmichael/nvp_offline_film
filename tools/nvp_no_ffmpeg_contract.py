"""DA-00: check the active native NVP application has no FFmpeg dependency.

Historical media modules and old tests are source-control evidence, not
permission to package or execute them. The audit follows native Python
imports, including imports nested in functions, and refuses executable
FFmpeg/ffprobe calls on all reached paths. Guard also checks the new
installer workflow and requirements. CI must run this check on every
candidate; a passing static check is NOT a substitute for installed-app
verification or a complete historical-code migration.
"""
from __future__ import annotations

import ast
from collections import deque
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
ENTRYPOINTS=(
    "tools/nvp_desktop_alpha.py",
    "tools/nvp_data_av_installed_acceptance.py",
    "backend/nvp_api.py",
    "backend/nvp_data_av_source.py",
    "backend/nvp_data_av_scene.py",
    "backend/nvp_data_av_usd.py",
    "backend/nvp_data_av_desktop.py",
    "backend/nvp_slate08b_native_camera_ipc.py",
    "backend/nvp_wo4_mastering_decision.py",
    "backend/nvp_wo4_loudness_stream.py",
)
# Standalone PyAV (av) is forbidden as an imported package, but an
# internal source module such as nvp_data_av_scene is NOT the PyAV package.
BAN=re.compile(r"(?:^|[._/\\])(?:ffmpeg|ffprobe|imageio_ffmpeg|libavcodec|"
               r"libavformat|libavutil|libavfilter|libavdevice|libswscale|"
               r"libswresample|avcodec|avformat)(?:$|[._/\\-])|"
               r"(?:^|[./\\])av(?:$|[./\\])",re.I)
NAME=re.compile(r"\b(?:ffmpeg|ffprobe|imageio_ffmpeg|avcodec|avformat|"
                r"libavcodec|libavformat|libavutil|libavfilter|libavdevice|"
                r"libswscale|libswresample)\b",re.I)
SHELL_CALLS={"run","Popen","check_call","check_output","call","which",
             "system","spawnv","spawnve","execv","execve","execvp","execvpe",
             "popen"}


def source_path(mod):
    if not mod.startswith(("backend.","tools.")):
        return None
    parts=mod.split(".")
    base=ROOT.joinpath(*parts)
    module_file=base.with_suffix(".py")
    if module_file.is_file():
        return module_file
    # Python package imports execute __init__.py before their children.
    # Skipping package initializers leaves an executable dependency blind spot.
    initializer=base/"__init__.py"
    return initializer if initializer.is_file() else None


def dotted(node):
    if isinstance(node,ast.Name):
        return node.id
    if isinstance(node,ast.Attribute):
        result=dotted(node.value)
        return (result+"." if result else "")+node.attr
    return ""


def imports(tree, current_path=None):
    result=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):
            result.extend(x.name for x in node.names)
        elif isinstance(node,ast.ImportFrom):
            name=node.module or ""
            if node.level==0:
                # Absolute imports can be resolved without a package context.
                result.append(name)
                result.extend(name+"."+a.name for a in node.names
                              if a.name!="*")
            elif current_path:
                # Never treat an invalid relative import that escapes its
                # package as an absolute module. Auditing imaginary modules
                # is not proof of the active runtime dependency graph.
                package=current_path.removesuffix(".py").split("/")[:-1]
                if node.level <= len(package):
                    prefix=package[:len(package)-node.level+1]
                    base=".".join(prefix+([name] if name else []))
                    if base:
                        result.append(base)
                        result.extend(base+"."+a.name for a in node.names
                                      if a.name!="*")
    return result


def reached_runtime():
    frontier=deque(ENTRYPOINTS)
    seen=set()
    while frontier:
        path=frontier.popleft()
        if path in seen:
            continue
        seen.add(path)
        # Importing backend.scenes.shot also executes backend/__init__.py
        # and backend/scenes/__init__.py. Audit those before treating the
        # leaf module as a complete representation of the runtime graph.
        parts=Path(path).parts[:-1]
        for depth in range(1,len(parts)+1):
            initializer=Path(*parts[:depth])/"__init__.py"
            rel=initializer.as_posix()
            if (ROOT/initializer).is_file() and rel not in seen:
                frontier.append(rel)
        absolute=ROOT/path
        if not absolute.is_file():
            raise RuntimeError("Missing packaged native source: "+path)
        tree=ast.parse(absolute.read_text("utf-8"),filename=path)
        yield path,tree
        # Traverse local absolute and relative imports without escaping packages.
        for mod in imports(tree, path):
            dep=source_path(mod)
            if dep:
                rel=dep.relative_to(ROOT).as_posix()
                if rel not in seen:frontier.append(rel)


def violations():
    issues=[]
    for path,tree in reached_runtime():
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                for imp in node.names:
                    if BAN.search(imp.name):
                        issues.append((path,node.lineno,"forbidden imported codec"))
            elif isinstance(node,ast.ImportFrom):
                # Inspect the complete imported symbols, not just the module.
                # 'from . import av' and 'from safe import ffmpeg' otherwise
                # evade the codec ban even when reached by a native entrypoint.
                names=imports(ast.Module(body=[node],type_ignores=[]),path)
                if any(BAN.search(name) for name in names):
                    issues.append((path,node.lineno,"forbidden imported codec"))
            elif isinstance(node,ast.Call):
                target=dotted(node.func)
                method=target.split(".")[-1]
                # Source words in explanatory text, tests and no-FFmpeg
                # permission notices are not executable codec calls.
                if method in SHELL_CALLS or target in (
                        "importlib.import_module","__import__"):
                    value=ast.dump(node,include_attributes=False)
                    if NAME.search(value):
                        issues.append((path,node.lineno,
                                       "forbidden executable codec dispatch"))
    for manifest in ("requirements-foundation.txt",
                     ".github/workflows/nvp-data-av01-native.yml"):
        file=ROOT/manifest
        if not file.is_file():
            issues.append((manifest,0,"missing native dependency manifest"))
            continue
        text=file.read_text("utf-8")
        for lineno,line in enumerate(text.splitlines(),1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if re.search(r"\b(?:pip|npm|apt-get|choco|winget|brew|cargo)\b",line) and (
                    re.search(r"\b(?:ffmpeg|ffprobe|imageio-ffmpeg|libavcodec|libavformat)\b",line,re.I)):
                issues.append((manifest,lineno,"installer pulls FFmpeg"))
        if "collect-submodules backend" in text or "collect-all backend" in text:
            issues.append((manifest,0,"installer indiscriminately bundles historical codecs"))
    return issues


def main():
    problems=violations()
    for path,line,why in problems:
        print(f"{path}:{line}: {why}",file=sys.stderr)
    if problems:
        return 1
    print("NVP_ACTIVE_NO_FFMPEG_POLICY_PASS")
    return 0


if __name__=="__main__":
    sys.exit(main())
