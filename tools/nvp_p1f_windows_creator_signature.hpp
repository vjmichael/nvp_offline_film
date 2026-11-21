#pragma once
// Native Windows P1-F independent creator signoff verifier.
// A trusted desktop approval UI signs ONE exact film-source scope using its
// private certificate. SCM verifies a detached CMS/PKCS7 signature against an
// exact installer-pinned signing certificate hash. No key, grant or arbitrary
// command can be authored by a project file or model.
// This verifier is NOT permission to release/execute private film by itself.
#include <windows.h>
#include <wincrypt.h>
#include <filesystem>
#include <string>
#include <vector>
#include <fstream>
#include <algorithm>
#include <stdexcept>
#include <ctime>
#include <iomanip>
#include <sstream>
#pragma comment(lib,"crypt32.lib")

namespace nvp_p1f_creator_signature {
namespace fs=std::filesystem;

struct SignedScope {
    std::string ticket,project_id,job_id,plan_sha256,blender_sha256,
        script_sha256,usd_sha256,pcm_sha256,frame_spec_sha256,
        expires_utc_epoch_seconds;
};

inline std::string message(const SignedScope& v) {
    return
        "nvp.p1f.original.creator_signoff.v1\n"
        "operation=nvp.p1f.render_original_cycles_frame.v1\n"
        "ticket="+v.ticket+"\n"
        "project_id="+v.project_id+"\n"
        "job_id="+v.job_id+"\n"
        "plan_sha256="+v.plan_sha256+"\n"
        "blender_sha256="+v.blender_sha256+"\n"
        "script_sha256="+v.script_sha256+"\n"
        "original_usd_sha256="+v.usd_sha256+"\n"
        "original_pcm_sha256="+v.pcm_sha256+"\n"
        "frame_spec_sha256="+v.frame_spec_sha256+"\n"
        "expires_utc_epoch_seconds="+v.expires_utc_epoch_seconds+"\n";
}

inline std::string cert_sha256_hex(PCCERT_CONTEXT cert) {
    DWORD n=0;
    if(!CertGetCertificateContextProperty(cert,CERT_SHA256_HASH_PROP_ID,
                                          nullptr,&n)||n!=32)
        throw std::runtime_error("Creator certificate SHA256 unavailable");
    BYTE digest[32]{};
    if(!CertGetCertificateContextProperty(cert,CERT_SHA256_HASH_PROP_ID,
                                          digest,&n)||n!=32)
        throw std::runtime_error("Creator certificate SHA256 could not be verified");
    std::ostringstream out;
    out<<std::hex<<std::setfill('0');
    for(BYTE b:digest)out<<std::setw(2)<<static_cast<unsigned>(b);
    return out.str();
}

inline std::vector<BYTE> sealed_signature_bytes(const fs::path& f) {
    if(fs::is_symlink(f)||!fs::is_regular_file(f))
        throw std::runtime_error("Missing immutable original creator signature");
    const auto n=fs::file_size(f);
    if(n<96||n>65536)
        throw std::runtime_error("Detached creator signature exceeds finite bound");
    std::ifstream in(f,std::ios::binary);
    std::vector<BYTE> result(static_cast<size_t>(n));
    in.read(reinterpret_cast<char*>(result.data()),static_cast<std::streamsize>(n));
    if(!in||in.gcount()!=static_cast<std::streamsize>(n))
        throw std::runtime_error("Incomplete immutable creator signature");
    return result;
}

inline bool verify(const SignedScope& scope,const fs::path& signature,
                   const std::string& pinned_cert_sha256) {
    if(pinned_cert_sha256.size()!=64||
       !std::all_of(pinned_cert_sha256.begin(),pinned_cert_sha256.end(),
           [](char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');}))
        throw std::runtime_error("No independently installer-pinned creator signer");
    const auto expires=std::stoll(scope.expires_utc_epoch_seconds);
    const auto now=static_cast<long long>(std::time(nullptr));
    if(expires<now||expires>now+900)
        throw std::runtime_error("Creator one-use signoff expired or exceeds 15-minute authority");
    const std::string body=message(scope);
    const std::vector<BYTE> bytes=sealed_signature_bytes(signature);
    const BYTE* originals[]={reinterpret_cast<const BYTE*>(body.data())};
    DWORD sizes[]={static_cast<DWORD>(body.size())};
    CRYPT_VERIFY_MESSAGE_PARA params{};
    params.cbSize=sizeof(params);
    params.dwMsgAndCertEncodingType=X509_ASN_ENCODING|PKCS_7_ASN_ENCODING;
    PCCERT_CONTEXT signer=nullptr;
    BOOL good=CryptVerifyDetachedMessageSignature(
        &params,0,bytes.data(),static_cast<DWORD>(bytes.size()),
        1,originals,sizes,&signer);
    if(!good||!signer)
        throw std::runtime_error("Creator-detached PKCS7 source approval signature invalid");
    try {
        if(CertVerifyTimeValidity(nullptr,signer->pCertInfo)!=0)
            throw std::runtime_error("Creator signing certificate outside validity interval");
        if(cert_sha256_hex(signer)!=pinned_cert_sha256)
            throw std::runtime_error("Creator signer differs from installer-pinned issuer");
    } catch(...) {CertFreeCertificateContext(signer);throw;}
    CertFreeCertificateContext(signer);
    return true;
}
}
