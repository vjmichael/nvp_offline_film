// P1-F trusted Windows creator-desktop ONE-USE signoff.
// This program requires an explicit native human Yes/No dialog, user-owned
// nonexportable certificate private key and an exact admin-pinned service
// job/source/expiry scope. It never launches Blender, creates system grants,
// changes WFP filters, starts SCM, supplies arbitrary paths or self-authorizes.
// A model/batch approval cannot substitute for the visible operator dialog.
//
// Installed exe must be separately reviewed/signed and invoked ONLY by the
// trusted creator UI; no unattended or --yes/--accept flags are available.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wincrypt.h>
#include <filesystem>
#include <string>
#include <vector>
#include <array>
#include <algorithm>
#include <iostream>
#include <ctime>
#include "nvp_p1f_windows_creator_signature.hpp"
#pragma comment(lib,"crypt32.lib")
#pragma comment(lib,"advapi32.lib")
#pragma comment(lib,"user32.lib")

namespace fs=std::filesystem;
static constexpr wchar_t APPROVED[]=L"SOFTWARE\\NVP\\P1F\\ApprovedPreview";
static constexpr wchar_t TRUST[]=L"SOFTWARE\\NVP\\P1F\\CreatorTrust";

static void required(bool condition,const char* description) {
    if(!condition)throw std::runtime_error(description);
}
static std::wstring reg_value(HKEY h,const wchar_t* key) {
    DWORD type=0,n=0;
    LONG rc=RegQueryValueExW(h,key,nullptr,&type,nullptr,&n);
    required(rc==ERROR_SUCCESS&&type==REG_SZ&&n>=2&&n<=1024,
             "No exact administrator-approved creator source scope");
    std::vector<wchar_t> buf(n/2+1,0);
    required(RegQueryValueExW(h,key,nullptr,&type,
        reinterpret_cast<BYTE*>(buf.data()),&n)==ERROR_SUCCESS,
        "Unable to read trusted NVP job scope");
    return std::wstring(buf.data());
}
static std::wstring machine_value(const wchar_t* key,const wchar_t* field) {
    HKEY h=nullptr;
    required(RegOpenKeyExW(HKEY_LOCAL_MACHINE,key,0,KEY_READ,&h)==ERROR_SUCCESS,
             "No independent NVP release/approval registry policy");
    try {
        auto r=reg_value(h,field);RegCloseKey(h);return r;
    } catch(...) {RegCloseKey(h);throw;}
}
static std::string ascii(const std::wstring& s) {
    required(!s.empty() && s.size()<=128 &&
             std::all_of(s.begin(),s.end(),[](wchar_t c){
                return c>=32&&c<=126;
             }),"Noncanonical creator job scope");
    return std::string(s.begin(),s.end());
}
static PCCERT_CONTEXT user_creator_certificate(const std::string& pinned) {
    HCERTSTORE store=CertOpenStore(CERT_STORE_PROV_SYSTEM_W,0,0,
                                  CERT_SYSTEM_STORE_CURRENT_USER,L"MY");
    required(store!=nullptr,"Trusted creator signing certificate store missing");
    PCCERT_CONTEXT match=nullptr;
    PCCERT_CONTEXT iterator=nullptr;
    while((iterator=CertEnumCertificatesInStore(store,iterator))!=nullptr) {
        try {
            if(nvp_p1f_creator_signature::cert_sha256_hex(iterator)==pinned &&
               CertVerifyTimeValidity(nullptr,iterator->pCertInfo)==0) {
                DWORD available=0;
                // Private key stays in creator user profile, not SCM.
                if(CertGetCertificateContextProperty(
                       iterator,CERT_KEY_PROV_INFO_PROP_ID,nullptr,&available)&&
                   available) {
                    match=CertDuplicateCertificateContext(iterator);
                    break;
                }
            }
        } catch(const std::exception&) {}
    }
    CertCloseStore(store,0);
    required(match!=nullptr,
             "Only the owner-enrolled, independent creator signing key may approve film");
    return match;
}
static std::filesystem::path sealed_job_root(const std::string& jobid) {
    required(jobid.size()>=2&&jobid.size()<=40&&
             (jobid[0]>='A'&&jobid[0]<='Z'||
              jobid[0]>='a'&&jobid[0]<='z')&&
             std::all_of(jobid.begin()+1,jobid.end(),[](char c){
                return (c>='a'&&c<='z')||(c>='A'&&c<='Z')||
                       (c>='0'&&c<='9')||c=='_'||c=='-';
             }),"Invalid fixed approved creator job ID");
    wchar_t program[MAX_PATH+1]{};
    DWORD n=GetEnvironmentVariableW(L"ProgramData",program,MAX_PATH);
    required(n>0&&n<MAX_PATH,"Trusted ProgramData path unavailable");
    auto root=fs::path(program)/L"NVP"/L"P1F"/L"ApprovedJobs"/
         std::wstring(jobid.begin(),jobid.end());
    required(!fs::is_symlink(root)&&fs::is_directory(root),
             "No trusted preapproved creator job root");
    return root;
}

