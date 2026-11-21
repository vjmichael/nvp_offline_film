// NVP-INT-LU-01E-GPU-01-R2: exact Lu Core GPU stop evidence issuer.
// Include INSIDE the installed NVP SCM service after windows.h/bcrypt.h/ncrypt.h.
// Never call from UI, Python worker, or a non-SCM process. The installed NVP
// service MUST hold the original Job handle from suspended worker assignment
// until after TerminateJobObject + kernel ACTIVE_ZERO validation.
#pragma once
#ifndef _WIN32
#error This receipt may only be signed by the native Windows NVP SCM service
#endif
#include <windows.h>
#include <bcrypt.h>
#include <ncrypt.h>
#include <sddl.h>
#include <array>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>
#include <filesystem>

#pragma comment(lib,"ncrypt.lib")
#pragma comment(lib,"bcrypt.lib")
#pragma comment(lib,"advapi32.lib")

namespace nvp_int_lu_gpu_stop {
namespace fs=std::filesystem;
static constexpr char DOMAIN[]="LU_NVP_GPU_JOB_EMPTY_V1"; // use sizeof = trailing NUL
static constexpr char METHOD[]="WINDOWS_JOB_ACTIVE_ZERO_V1";
static constexpr wchar_t KEY_NAME[]=L"NVP-INT-LU-GPU-JOB-EMPTY-P256-v1";

struct Original {
    std::string lease_ref,device_ref,module_id,workspace_ref,conversation_ref;
    std::string user_turn_ref,task_ref,core_epoch_ref,nvp_session_ref;
    std::string original_nvp_job_ref; // local owner check; NOT in Lu canonical binary
};
inline void require(bool ok,const char* why){if(!ok)throw std::runtime_error(why);}
inline void bound(std::vector<BYTE>& out,const std::string& s){
    require(!s.empty() && s.size()<=128,"Unbounded original Lu GPU receipt field");
    for(const unsigned char c:s)
        require((c>='0'&&c<='9')||(c>='a'&&c<='z')||
                (c>='A'&&c<='Z')||c=='-'||c=='_'||c=='.'||
                c==':'||c=='/' ,"Noncanonical original Lu GPU scope");
    out.push_back(static_cast<BYTE>(s.size()));
    out.insert(out.end(),s.begin(),s.end());
}
inline void le32(std::vector<BYTE>& out,std::uint32_t n){
    for(int i=0;i<4;++i)out.push_back(static_cast<BYTE>((n>>(8*i))&0xff));
}
inline void le64(std::vector<BYTE>& out,std::uint64_t n){
    for(int i=0;i<8;++i)out.push_back(static_cast<BYTE>((n>>(8*i))&0xff));
}
inline std::uint64_t filetime(const FILETIME& t){
    return (static_cast<std::uint64_t>(t.dwHighDateTime)<<32)|t.dwLowDateTime;
}
inline std::uint64_t birth(HANDLE process){
    FILETIME created{},ended{},kernel{},user{};
    require(GetProcessTimes(process,&created,&ended,&kernel,&user)!=FALSE,
            "Native SCM original process birth unobservable");
    const auto b=filetime(created);
    require(b!=0,"Native SCM worker has zero birth generation");
    return b;
}
inline void require_scm_system(){
    HANDLE token=nullptr;
    require(OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token)!=FALSE,
            "Native NVP SCM service has no real token");
    struct Token{HANDLE handle;~Token(){if(handle)CloseHandle(handle);}} close{token};
    alignas(TOKEN_USER) std::array<BYTE,1024> buffer{};DWORD used=0;
    require(GetTokenInformation(token,TokenUser,buffer.data(),
             static_cast<DWORD>(buffer.size()),&used)!=FALSE,
            "NVP native signer cannot inspect OS service SID");
    auto* owner=reinterpret_cast<TOKEN_USER*>(buffer.data());
    require(IsWellKnownSid(owner->User.Sid,WinLocalSystemSid)!=FALSE,
            "NVP GPU stop signer was not an installed SYSTEM SCM service");
    DWORD session=~DWORD(0);
    require(GetTokenInformation(token,TokenSessionId,&session,sizeof(session),
             &used)!=FALSE && session==0,
            "NVP GPU stop signer not in Windows Session 0");
}
inline std::vector<BYTE> canonical(const Original& o,DWORD spid,
              std::uint64_t sbirth,DWORD wpid,std::uint64_t wbirth){
    require(o.module_id=="nvp.film","Foreign module cannot sign NVP GPU stop");
    require(spid>0 && sbirth>0 && wpid>0 && wbirth>0,
            "Original native SCM/worker process identity absent");
    require(o.lease_ref.size()<=128 && !o.lease_ref.empty(),
            "Invalid Core-issued original GPU lease");
    for(const unsigned char ch:o.lease_ref)
        require((ch>='0'&&ch<='9')||(ch>='a'&&ch<='z')||
                (ch>='A'&&ch<='Z')||ch=='-',
                "Lu installer rejects unsafe GPU receipt lease filename");
    std::vector<BYTE> out(reinterpret_cast<const BYTE*>(DOMAIN),
           reinterpret_cast<const BYTE*>(DOMAIN)+sizeof(DOMAIN));
    for(const std::string* item:{&o.lease_ref,&o.device_ref,&o.module_id,
           &o.workspace_ref,&o.conversation_ref,&o.user_turn_ref,&o.task_ref,
           &o.core_epoch_ref,&o.nvp_session_ref})bound(out,*item);
    bound(out,METHOD);
    le32(out,spid);le64(out,sbirth);le32(out,wpid);le64(out,wbirth);
    require(out.size()+64<=4096,"NVP GPU receipt exceeds Lu installed reader bound");
    return out;
}
inline std::vector<BYTE> sign_with_distinct_installed_key(const std::vector<BYTE>& body){
    BCRYPT_ALG_HANDLE sha=nullptr;
    require(BCryptOpenAlgorithmProvider(&sha,BCRYPT_SHA256_ALGORITHM,nullptr,0)>=0,
            "Windows SHA256 provider absent for original worker proof");
    std::array<BYTE,32> digest{};
    const auto rc=BCryptHash(sha,nullptr,0,const_cast<BYTE*>(body.data()),
                 static_cast<ULONG>(body.size()),digest.data(),
                 static_cast<ULONG>(digest.size()));
    BCryptCloseAlgorithmProvider(sha,0);
    require(rc>=0,"Original NVP GPU receipt digest failed");
    NCRYPT_PROV_HANDLE provider=0;NCRYPT_KEY_HANDLE key=0;
    require(NCryptOpenStorageProvider(&provider,MS_KEY_STORAGE_PROVIDER,0)==ERROR_SUCCESS,
            "NVP SCM CNG storage provider unavailable");
    try {
        require(NCryptOpenKey(provider,&key,KEY_NAME,0,NCRYPT_MACHINE_KEY_FLAG)==ERROR_SUCCESS,
                "Independent installer-owned NVP GPU key absent");
        wchar_t algorithm[128]{};DWORD returned=0;
        require(NCryptGetProperty(key,NCRYPT_ALGORITHM_PROPERTY,
                reinterpret_cast<PBYTE>(algorithm),sizeof(algorithm),&returned,0)==ERROR_SUCCESS &&
                wcscmp(algorithm,BCRYPT_ECDSA_P256_ALGORITHM)==0,
                "Original NVP GPU key is not ECDSA-P256");
        DWORD export_policy=0,policy_bytes=0;
        require(NCryptGetProperty(key,NCRYPT_EXPORT_POLICY_PROPERTY,
                reinterpret_cast<PBYTE>(&export_policy),sizeof(export_policy),
                &policy_bytes,0)==ERROR_SUCCESS &&
                policy_bytes==sizeof(export_policy) && export_policy==0,
                "NVP GPU private signing key must be non-exportable");
        DWORD n=0;
        require(NCryptSignHash(key,nullptr,digest.data(),
                static_cast<DWORD>(digest.size()),nullptr,0,&n,0)==ERROR_SUCCESS && n==64,
                "NVP GPU CNG signature width not Lu's 64 raw bytes");
        std::vector<BYTE> signature(64);
        require(NCryptSignHash(key,nullptr,digest.data(),
                static_cast<DWORD>(digest.size()),signature.data(),
                static_cast<DWORD>(signature.size()),&n,0)==ERROR_SUCCESS && n==64,
                "NVP GPU SCM P-256 signature failed");
        NCryptFreeObject(key);NCryptFreeObject(provider);
        return signature;
    }catch(...){if(key)NCryptFreeObject(key);NCryptFreeObject(provider);throw;}
}
inline void write_immutable_installed_receipt(const Original& original,
                  const std::vector<BYTE>& canonical_body){
    require_scm_system();
    const auto signature=sign_with_distinct_installed_key(canonical_body);
    std::vector<BYTE> bytes=canonical_body;
    bytes.insert(bytes.end(),signature.begin(),signature.end());
    wchar_t program_data[32768]{};
    const DWORD n=GetEnvironmentVariableW(L"ProgramData",program_data,32768);
    require(n>0 && n<32768,"Installed ProgramData path unavailable");
    const fs::path root=fs::path(program_data)/L"Lu"/L"IPC"/L"nvp-gpu-stops-v1";
    // NVP cannot create a Lu-owned receipt store or select a different path.
    require(fs::is_directory(root) && !fs::is_symlink(root),
            "Installer-owned Lu GPU stop receipt directory absent");
    const fs::path file=root/(std::wstring(original.lease_ref.begin(),
                            original.lease_ref.end())+L".stop.v1");
    // Lu's independent reader requires a PROTECTED explicit DACL on the
    // RECEIPT FILE, not just on the parent. Inherited defaults are rejected.
    PSECURITY_DESCRIPTOR sd=nullptr;
    require(ConvertStringSecurityDescriptorToSecurityDescriptorW(
           L"O:SYG:SYD:P(A;;FA;;;SY)(A;;FA;;;BA)",SDDL_REVISION_1,
           &sd,nullptr)!=FALSE && sd!=nullptr,
           "Installer-custodian NVP GPU receipt DACL unavailable");
    SECURITY_ATTRIBUTES sec{sizeof(SECURITY_ATTRIBUTES),sd,FALSE};
    const HANDLE output=CreateFileW(file.c_str(),GENERIC_WRITE,0,&sec,CREATE_NEW,
                                     FILE_FLAG_WRITE_THROUGH,nullptr);
    LocalFree(sd);
    require(output!=INVALID_HANDLE_VALUE,
            "Original NVP worker receipt already issued or inaccessible");
    struct File{HANDLE handle;~File(){if(handle!=INVALID_HANDLE_VALUE)CloseHandle(handle);}} guard{output};
    DWORD written=0;
    require(WriteFile(output,bytes.data(),static_cast<DWORD>(bytes.size()),
                      &written,nullptr)!=FALSE && written==bytes.size() &&
            FlushFileBuffers(output)!=FALSE,
            "Original native NVP GPU stop receipt not durably published");
}
/// Called ONLY with the actual SCM-held original Job handle, after protected
/// worker exit AND native cancellation/descendant termination. Never use a PID
/// or untrusted client outcome in place of the original handle.
inline void issue_after_original_job_empty(HANDLE original_job,
       HANDLE original_worker,const Original& original,
       const std::string& actual_original_job_ref){
    require(original_job!=nullptr && original_job!=INVALID_HANDLE_VALUE &&
            original_worker!=nullptr && original_worker!=INVALID_HANDLE_VALUE,
            "Original NVP SCM Job/worker native handles missing");
    require(!actual_original_job_ref.empty() &&
            original.original_nvp_job_ref==actual_original_job_ref,
            "NVP GPU lease refers to a foreign preallocated LTX job");
    DWORD code=STILL_ACTIVE;
    require(GetExitCodeProcess(original_worker,&code)!=FALSE && code!=STILL_ACTIVE,
            "NVP GPU worker not stopped");
    JOBOBJECT_BASIC_ACCOUNTING_INFORMATION account{};
    require(QueryInformationJobObject(original_job,JobObjectBasicAccountingInformation,
                 &account,sizeof(account),nullptr)!=FALSE &&
            account.ActiveProcesses==0,
            "Original NVP SCM Job not kernel ACTIVE_ZERO");
    require_scm_system();
    const auto packet=canonical(original,GetCurrentProcessId(),birth(GetCurrentProcess()),
                                GetProcessId(original_worker),birth(original_worker));
    write_immutable_installed_receipt(original,packet);
}
} // namespace nvp_int_lu_gpu_stop
