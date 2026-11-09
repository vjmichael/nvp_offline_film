"""CI-only download of a known tiny GGUF; never shipped in NVP installer.

Fetch the exact resolved model commit, capture its file digest, and expose
the absolute path to subsequent genuine native llama.cpp test steps.
If Hugging Face/runner network is unavailable, FAIL instead of substituting
a canned model response or skipping real inference.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path

REPO="tensorblock/SmolLM2-135M-Instruct-GGUF"
FILE="SmolLM2-135M-Instruct-Q3_K_M.gguf"


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--directory",required=True)
    parser.add_argument("--manifest",required=True)
    a=parser.parse_args()
    from huggingface_hub import HfApi,hf_hub_download
    from tools.nvp_wo6_07b_real_gguf_smoke import checked_path,sha256_file
    directory=Path(a.directory).resolve()
    directory.mkdir(parents=True,exist_ok=True)
    info=HfApi().model_info(REPO,revision="main")
    commit=info.sha
    if not isinstance(commit,str) or len(commit)!=40:
        raise RuntimeError("No exact model snapshot commit from Hugging Face")
    location=hf_hub_download(
        repo_id=REPO,filename=FILE,revision=commit,
        local_dir=str(directory))
    model=checked_path(Path(location).resolve(),model=True)
    receipt={
        "format":"nvp.wo6_07b.ci_model_source_provenance.v1",
        "repository":REPO,"filename":FILE,"resolved_commit_sha":commit,
        "model_sha256":sha256_file(model),"file_size_bytes":model.stat().st_size,
        "license_clearance_for_distribution":False,
        "model_bundled_in_nvp_installer":False,
        "test_only":True,
    }
    manifest=Path(a.manifest)
    if not manifest.is_absolute() or manifest.exists() or not manifest.parent.is_dir():
        raise PermissionError("One new absolute manifest required")
    manifest.write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n",encoding="utf8")
    output=os.getenv("GITHUB_ENV")
    if output:
        with open(output,"a",encoding="utf8") as fd:
            fd.write("NVP_TEST_GGUF_PATH="+str(model)+"\n")
    print(json.dumps(receipt,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
