// POST-01F LTX one-use exact creator CMS; not an SCM or model tool.
// Requires an installed user-owned certificate, administrator-pinned job and
// explicit native Yes/No consent. No unattended/flag-driven approval.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wincrypt.h>
#include <shlobj.h>
#include <knownfolders.h>
#include <combaseapi.h>
#include <filesystem>
#include <string>
#include <vector>
#include <regex>
#include <stdexcept>
#include <iostream>
#include <ctime>
#include <algorithm>
#include "nvp_post01f_windows_creator_signature.hpp"
#pragma comment(lib,"crypt32.lib")
#pragma comment(lib,"advapi32.lib")
#pragma comment(lib,"user32.lib")
namespace fs=std::filesystem;
namespace {
constexpr wchar_t APPROVED[]=L"SOFTWARE\\NVP\\POST01F\\ApprovedLtxPicture";
constexpr wchar_t TRUST[]=L"SOFTWARE\\NVP\\POST01F\\CreatorTrust";
void required(bool ok,const char* message) {
    if(!ok)throw std::runtime_error(message);
}
std::wstring machine_string(const wchar_t* key,const wchar_t* name) {
    HKEY h=nullptr;
    required(RegOpenKeyExW(HKEY_LOCAL_MACHINE,key,0,KEY_READ|KEY_WOW64_64KEY,&h)==ERROR_SUCCESS,
             "No installed independent creator grant/trust");
    try {
        DWORD type=0,n=0;
        required(RegQueryValueExW(h,name,nullptr,&type,nullptr,&n)==ERROR_SUCCESS &&
                 type==REG_SZ && n>=sizeof(wchar_t) && n<=2048 &&
                 n%sizeof(wchar_t)==0,"Missing exact native approval field");
        std::vector<wchar_t> chars(n/sizeof(wchar_t));
        required(RegQueryValueExW(h,name,nullptr,&type,
                 reinterpret_cast<BYTE*>(chars.data()),&n)==ERROR_SUCCESS &&
                 chars.back()==0 && std::find(chars.begin(),chars.end()-1,0)==chars.end()-1,
                 "Invalid native approval string");
        RegCloseKey(h);return std::wstring(chars.data());
    }catch(...){RegCloseKey(h);throw;}
}
std::string ascii(const std::wstring& w) {
    required(!w.empty()&&w.size()<=512,"Unbounded creator scope");
    for(wchar_t c:w)required(c>=33&&c<=126,"Noncanonical creator scope");
    return std::string(w.begin(),w.end());
}
void exact(const std::string& s,const char* pattern){
    required(std::regex_match(s,std::regex(pattern)),"Invalid signed scope identity");
}
void efs(const fs::path& p){
    DWORD flags=0;
    required(FileEncryptionStatusW(p.c_str(),&flags)&&flags==FILE_IS_ENCRYPTED,
             "Native creator approval must remain EFS-encrypted");
}
PCCERT_CONTEXT enrolled_cert(const std::string& pinned) {
    HCERTSTORE store=CertOpenStore(CERT_STORE_PROV_SYSTEM_W,0,0,
                                   CERT_SYSTEM_STORE_CURRENT_USER,L"MY");
    required(store!=nullptr,"Independent creator cert store unavailable");
    PCCERT_CONTEXT found=nullptr;
    PCCERT_CONTEXT cursor=nullptr;
    while((cursor=CertEnumCertificatesInStore(store,cursor))!=nullptr){
        try{
            if(nvp_post01f_creator::cert_hash(cursor)==pinned &&
               CertVerifyTimeValidity(nullptr,cursor->pCertInfo)==0){
                DWORD len=0;
                if(CertGetCertificateContextProperty(cursor,CERT_KEY_PROV_INFO_PROP_ID,
                                                     nullptr,&len)&&len){
                    found=CertDuplicateCertificateContext(cursor);break;
                }
            }
        }catch(const std::exception&){}
    }
    CertCloseStore(store,0);
    required(found!=nullptr,"Owner-enrolled creator signing certificate absent");
    return found;
}
int sign_one(){
    auto field=[](const wchar_t* name){return ascii(machine_string(APPROVED,name));};
    nvp_post01f_creator::Scope s{
        field(L"PendingId"),field(L"ProjectId"),field(L"JobId"),
        field(L"PlanSha256"),field(L"ModelStackSha256"),field(L"BootstrapSha256"),
        field(L"LayoutSha256"),field(L"LookSha256"),field(L"ConditioningSha256"),
        field(L"ReceiptNonce"),field(L"CreatorExpiresUtc")
    };
    exact(s.ticket,"[a-f0-9]{32}");
    exact(s.project,"[a-f0-9]{32}");
    exact(s.job,"ltx_[a-f0-9]{24}");
    exact(s.nonce,"[a-f0-9]{32}");
    for(const auto* d:{&s.plan,&s.model_stack,&s.bootstrap,&s.layout,
                       &s.look,&s.conditioning})exact(*d,"[a-f0-9]{64}");
    exact(s.expires,"[0-9]{10,12}");
    auto expiry=std::stoll(s.expires);
    auto now=static_cast<long long>(std::time(nullptr));
    required(expiry>=now && expiry<=now+900,
             "Native creator consent expired or exceeds 15-minute scope");
    const std::string pin=ascii(machine_string(TRUST,L"SignerCertificateSha256"));
    exact(pin,"[a-f0-9]{64}");
    PWSTR trusted_program_data=nullptr;
    HRESULT known=SHGetKnownFolderPath(FOLDERID_ProgramData,KF_FLAG_DEFAULT,
                                        nullptr,&trusted_program_data);
    required(SUCCEEDED(known)&&trusted_program_data,
             "Installed Windows system-known ProgramData unavailable");
    const fs::path machine_data(trusted_program_data);
    CoTaskMemFree(trusted_program_data);
    const fs::path root=machine_data/L"NVP"/L"POST01F"/L"CreatorApprovals";
    required(!fs::is_symlink(root)&&fs::is_directory(root),
             "No fixed installed native creator approval directory");
    efs(root);
    const fs::path output=root/(std::wstring(s.job.begin(),s.job.end())+L".p7s");
    required(!fs::exists(output)&&!fs::is_symlink(output),
             "Duplicate creator approval refused");
    const std::wstring prompt=
        L"Authorize ONE LTX generated-picture job?\n\nProject: "+
        std::wstring(s.project.begin(),s.project.end())+
        L"\nJob: "+std::wstring(s.job.begin(),s.job.end())+
        L"\nPlan SHA-256: "+std::wstring(s.plan.begin(),s.plan.end())+
        L"\nModel-stack SHA-256: "+std::wstring(s.model_stack.begin(),s.model_stack.end())+
        L"\n\nOriginal Takes and sound remain unchanged."
        L"\nGenerated picture still requires your separate review.\nDeny by default.";
    const int response=MessageBoxW(nullptr,prompt.c_str(),
        L"NVP — one-time LTX picture creator approval",
        MB_YESNO|MB_ICONWARNING|MB_DEFBUTTON2|MB_TOPMOST|MB_SETFOREGROUND);
    required(response==IDYES,"Creator refused or closed native consent");
    PCCERT_CONTEXT cert=enrolled_cert(pin);
    const std::string body=nvp_post01f_creator::message(s);
    const BYTE* bytes=reinterpret_cast<const BYTE*>(body.data());
    DWORD size=static_cast<DWORD>(body.size());
    CRYPT_SIGN_MESSAGE_PARA para{};
    para.cbSize=sizeof(para);
    para.dwMsgEncodingType=X509_ASN_ENCODING|PKCS_7_ASN_ENCODING;
    para.pSigningCert=cert;
    para.HashAlgorithm.pszObjId=const_cast<char*>(szOID_NIST_sha256);
    para.cMsgCert=1;para.rgpMsgCert=&cert;
    DWORD needed=0;
    BOOL measured=CryptSignMessage(&para,TRUE,1,&bytes,&size,nullptr,&needed);
    required(measured&&needed>=96&&needed<=65536,
             "Actual Windows detached creator CMS signature unavailable");
    std::vector<BYTE> signature(needed);
    BOOL signed_ok=CryptSignMessage(&para,TRUE,1,&bytes,&size,
                                    signature.data(),&needed);
    CertFreeCertificateContext(cert);
    required(signed_ok&&needed>=96&&needed<=65536,
             "Windows creator CMS signature creation failed");
    HANDLE h=CreateFileW(output.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,
                          FILE_ATTRIBUTE_NORMAL,nullptr);
    required(h!=INVALID_HANDLE_VALUE,"Native signature already exists or is denied");
    DWORD written=0;
    BOOL wrote=WriteFile(h,signature.data(),needed,&written,nullptr);
    BOOL synced=FlushFileBuffers(h);
    CloseHandle(h);
    required(wrote&&synced&&written==needed,"Creator signature was not durable");
    efs(output);
    required(nvp_post01f_creator::verify(s,output,pin),
             "Creator CMS failed the same exact independent SCM verifier");
    std::cout<<"NVP_POST01F_CREATOR_ONE_USE_SIGNED_NOT_FILM_APPROVED\n";
    return 0;
}
}
int wmain(int argc,wchar_t**){
    try{
        required(argc==1,"No unattended creator-authorization arguments");
        return sign_one();
    }catch(const std::exception& ex){
        std::cerr<<"NVP_POST01F_CREATOR_SIGNOFF_DENIED: "<<ex.what()<<"\n";
        return 91;
    }
}
