"""Only synthetic native CI source fixtures may use this authority.
No production entrypoint imports it. Never infer production consent from CI.
"""
from functools import lru_cache
import json
import os
from pathlib import Path
from backend.nvp_wo3_native_codecs import (
    ProtectedCodecAuthority,ApprovedCodecBinary,ROLES)
from backend.nvp_wo3_codec_bundle_provenance import DUAL_QUALIFICATION_FORMAT

@lru_cache(maxsize=1)
def authority():
    bundle=Path(os.environ["NVP_WO3_FIXTURE_BUNDLE"])
    runtime=Path(os.environ["NVP_WO3_FIXTURE_ROOT"])
    manifest=json.loads((bundle/"nvp-codec-manifest.json").read_text("ascii"))
    seen=set()
    def approved(scope):
        identity=(scope["job_id"],scope.get("invocation_id"))
        if identity in seen or scope["project_id"]!="wo3-generated-ci-fixture":
            return False
        seen.add(identity)
        return True
    return ProtectedCodecAuthority(bundle,manifest,
        manifest_sha256=os.environ["NVP_WO3_FIXTURE_MANIFEST_PIN"],
        runtime=runtime,project_id="wo3-generated-ci-fixture",
        authorize_stage=approved,authorize_execution=approved,check_cancel=lambda:False,
        dual_decoder_qualification=manifest["format"]==DUAL_QUALIFICATION_FORMAT)

def fixture_codec(env,product):
    host=authority()
    item=host.manifest["tools"][ROLES[product]]
    return ApprovedCodecBinary(Path(os.environ[env]),sha256=item["sha256"],
                               product=product,authority=host)

def provision_generated_ci_fixture():
    """Build-time fixture provisioning only, from the pinned CI source builds."""
    import hashlib
    import shutil
    from backend.nvp_wo3_codec_bundle_provenance import (
        REQUIRED,FORMAT,DUAL_QUALIFICATION_REQUIRED,verify_native_codec_bundle)
    if os.name!="nt" or os.environ.get("GITHUB_ACTIONS")!="true":
        raise PermissionError("Dedicated Windows CI fixture only")
    root=Path(os.environ["NVP_WO3_FIXTURE_BUNDLE"])
    root.mkdir()
    source=Path(os.environ["NVP_WO3_BUILD_TOOLS"])
    names={"openjpeg-encoder":"opj_compress.exe",
           "openjpeg-decoder":"opj_decompress.exe",
           "asdcp-wrap":"asdcp-wrap.exe",
           "asdcp-info":"asdcp-info.exe",
           "asdcp-unwrap":"asdcp-unwrap.exe"}
    dual=os.environ.get("NVP_WO3_DUAL_QUALIFICATION")=="1"
    if dual:names["jasper-decoder"]="nvp_jasper_decode.exe"
    tools={}
    for role,(product,license_id) in (DUAL_QUALIFICATION_REQUIRED if dual else REQUIRED).items():
        binary=root/names[role]
        shutil.copyfile(source/names[role],binary)
        notice=root/(product+".LICENSE")
        if not notice.exists():
            license_path={"OpenJPEG":"deps/openjpeg/LICENSE","asdcplib":"deps/asdcplib/COPYING","JasPer":"deps/jasper/LICENSE.txt"}[product]
            shutil.copyfile(Path(license_path),notice)
        tools[role]={"product":product,"license":license_id,
                     "filename":binary.name,"sha256":hashlib.sha256(binary.read_bytes()).hexdigest(),
                     "license_notice":notice.name,
                     "license_sha256":hashlib.sha256(notice.read_bytes()).hexdigest()}
    manifest={"format":DUAL_QUALIFICATION_FORMAT if dual else FORMAT,"tools":tools}
    verify_native_codec_bundle(root,manifest,allow_dual_qualification=dual)
    raw=json.dumps(manifest,sort_keys=True,separators=(",",":"),
                   ensure_ascii=True).encode("ascii")
    (root/"nvp-codec-manifest.json").write_bytes(raw)
    print(hashlib.sha256(raw).hexdigest())

if __name__=="__main__":
    provision_generated_ci_fixture()