static int approve() {
    required(machine_value(TRUST,L"PrivateReleaseAccepted")==L"1",
             "NVP signed private-film release/installer gate not authorized");
    required(machine_value(APPROVED,L"PublicFixtureOnly")==L"0",
             "Creator signer must never authorize the public fixture worker");
    nvp_p1f_creator_signature::SignedScope scope{
        ascii(machine_value(APPROVED,L"PendingId")),
        ascii(machine_value(APPROVED,L"ProjectId")),
        ascii(machine_value(APPROVED,L"JobId")),
        ascii(machine_value(APPROVED,L"OriginalPlanSha256")),
        ascii(machine_value(APPROVED,L"BlenderSha256")),
        ascii(machine_value(APPROVED,L"FixedScriptSha256")),
        ascii(machine_value(APPROVED,L"OriginalUsdSha256")),
        ascii(machine_value(APPROVED,L"OriginalPcmSha256")),
        ascii(machine_value(APPROVED,L"FrameSpecSha256")),
        ascii(machine_value(APPROVED,L"CreatorConsentExpiryUtc"))
    };
    auto issuer=ascii(machine_value(TRUST,L"SignerCertificateSha256"));
    const auto now=static_cast<long long>(std::time(nullptr));
    const auto expiration=std::stoll(scope.expires_utc_epoch_seconds);
    required(expiration>=now&&expiration<=now+900,
             "Creator one-use approval expired or exceeds 15-minute window");
    auto root=sealed_job_root(scope.job_id);
    auto receipt=root/L"creator_approval.p7s";
    required(!fs::exists(receipt)&&!fs::is_symlink(receipt),
             "Refuse duplicate or previously signed creator authorization");
    std::wstring prompt=
        L"Authorize ONE original NVP film frame?\n\nProject: "+
        std::wstring(scope.project_id.begin(),scope.project_id.end())+
        L"\nJob: "+std::wstring(scope.job_id.begin(),scope.job_id.end())+
        L"\nPlan SHA-256: "+
        std::wstring(scope.plan_sha256.begin(),scope.plan_sha256.end())+
        L"\nOriginal USD SHA-256: "+
        std::wstring(scope.usd_sha256.begin(),scope.usd_sha256.end())+
        L"\nOriginal PCM SHA-256: "+
        std::wstring(scope.pcm_sha256.begin(),scope.pcm_sha256.end())+
        L"\n\nThis is NOT approval of an entire film or a reusable batch.";
    int response=MessageBoxW(nullptr,prompt.c_str(),
        L"NVP — approve exactly one original-source Cycles frame",
        MB_YESNO|MB_ICONWARNING|MB_DEFBUTTON2|MB_TOPMOST|MB_SETFOREGROUND);
    required(response==IDYES,"Creator explicitly refused or closed one-use native dialog");
    PCCERT_CONTEXT creator=user_creator_certificate(issuer);
    const auto body=nvp_p1f_creator_signature::message(scope);
    const BYTE* message=reinterpret_cast<const BYTE*>(body.data());
    DWORD message_len=static_cast<DWORD>(body.size());
    CRYPT_SIGN_MESSAGE_PARA sign{};
    sign.cbSize=sizeof(sign);
    sign.dwMsgEncodingType=X509_ASN_ENCODING|PKCS_7_ASN_ENCODING;
    sign.pSigningCert=creator;
    sign.HashAlgorithm.pszObjId=const_cast<char*>(szOID_NIST_sha256);
    sign.cMsgCert=1;
    sign.rgpMsgCert=&creator;
    DWORD needed=0;
    BOOL first=CryptSignMessage(
        &sign,TRUE,1,&message,&message_len,nullptr,&needed);
    required(first&&needed>=96&&needed<=65536,
             "Creator certificate refused detached PKCS7 signoff");
    std::vector<BYTE> signed_bytes(needed);
    BOOL second=CryptSignMessage(&sign,TRUE,1,&message,&message_len,
                                 signed_bytes.data(),&needed);
    CertFreeCertificateContext(creator);
    required(second&&needed>=96&&needed<=65536,
             "Actual creator signoff was not cryptographically produced");
    HANDLE h=CreateFileW(receipt.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,
                         FILE_ATTRIBUTE_NORMAL,nullptr);
    required(h!=INVALID_HANDLE_VALUE,
             "Creator one-use signature already exists or cannot be written");
    DWORD written=0;
    BOOL ok=WriteFile(h,signed_bytes.data(),needed,&written,nullptr);
    BOOL synced=FlushFileBuffers(h);
    CloseHandle(h);
    required(ok&&synced&&written==needed,
             "User-owned creator signature cannot be durably sealed");
    required(nvp_p1f_creator_signature::verify(scope,receipt,issuer),
             "Created creator signature failed independent exact-source re-verification");
    std::cout<<"NVP_P1F_CREATOR_ONE_USE_NATIVE_SIGNOFF_PRODUCED_NOT_RENDERED\n";
    return 0;
}
int wmain(int argc,wchar_t** argv) {
    try {
        required(argc==1,
                "Trusted creator UI takes no model-provided command flags");
        return approve();
    } catch(const std::exception& ex) {
        std::cerr<<"NVP_P1F_CREATOR_SIGNOFF_DENIED: "<<ex.what()<<"\n";
        return 91;
    }
}
