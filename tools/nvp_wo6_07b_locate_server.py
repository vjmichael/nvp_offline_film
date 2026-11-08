"""Locate exactly one freshly built test-only llama.cpp server artifact."""
import json
import os
from pathlib import Path
import sys

from tools.nvp_wo6_07b_real_gguf_smoke import checked_path,sha256_file


def main(argv=None):
    args=sys.argv[1:] if argv is None else argv
    if len(args)!=1:
        raise ValueError("Supply one test-only llama.cpp build directory")
    root=Path(args[0]).resolve()
    if not root.is_dir():
        raise FileNotFoundError("The native test compiler produced no build tree")
    filename="llama-server.exe" if os.name=="nt" else "llama-server"
    found=[x for x in root.rglob(filename) if x.is_file() and not x.is_symlink()]
    if len(found)!=1:
        raise RuntimeError(f"Expected one native llama-server, found {len(found)}")
    artifact=checked_path(found[0])
    info={"llama_server_sha256":sha256_file(artifact),
          "local_binary_size_bytes":artifact.stat().st_size}
    with open(os.environ["GITHUB_ENV"],"a",encoding="utf8") as fd:
        fd.write("NVP_TEST_LLAMA_SERVER="+str(artifact)+"\n")
    print(json.dumps(info,sort_keys=True))


if __name__=="__main__":
    main()
