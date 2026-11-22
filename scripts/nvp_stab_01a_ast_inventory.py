#!/usr/bin/env python3
"""NVP-STAB-01A exact-head read-only static AST and dependency inventory.
No runtime, native workers, model loading, project access, or release claims.
"""
import argparse,ast,csv,json,re,subprocess,tomllib
from pathlib import Path
from collections import defaultdict,deque

def git(*x):return subprocess.check_output(["git",*x]).decode().strip()
def dump(path,cols,rows):
    with path.open("w",newline="",encoding="utf8") as f:
        w=csv.writer(f);w.writerow(cols);w.writerows(rows)
def target(mod, known):
    p=mod.replace(".","/")
    return next((x for x in (p+".py",p+"/__init__.py") if x in known),None)
def rel(source,dst,known):
    parts=[]
    for part in (Path(source).parent/dst).parts:
        if part=="..":
            if parts:parts.pop()
        elif part not in ("","."):parts.append(part)
    p="/".join(parts)
    return next((x for x in [p]+[p+s for s in (".js",".jsx",".mjs",".ts",".tsx",".py",".h",".hpp",".rs",".json")]+[p+"/index"+s for s in (".js",".jsx",".ts",".tsx",".mjs")] if x in known),None)
def main():
    a=argparse.ArgumentParser()
    a.add_argument("--repo",required=True,type=Path);a.add_argument("--out",required=True,type=Path);a.add_argument("--sha",required=True)
    args=a.parse_args();root=args.repo.resolve(strict=True);out=args.out.resolve()
    assert (root/".git").exists() and root!=out and root not in out.parents
    sha=git("-C",str(root),"rev-parse","HEAD");assert sha==args.sha,(sha,args.sha)
    files=sorted(p for p in subprocess.check_output(["git","-C",str(root),"ls-files","-z"]).decode().split("\0") if p)
    known=set(files);out.mkdir(parents=True,exist_ok=True)
    edges=[];calls=[];tests=[];unresolved=[];source=[];native=[];deps=[];flows=[];graph=defaultdict(set)
    js_re=re.compile(r"""(?:\b(?:import|export)\s+(?:[^\n;]*?\s+from\s+)?|\bimport\s*\()\s*['"](\.[^'"]+)['"]""")
    native_re=re.compile(r"CreateProcess|StartService|AssignProcessToJobObject|NCryptSignHash|BCryptHashData|AppContainer|\bffmpeg\b|\bffprobe\b",re.I)
    for file in files:
        f=root/file
        if not f.is_file() or f.is_symlink():
            unresolved.append((file,0,"missing/linked file",""));continue
        if f.suffix not in (".py",".js",".jsx",".mjs",".ts",".tsx",".c",".cpp",".h",".hpp",".rs",".nsi",".ps1",".sh",".yml",".yaml",".proto",".cmd",".bat") and f.name not in ("Cargo.lock","package-lock.json","Cargo.toml","package.json") and not f.name.startswith("requirements"):continue
        try:s=f.read_text(encoding="utf8")
        except Exception as e:unresolved.append((file,0,"unreadable",type(e).__name__));continue
        source.append((file,len(s),f.suffix))
        if f.suffix==".py":
            try:t=ast.parse(s,filename=file)
            except SyntaxError as e:
                unresolved.append((file,e.lineno or 0,"Python syntax",e.msg));continue
            for n in ast.walk(t):
                if isinstance(n,ast.Import):
                    mods=[q.name for q in n.names];kind="AST import"
                elif isinstance(n,ast.ImportFrom):
                    module=n.module or ""
                    if n.level:
                        pkg=file[:-3].split("/")[:-1];up=n.level-1
                        pkg=pkg[:-up] if up else pkg
                        module=".".join(pkg+[module] if module else pkg)
                    mods=[module]+[module+"."+q.name for q in n.names if q.name!="*"];kind="AST from"
                else:mods=[]
                for mod in mods:
                    dst=target(mod,known)
                    if dst:
                        edges.append((file,dst,getattr(n,"lineno",0),kind));graph[file].add(dst)
                if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith("test_") and file.startswith("tests/"):
                    tests.append((file,n.lineno,n.name,"static definition—not executed"))
                if isinstance(n,ast.Call):
                    try:expr=ast.unparse(n.func)
                    except Exception:expr="<unparseable>"
                    if re.search(r"^(?:subprocess\.|os\.(?:exec|spawn|system)|importlib\.|__import__|exec$|eval$|getattr$|setattr$|ctypes\.|cffi\.)|\.add_api_route$|\.include_router$",expr):
                        kind="dynamic/reflection" if re.search(r"__import__|importlib|exec$|eval$|getattr$|setattr$",expr) else "launch/API"
                        calls.append((file,n.lineno,expr,kind))
                        if kind=="dynamic/reflection":unresolved.append((file,n.lineno,"dynamic AST call",expr))
                        if expr in ("__import__","importlib.import_module") and n.args and isinstance(n.args[0],ast.Constant) and isinstance(n.args[0].value,str):
                            dst=target(n.args[0].value,known)
                            if dst:edges.append((file,dst,n.lineno,"AST literal dynamic import"));graph[file].add(dst)
        if f.suffix in (".js",".jsx",".mjs",".ts",".tsx"):
            for m in js_re.finditer(s):
                dst=rel(file,m.group(1),known);line=s.count("\n",0,m.start())+1
                if dst:edges.append((file,dst,line,"JS literal"));graph[file].add(dst)
                elif not m.group(1).endswith((".css",".svg",".png",".jpg")):unresolved.append((file,line,"JS unresolved relative import",m.group(1)))
        if f.suffix in (".cpp",".c",".hpp",".h"):
            for m in re.finditer(r'^\s*#\s*include\s*"([^"]+)"',s,re.M):
                dst=rel(file,m.group(1),known);line=s.count("\n",0,m.start())+1
                if dst:edges.append((file,dst,line,"C/C++ local header"));graph[file].add(dst)
                else:unresolved.append((file,line,"external/generated native include",m.group(1)))
        if f.suffix==".rs":
            for m in re.finditer(r"^\s*(?:pub\s+)?mod\s+(\w+)\s*;",s,re.M):
                dst=rel(file,m.group(1)+".rs",known) or rel(file,m.group(1)+"/mod.rs",known)
                if dst:edges.append((file,dst,s.count("\n",0,m.start())+1,"Rust module"));graph[file].add(dst)
                else:unresolved.append((file,s.count("\n",0,m.start())+1,"Rust mod unresolved",m.group(1)))
        if f.suffix in (".py",".cpp",".c",".h",".hpp",".rs",".ps1",".sh",".cmd"):
            for m in native_re.finditer(s):native.append((file,s.count("\n",0,m.start())+1,m.group(0),"lexical candidate only"))
        if file.startswith(".github/workflows/"):
            flows.append((file,";".join(sorted(set(re.findall(r"test_[\w*]+\.py",s)))),bool(re.search(r"\bif:|skipif|skipUnless",s)),bool(re.search(r"blender|PyInstaller|makensis|cmake|cargo test",s,re.I))))
    for req in sorted(root.glob("requirements*.txt")):
        for x in req.read_text("utf8").splitlines():
            if x.strip() and not x.lstrip().startswith("#"):deps.append((req.name,x.strip(),"Python declared"))
    for path,ecosystem in (("frontend/package-lock.json","npm lock"),("native/nvp_lu_ipc_client/Cargo.lock","Rust lock")):
        f=root/path
        if f.is_file():
            try:
                d=json.loads(f.read_text("utf8")) if ecosystem=="npm lock" else tomllib.loads(f.read_text("utf8"))
                seq=[(k,v.get("version","")) for k,v in d.get("packages",{}).items() if k] if ecosystem=="npm lock" else [(v["name"],v["version"]) for v in d.get("package",[])]
                for name,version in seq:deps.append((path,name+"@"+version,ecosystem))
            except Exception as e:unresolved.append((path,0,"lockfile parse error",str(e)))
    roots=[p for p in ("backend/nvp_api.py","tools/nvp_desktop_alpha.py","frontend/src/main.jsx","frontend/src/postproduction-entry.jsx") if p in known]
    reachable=set();queue=deque(roots)
    while queue:
        n=queue.popleft()
        if n in reachable:continue
        reachable.add(n);queue.extend(graph[n]-reachable)
    dump(out/"ast_import_graph.csv",["source","target","line","kind"],sorted(set(edges)))
    dump(out/"ast_dynamic_calls.csv",["path","line","expression","kind"],calls)
    dump(out/"ast_test_definitions.csv",["path","line","test","evidence_type"],tests)
    dump(out/"native_candidates.csv",["path","line","name","evidence_type"],native)
    dump(out/"unresolved_candidates.csv",["path","line","kind","detail"],unresolved)
    dump(out/"source_files.csv",["path","characters","extension"],source)
    dump(out/"workflow_declarations.csv",["path","tests","conditional","native_indicators"],flows)
    dump(out/"dependency_inventory.csv",["source","package","ecosystem"],deps)
    summary=dict(format="nvp.stab01a.ast_inventory.v1",sha=sha,tracked_files=len(files),read_source_files=len(source),backend_python=sum(p.startswith("backend/") and p.endswith(".py") for p in files),test_python=sum(p.startswith("tests/") and p.endswith(".py") for p in files),frontend_js=sum(p.startswith("frontend/") and p.endswith((".jsx",".js",".mjs",".ts",".tsx")) for p in files),ast_import_edges=len(set(edges)),dynamic_callsite_candidates=len(calls),native_lexical_candidates=len(native),test_definitions=len(tests),dependency_records=len(deps),unresolved_candidates=len(unresolved),workflow_files=len(flows),static_root_reachability=len(reachable),runtime_execution_verified=False,physical_install_verified=False,signer_authority_verified=False)
    (out/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n","utf8")
    (out/"README.md").write_text("# NVP-STAB-01A static analysis\n\nGenerated from an exact real Git checkout. AST import/call source candidates are not real executed functions, signed identities or user approvals.\n","utf8")
    print(json.dumps(summary,sort_keys=True))
    if summary["tracked_files"]<1500 or summary["backend_python"]!=485 or summary["test_python"]<430 or summary["frontend_js"]<108 or summary["ast_import_edges"]<500 or summary["test_definitions"]<100:
        raise SystemExit("INCOMPLETE_AST_SOURCE_CENSUS")
    if any(x[2]=="Python syntax" for x in unresolved):raise SystemExit("PYTHON_SYNTAX_PARSE_FAILED")
if __name__=="__main__":main()
