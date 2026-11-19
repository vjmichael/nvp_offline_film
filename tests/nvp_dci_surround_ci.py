"""Real pinned Windows 5.1 / 7.1DS native sound qualification; synthetic source only."""
import json
import os
from pathlib import Path
from hashlib import sha256
from uuid import uuid4
from backend.nvp_dci_surround import SOURCE_CHANNELS
from backend.nvp_dci_surround_native import qualify_native_surround
from backend.nvp_wo4_pcm_stream import _protected_path
from backend.nvp_w1g_encrypted_source import require_efs_stage
from backend.nvp_w1g_release_gate import inspect_original_process_journals
from nvp_wo3_fixture_authority import fixture_codec
from test_nvp_dci_surround import source_fixture


def run():
    if os.name!="nt" or os.environ.get("GITHUB_ACTIONS")!="true":
        raise PermissionError("Generated native Windows CI fixture only")
    root=Path(os.environ["NVP_WO3_FIXTURE_ROOT"]).absolute()/"surround-fixtures"
    root.mkdir(exist_ok=False);require_efs_stage(root)
    wrap=fixture_codec("NVP_NATIVE_ASDCP_WRAP","ASDCP-asdcp_wrap")
    info=fixture_codec("NVP_NATIVE_ASDCP_INFO","ASDCP-asdcp_info")
    unwrap=fixture_codec("NVP_NATIVE_ASDCP_UNWRAP","ASDCP-asdcp_unwrap")
    for profile,labels in SOURCE_CHANNELS.items():
        raw=source_fixture(len(labels),96000)
        path=root/(profile+".pcm")
        with path.open("xb") as stream:
            st=os.fstat(stream.fileno())
            if _protected_path(path)!=(st.st_dev,st.st_ino):raise PermissionError("EFS fixture identity")
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        size=48000*len(labels)*3
        reels=[{"id":str(uuid4()),"first_edit_unit":i*24,"edit_units":24,
                "source_pcm_sha256":sha256(raw[i*size:(i+1)*size]).hexdigest()} for i in range(2)]
        report=qualify_native_surround(wrap,info,unwrap,source_path=path,
            source_sha256=sha256(raw).hexdigest(),source_take_sha256=sha256(b"generated surround fixture").hexdigest(),
            profile=profile,labels=labels,total_edit_units=48,reels=reels,approve=lambda _:True)
        if (report["status"]!="PROTECTED_NATIVE_SURROUND_REFERENCE_EXACT" or
                report["samples_per_channel"]!=96000 or report["reel_count"]!=2 or
                not report["all_samples_exact"] or not report["mxf_channel_metadata_verified"] or not report["reel_continuity_verified"]):
            raise RuntimeError("Native surround qualification incomplete")
        print(json.dumps(report,sort_keys=True),flush=True)
    custody=inspect_original_process_journals()
    if custody["unresolved_original_native_launches"] or custody["original_windows_launch_journals_verified"]<1:
        raise RuntimeError("Native custody not verified")

if __name__=="__main__":run()
