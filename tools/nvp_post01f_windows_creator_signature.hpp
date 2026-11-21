#pragma once
// Separate exact POST-01F LTX creator approval, NOT Blender's original-frame
// scope. Detached CMS signed in a separate reviewed director desktop action.
// The SCM LocalSystem broker independently pins creator cert hash at install.
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
namespace nvp_post01f_creator {
namespace fs=std::filesystem;
struct Scope {
    std::string ticket,project,job,plan,model_stack,bootstrap,layout,look,
                conditioning,nonce,expires;
};
inline std::string message(const Scope& s) {
    return "nvp.post01f.ltx.creator_scope.v1\n"
      "operation=nvp.post01f.ltx_picture_generation.v1\n"
      "ticket="+s.ticket+"\n"
      "project_id="+s.project+"\n"
      "job_id="+s.job+"\n"
      "plan_sha256="+s.plan+"\n"
      "model_stack_sha256="+s.model_stack+"\n"
      "bootstrap_sha256="+s.bootstrap+"\n"
      "layout_sha256="+s.layout+"\n"
      "look_sha256="+s.look+"\n"
      "conditioning_sha256="+s.conditioning+"\n"
      "receipt_nonce="+s.nonce+"\n"
      "expires_utc_epoch_seconds="+s.expires+"\n";
}
inline std::string cert_hash(PCCERT_CONTEXT cert) {
    DWORD count=0;
    if(!CertGetCertificateContextProperty(cert,CERT_SHA256_HASH_PROP_ID,nullptr,&count)||count!=32)
        throw std::runtime_error("No native Windows creator certificate SHA256");
    BYTE digest[32]{};
    if(!CertGetCertificateContextProperty(cert,CERT_SHA256_HASH_PROP_ID,digest,&count)||count!=32)
        throw std::runtime_error("Cannot read exact creator certificate digest");
    std::ostringstream out;out<<std::hex<<std::setfill('0');
    for(BYTE x:digest)out<<std::setw(2)<<static_cast<unsigned>(x);
    return out.str();
}
inline bool verify(const Scope& s,const fs::path& path,const std::string& pinned) {
    if(pinned.size()!=64 || !std::all_of(pinned.begin(),pinned.end(),[](char c){
        return (c>='0'&&c<='9')||(c>='a'&&c<='f');}))
        throw std::runtime_error("Installer-pinned independent creator signer absent");
    if(s.expires.size()<10||s.expires.size()>12||
       !std::all_of(s.expires.begin(),s.expires.end(),[](char c){return c>='0'&&c<='9';}))
        throw std::runtime_error("Invalid creator consent expiry");
    const auto expires=std::stoll(s.expires);
    const auto now=static_cast<long long>(std::time(nullptr));
    if(expires<now || expires>now+900)
        throw std::runtime_error("Creator consent expired or exceeds 15-minute authority");
    if(fs::is_symlink(path) || !fs::is_regular_file(path) ||
       fs::file_size(path)<96 || fs::file_size(path)>65536)
        throw std::runtime_error("Native creator signature missing, linked or unbounded");
    const auto size=static_cast<size_t>(fs::file_size(path));
    std::vector<BYTE> bytes(size);
    std::ifstream input(path,std::ios::binary);
    input.read(reinterpret_cast<char*>(bytes.data()),static_cast<std::streamsize>(size));
    if(!input || input.gcount()!=static_cast<std::streamsize>(size))
        throw std::runtime_error("Incomplete native creator signature read");
    const std::string content=message(s);
    const BYTE* originals[]={reinterpret_cast<const BYTE*>(content.data())};
    DWORD sizes[]={static_cast<DWORD>(content.size())};
    CRYPT_VERIFY_MESSAGE_PARA para{};
    para.cbSize=sizeof(para);
    para.dwMsgAndCertEncodingType=X509_ASN_ENCODING|PKCS_7_ASN_ENCODING;
    PCCERT_CONTEXT signer=nullptr;
    BOOL okay=CryptVerifyDetachedMessageSignature(&para,0,bytes.data(),
                   static_cast<DWORD>(bytes.size()),1,originals,sizes,&signer);
    if(!okay||!signer)throw std::runtime_error("Creator detached CMS did not verify");
    try {
        if(CertVerifyTimeValidity(nullptr,signer->pCertInfo)!=0 || cert_hash(signer)!=pinned)
            throw std::runtime_error("Creator signer not within installed independent trust policy");
    } catch(...) {CertFreeCertificateContext(signer);throw;}
    CertFreeCertificateContext(signer);
    return true;
}
}
