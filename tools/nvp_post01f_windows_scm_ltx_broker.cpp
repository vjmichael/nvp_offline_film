// POST-01F LTX2 SCM-owned one-shot native broker / CNG P-256 receipt.
// Windows-only, fixed installed paths and admin-scoped HKLM authorization.
// SOURCE CANDIDATE. Real MSVC/SCM/lowbox/WFP/EFS/GPU qualification OPEN.
// An absent signer key, one-use grant, model stack or real kernel proof is FATAL.
#define NVP_P1F_EMBEDDED_IN_SCM_SERVICE 1
#include "nvp_p1f_windows_private_kernel_probe.cpp"  // tested kernel helpers
#include "nvp_p1f_windows_private_desktop.hpp"
#include "nvp_post01f_windows_creator_signature.hpp"
#include "nvp_int_lu_gpu_stop_issuer.hpp" // native SCM Job ACTIVE_ZERO + separate CNG key
#include <bcrypt.h>
#include <ncrypt.h>
#include <shlobj.h> // fixed OS-known ProgramData/ProgramFiles, not SCM environment
#include <algorithm>
#include <atomic>
#include <array>
#include <iomanip>
#include <cstring>
#include <memory>
#include <regex>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
#pragma comment(lib,"bcrypt.lib")
#pragma comment(lib,"ncrypt.lib")
#pragma comment(lib,"shell32.lib")

namespace {
constexpr wchar_t SERVICE[]=L"NVP-POST01F-SCM-LTX-Picture";
constexpr wchar_t AUTH[]=L"SOFTWARE\\NVP\\POST01F\\ApprovedLtxPicture";
constexpr wchar_t KEY_NAME[]=L"NVP-POST01F-LTX-SCM-PICTURE-P256-v2";
constexpr char FORMAT[]="nvp.post01f.scm_cng_p256_picture_result.v2";
SERVICE_STATUS_HANDLE g_handle=nullptr;
SERVICE_STATUS g_status{};
std::atomic<bool> g_stop_requested{false}; // Owned SCM cancel; never an all-clear proof.

void must(bool condition,const char* description) {if(!condition)throw std::runtime_error(description);}
std::wstring known_folder(REFKNOWNFOLDERID id) {
    PWSTR raw=nullptr;
    const HRESULT hr=SHGetKnownFolderPath(id,KF_FLAG_DEFAULT,nullptr,&raw);
    must(SUCCEEDED(hr) && raw && *raw,
         "Original Windows machine known folder unavailable");
    const std::wstring result(raw);
    CoTaskMemFree(raw);
    return result;
}
std::wstring installed_root() {
    return known_folder(FOLDERID_ProgramFiles)+L"\\NVP\\LTX";
}
std::wstring protected_root() {
    return known_folder(FOLDERID_ProgramData)+L"\\NVP\\POST01F";
}
std::string to_ascii(const std::wstring& wide) {
    must(!wide.empty() && wide.size()<=512,"Unbounded native approval field");
    for(auto c:wide)must(c>=33 && c<=126,"Noncanonical SCM ticket field");
    return std::string(wide.begin(),wide.end());
}
bool exact(const std::string& s,const std::string& pattern) {
    return std::regex_match(s,std::regex(pattern));
}
std::string hex(const BYTE* bytes,size_t count) {
    static const char alphabet[]="0123456789abcdef";
    std::string out;out.reserve(count*2);
    for(size_t i=0;i<count;++i){out+=alphabet[bytes[i]>>4];out+=alphabet[bytes[i]&15];}
    return out;
}
std::array<BYTE,32> hash_bytes(const BYTE* value,size_t count) {
    BCRYPT_ALG_HANDLE provider=nullptr;
    must(BCryptOpenAlgorithmProvider(&provider,BCRYPT_SHA256_ALGORITHM,nullptr,0)>=0,
         "SCM BCrypt SHA256 unavailable");
    std::array<BYTE,32> digest{};
    const NTSTATUS rc=BCryptHash(provider,nullptr,0,
        const_cast<PUCHAR>(value),static_cast<ULONG>(count),
        digest.data(),static_cast<ULONG>(digest.size()));
    BCryptCloseAlgorithmProvider(provider,0);
    must(rc>=0,"SCM BCrypt SHA256 hash failed");
    return digest;
}
std::string file_sha(const fs::path& path) {
    HANDLE h=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,
                         OPEN_EXISTING,FILE_FLAG_SEQUENTIAL_SCAN,nullptr);
    must(h!=INVALID_HANDLE_VALUE,"SCM cannot open exact installed file");
    BCRYPT_ALG_HANDLE provider=nullptr;BCRYPT_HASH_HANDLE hash=nullptr;
    try {
        must(BCryptOpenAlgorithmProvider(&provider,BCRYPT_SHA256_ALGORITHM,nullptr,0)>=0,
             "SCM source hashing provider unavailable");
        must(BCryptCreateHash(provider,&hash,nullptr,0,nullptr,0,0)>=0,
             "SCM source hashing handle unavailable");
        std::array<BYTE,65536> data{};DWORD n=0;
        for(;;) {
            must(ReadFile(h,data.data(),static_cast<DWORD>(data.size()),&n,nullptr),
                 "SCM source I/O failed");
            if(n==0)break;
            must(BCryptHashData(hash,data.data(),n,0)>=0,"SCM source hashing failed");
        }
        std::array<BYTE,32> result{};
        must(BCryptFinishHash(hash,result.data(),static_cast<ULONG>(result.size()),0)>=0,
             "SCM source hash finalization failed");
        BCryptDestroyHash(hash);BCryptCloseAlgorithmProvider(provider,0);CloseHandle(h);
        return hex(result.data(),result.size());
    } catch(...) {
        if(hash)BCryptDestroyHash(hash);
        if(provider)BCryptCloseAlgorithmProvider(provider,0);
        CloseHandle(h);throw;
    }
}
fs::path regular(const fs::path& file) {
    DWORD attributes=GetFileAttributesW(file.c_str());
    must(attributes!=INVALID_FILE_ATTRIBUTES &&
         !(attributes&FILE_ATTRIBUTE_REPARSE_POINT) &&
         !(attributes&FILE_ATTRIBUTE_DIRECTORY),"Native source/output is missing or reparse");
    return file;
}
void allow_exact_derived_input_readonly(const fs::path& file,PSID sid) {
    regular(file);
    PACL previous=nullptr,derived=nullptr;
    PSECURITY_DESCRIPTOR sd=nullptr;
    DWORD rc=GetNamedSecurityInfoW(const_cast<LPWSTR>(file.c_str()),SE_FILE_OBJECT,
             DACL_SECURITY_INFORMATION,nullptr,nullptr,&previous,nullptr,&sd);
    must(rc==ERROR_SUCCESS && sd && previous,
         "SCM protected source input DACL missing");
    try {
        EXPLICIT_ACCESSW rule{};rule.grfAccessPermissions=FILE_GENERIC_READ;
        rule.grfAccessMode=GRANT_ACCESS;rule.grfInheritance=NO_INHERITANCE;
        rule.Trustee.TrusteeForm=TRUSTEE_IS_SID;
        rule.Trustee.TrusteeType=TRUSTEE_IS_USER;
        rule.Trustee.ptstrName=reinterpret_cast<LPWSTR>(sid);
        rc=SetEntriesInAclW(1,&rule,previous,&derived);
        must(rc==ERROR_SUCCESS && derived,"SCM cannot create exact input read ACE");
        rc=SetNamedSecurityInfoW(const_cast<LPWSTR>(file.c_str()),SE_FILE_OBJECT,
              DACL_SECURITY_INFORMATION|PROTECTED_DACL_SECURITY_INFORMATION,
              nullptr,nullptr,derived,nullptr);
        must(rc==ERROR_SUCCESS,"SCM cannot restrict exact input to lowbox SID");
        TRUSTEE_W trustee{};trustee.TrusteeForm=TRUSTEE_IS_SID;
        trustee.TrusteeType=TRUSTEE_IS_USER;
        trustee.ptstrName=reinterpret_cast<LPWSTR>(sid);
        ACCESS_MASK rights=0;
        must(GetEffectiveRightsFromAclW(derived,&trustee,&rights)==ERROR_SUCCESS &&
             (rights&FILE_GENERIC_READ)==FILE_GENERIC_READ &&
             (rights&(FILE_WRITE_DATA|FILE_APPEND_DATA|DELETE|WRITE_DAC|WRITE_OWNER))==0,
             "AppContainer acquired write/erase of approved original-derived guide");
    } catch(...) {
        if(derived)LocalFree(derived);LocalFree(sd);throw;
    }
    LocalFree(derived);LocalFree(sd);
}
void encrypted(const fs::path& path) {
    DWORD state=0;
    must(FileEncryptionStatusW(path.c_str(),&state)&&state==FILE_IS_ENCRYPTED,
         "SCM file lacks actual Windows EFS protection");
}
void durable_new(const fs::path& path,const std::string& value) {
    HANDLE file=CreateFileW(path.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,
                            FILE_ATTRIBUTE_NORMAL,nullptr);
    must(file!=INVALID_HANDLE_VALUE,"SCM refuses duplicate/unauthorized result");
    DWORD written=0;
    const BOOL ok=WriteFile(file,value.data(),static_cast<DWORD>(value.size()),
                            &written,nullptr);
    const BOOL fsynced=FlushFileBuffers(file);
    CloseHandle(file);
    must(ok && written==value.size() && fsynced,
         "Native SCM receipt/authorization not durable");
}
std::wstring reg_string(HKEY key,const wchar_t* name) {
    DWORD type=0,size=0;
    must(RegQueryValueExW(key,name,nullptr,&type,nullptr,&size)==ERROR_SUCCESS&&
         type==REG_SZ && size>=sizeof(wchar_t) && size<=2048,
         "Native one-use HKLM approval field absent");
    must(size%sizeof(wchar_t)==0,"Invalid UTF-16 SCM registry record");
    std::vector<wchar_t> out(size/sizeof(wchar_t));
    must(RegQueryValueExW(key,name,nullptr,&type,
         reinterpret_cast<BYTE*>(out.data()),&size)==ERROR_SUCCESS &&
         out.back()==L'\0' &&
         std::find(out.begin(),out.end()-1,L'\0')==out.end()-1,
         "SCM approval registry value changed/contains an injected NUL");
    return std::wstring(out.data());
}
struct Approval {
    std::string ticket,job,project,plan,stack,bootstrap,layout,look,conditioning,nonce,expires;
    // Optional Lu-connected resource job, sealed by the original machine
    // custodian, NEVER supplied as model/UI arguments or a worker reply.
    std::string gpu_ref,gpu_device,gpu_job,gpu_workspace,gpu_conversation,
                gpu_turn,gpu_task,gpu_epoch,gpu_session;
};
Approval consume() {
    HKEY registry=nullptr;
    must(RegOpenKeyExW(HKEY_LOCAL_MACHINE,AUTH,0,KEY_QUERY_VALUE|KEY_SET_VALUE,
                      &registry)==ERROR_SUCCESS,"Installed admin-only SCM approval absent");
    try {
        auto read=[&](const wchar_t* name){return to_ascii(reg_string(registry,name));};
        Approval a{read(L"PendingId"),read(L"JobId"),read(L"ProjectId"),
          read(L"PlanSha256"),read(L"ModelStackSha256"),read(L"BootstrapSha256"),
          read(L"LayoutSha256"),read(L"LookSha256"),read(L"ConditioningSha256"),
          read(L"ReceiptNonce"),read(L"CreatorExpiresUtc")};
        must(exact(a.ticket,"[a-f0-9]{32}") && exact(a.job,"ltx_[a-f0-9]{24}") &&
             exact(a.project,"[a-f0-9]{32}") && exact(a.nonce,"[a-f0-9]{32}"),
             "SCM ticket, project or job identity malformed");
        for(const auto* digest:{&a.plan,&a.stack,&a.bootstrap,&a.layout,
                                 &a.look,&a.conditioning})
            must(exact(*digest,"[a-f0-9]{64}"),"SCM source/model pin invalid");
        DWORD gpu_type=0,gpu_len=0;
        const LONG gpu_presence=RegQueryValueExW(registry,L"GpuLeaseRef",nullptr,
                         &gpu_type,nullptr,&gpu_len);
        must(gpu_presence==ERROR_FILE_NOT_FOUND||gpu_presence==ERROR_SUCCESS,
             "Protected Lu GPU lease registry state invalid");
        if(gpu_presence==ERROR_SUCCESS) {
            // A partially populated GPU binding cannot be silently treated
            // as an ordinary non-Lu job and bypass the signed stop receipt.
            a.gpu_ref=read(L"GpuLeaseRef");
            a.gpu_device=read(L"GpuDeviceRef");
            a.gpu_job=read(L"GpuOriginalJobRef");
            a.gpu_workspace=read(L"GpuWorkspaceRef");
            a.gpu_conversation=read(L"GpuConversationRef");
            a.gpu_turn=read(L"GpuUserTurnRef");
            a.gpu_task=read(L"GpuTaskRef");
            a.gpu_epoch=read(L"GpuCoreEpochRef");
            a.gpu_session=read(L"GpuNvpSessionRef");
            must(a.gpu_job==a.job &&
                 exact(a.gpu_device,"dxgi:luid_0x[0-9a-fA-F]{8}_0x[0-9a-fA-F]{8}_phys_0") &&
                 exact(a.gpu_ref,"gpu-[A-Za-z0-9-]{1,124}"),
                 "Lu GPU lease not tied to original admitted native LTX job/device");
        }
        std::string previous;
        try {previous=read(L"ConsumedId");}catch(const std::exception&){}
        must(previous!=a.ticket,"SCM one-use ticket replay");
        const std::wstring ticket(a.ticket.begin(),a.ticket.end());
        // The single most-recent ConsumedId registry value is NOT a durable
        // all-history anti-replay register. Keep one immutable spent file per
        // ticket so even an older ticket cannot be resurrected after another.
        const fs::path history=fs::path(protected_root())/L"SpentTickets";
        must(fs::is_directory(history)&&!fs::is_symlink(history),
             "Native SCM one-use spent-ticket directory absent");
        encrypted(history);
        const fs::path spent=history/(ticket+L".spent");
        durable_new(spent,"format=nvp.post01f.scm_spent.v1\nticket="+a.ticket+"\n");
        encrypted(spent);
        must(RegSetValueExW(registry,L"ConsumedId",0,REG_SZ,
                 reinterpret_cast<const BYTE*>(ticket.c_str()),
                 static_cast<DWORD>((ticket.size()+1)*sizeof(wchar_t)))==ERROR_SUCCESS,
             "Native SCM approval could not be spent");
        must(RegDeleteValueW(registry,L"PendingId")==ERROR_SUCCESS &&
             RegFlushKey(registry)==ERROR_SUCCESS,
             "Native SCM one-use ticket not durably consumed");
        RegCloseKey(registry);return a;
    } catch(...) {RegCloseKey(registry);throw;}
}
std::string sign_cng_machine(const std::string& signed_json) {
    // The installed machine key MUST preexist and be ACLed to this fixed SCM
    // service identity. Never create/import it here; never accept a key path.
    NCRYPT_PROV_HANDLE provider=0;NCRYPT_KEY_HANDLE key=0;
    must(NCryptOpenStorageProvider(&provider,MS_KEY_STORAGE_PROVIDER,0)==ERROR_SUCCESS,
         "Windows machine KSP unavailable");
    try {
        must(NCryptOpenKey(provider,&key,KEY_NAME,0,NCRYPT_MACHINE_KEY_FLAG)==ERROR_SUCCESS,
             "Installer-owned non-exportable SCM machine signer key absent");
        wchar_t algorithm[128]{};DWORD returned=0;
        must(NCryptGetProperty(key,NCRYPT_ALGORITHM_PROPERTY,
               reinterpret_cast<PBYTE>(algorithm),sizeof(algorithm),&returned,0)==ERROR_SUCCESS &&
             wcscmp(algorithm,BCRYPT_ECDSA_P256_ALGORITHM)==0,
             "SCM machine signer must be ECDSA P-256");
        auto digest=hash_bytes(reinterpret_cast<const BYTE*>(signed_json.data()),
                               signed_json.size());
        DWORD bytes=0;
        must(NCryptSignHash(key,nullptr,digest.data(),static_cast<DWORD>(digest.size()),
                nullptr,0,&bytes,0)==ERROR_SUCCESS && bytes==64,
             "Windows CNG P-256 signature length invalid");
        std::array<BYTE,64> signature{};
        must(NCryptSignHash(key,nullptr,digest.data(),static_cast<DWORD>(digest.size()),
                signature.data(),static_cast<DWORD>(signature.size()),&bytes,0)==ERROR_SUCCESS &&
                bytes==signature.size(),"Native SCM machine signing operation failed");
        NCryptFreeObject(key);NCryptFreeObject(provider);
        return hex(signature.data(),signature.size());
    } catch(...) {
        if(key)NCryptFreeObject(key);
        NCryptFreeObject(provider);throw;
    }
}
std::string body(const Approval& a,DWORD pid,const std::string& sid,
                 const std::string& picture) {
    // Canonical ASCII JSON key order is exactly Python's sort_keys=True.
    return std::string("{\"appcontainer_sid_sha256\":\"")+sid+
      "\",\"appcontainer_zero_network_caps_verified\":true,"
      "\"bootstrap_sha256\":\""+a.bootstrap+"\",\"efs_verified\":true,"
      "\"job_id\":\""+a.job+"\",\"model_stack_sha256\":\""+a.stack+
      "\",\"picture_sha256\":\""+picture+"\",\"plan_sha256\":\""+a.plan+
      "\",\"project_id\":\""+a.project+"\",\"receipt_nonce\":\""+a.nonce+
      "\",\"scm_service_custody_verified\":true,\"wfp_no_egress_verified\":true,"
      "\"worker_pid\":"+std::to_string(pid)+"}";
}
bool zero_active_processes(HANDLE job) {
    JOBOBJECT_BASIC_ACCOUNTING_INFORMATION accounting{};
    return QueryInformationJobObject(job,JobObjectBasicAccountingInformation,
        &accounting,sizeof(accounting),nullptr) && accounting.ActiveProcesses==0;
}
int run_once() {
    const Approval a=consume(); // consume ticket BEFORE any model/worker spawn
    const fs::path stage=fs::path(protected_root())/L"ApprovedJobs"/
                         fs::path(std::wstring(a.job.begin(),a.job.end()));
    const fs::path exe=fs::path(installed_root())/L"nvp_ltx_broker.exe";
    const fs::path lock=fs::path(installed_root())/L"nvp_ltx_runtime.lock.json";
    must(fs::is_directory(stage) && !fs::is_symlink(stage),
         "Missing exact preauthorized EFS SCM job directory");
    encrypted(stage);
    regular(exe);regular(lock);
    must(file_sha(exe)==a.bootstrap && file_sha(lock)==a.stack,
         "Installed LTX bootstrap or manifest digest drifted");
    for(const auto& e:std::vector<std::pair<std::wstring,std::string>>{
          {L"plan.json",a.plan},{L"layout.mp4",a.layout},
          {L"look.png",a.look},{L"conditioning.json",a.conditioning}}) {
        const fs::path p=regular(stage/e.first);encrypted(p);
        must(file_sha(p)==e.second,"Original derived LTX conditioning changed");
    }
    for(const auto& name:{L"journal.json",L"stdout.log",L"stderr.log"}) {
        regular(stage/name);encrypted(stage/name);
    }
    const fs::path approval_file=fs::path(protected_root())/L"CreatorApprovals"/
                   fs::path(std::wstring(a.job.begin(),a.job.end())+L".p7s");
    regular(approval_file);encrypted(approval_file);
    // Actual one-use creator approval is cryptographically verified in SCM,
    // not accepted as a model response, a desktop boolean or an HKLM flag.
    HKEY creator_trust=nullptr;
    must(RegOpenKeyExW(HKEY_LOCAL_MACHINE,L"SOFTWARE\\NVP\\POST01F\\CreatorTrust",
           0,KEY_QUERY_VALUE,&creator_trust)==ERROR_SUCCESS,
         "Independent installer creator trust anchor unavailable");
    std::string creator_cert;
    try {creator_cert=to_ascii(reg_string(creator_trust,L"SignerCertificateSha256"));}
    catch(...) {RegCloseKey(creator_trust);throw;}
    RegCloseKey(creator_trust);
    const nvp_post01f_creator::Scope approved={a.ticket,a.project,a.job,a.plan,
           a.stack,a.bootstrap,a.layout,a.look,a.conditioning,a.nonce,a.expires};
    must(nvp_post01f_creator::verify(approved,approval_file,creator_cert),
         "No independent native creator signoff for exact LTX source/plan");
    const std::set<std::wstring> expected={L"journal.json",L"stdout.log",
        L"stderr.log",L"plan.json",L"layout.mp4",L"look.png",L"conditioning.json"};
    for(const auto& entry:fs::directory_iterator(stage))
        must(expected.count(entry.path().filename().wstring())==1 &&
             !entry.is_symlink(),"Unreviewed source sidecar before SCM child launch");
    Handles h;
    h.profile=L"NVP.POST01F.LTX."+std::wstring(a.ticket.begin(),a.ticket.end());
    must(SUCCEEDED(CreateAppContainerProfile(h.profile.c_str(),L"NVP finite LTX preview",
        L"One source-bound model job",nullptr,0,&h.sid))&&h.sid,
        "Installed SCM could not create exact AppContainer SID");
    h.profile_created=true;
    allow_one_job_root(stage.wstring(),h.sid,h);
    for(const auto& frozen:{L"plan.json",L"layout.mp4",L"look.png",L"conditioning.json"})
        allow_exact_derived_input_readonly(stage/frozen,h.sid);
    FWPM_SESSION0 session{};session.flags=FWPM_SESSION_FLAG_DYNAMIC;
    must(FwpmEngineOpen0(nullptr,RPC_C_AUTHN_WINNT,nullptr,&session,
                         &h.wfp)==ERROR_SUCCESS && h.wfp,
         "SCM has no WFP dynamic service authority");
    add_wfp_block(h.wfp,h.sid,FWPM_LAYER_ALE_AUTH_CONNECT_V4);
    add_wfp_block(h.wfp,h.sid,FWPM_LAYER_ALE_AUTH_CONNECT_V6);
    add_wfp_block(h.wfp,h.sid,FWPM_LAYER_ALE_AUTH_RECV_ACCEPT_V4);
    add_wfp_block(h.wfp,h.sid,FWPM_LAYER_ALE_AUTH_RECV_ACCEPT_V6);
    h.job=CreateJobObjectW(nullptr,nullptr);
    must(h.job!=nullptr,"SCM Windows Job not created");
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
    limits.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE|
                                            JOB_OBJECT_LIMIT_JOB_MEMORY;
    limits.JobMemoryLimit=24ULL*1024ULL*1024ULL*1024ULL;
    must(SetInformationJobObject(h.job,JobObjectExtendedLimitInformation,
        &limits,sizeof(limits)),"SCM Job resource fence unavailable");
    SECURITY_CAPABILITIES caps{};caps.AppContainerSid=h.sid;
    SIZE_T attr_bytes=0;
    InitializeProcThreadAttributeList(nullptr,1,0,&attr_bytes);
    must(attr_bytes>0,"No Windows AppContainer startup list");
    std::vector<BYTE> backing(attr_bytes);
    auto* attrs=reinterpret_cast<PPROC_THREAD_ATTRIBUTE_LIST>(backing.data());
    must(InitializeProcThreadAttributeList(attrs,1,0,&attr_bytes),
         "SCM AppContainer process attributes unavailable");
    must(UpdateProcThreadAttribute(attrs,0,PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
        &caps,sizeof(caps),nullptr,nullptr),"SCM lowbox SID cannot be attached");
    nvp_p1f_private_desktop::PrivateDesktop private_desktop(
          std::wstring(a.ticket.begin(),a.ticket.end()));
    STARTUPINFOEXW start{};start.StartupInfo.cb=sizeof(start);
    start.lpAttributeList=attrs;
    start.StartupInfo.lpDesktop=const_cast<LPWSTR>(private_desktop.qualified.c_str());
    // Exact installed executable, exact plan. No user-provided executable,
    // prompt, shell, extra args or arbitrary Python module.
    must(!g_stop_requested.load(std::memory_order_acquire),
         "SCM creator cancelled original GPU job before worker launch");
    const std::wstring cmd=quoted(exe.wstring())+L" --nvp-ltx-job "+
                 quoted((stage/L"plan.json").wstring());
    std::vector<wchar_t> args(cmd.begin(),cmd.end());args.push_back(0);
    PROCESS_INFORMATION pi{};
    BOOL started=CreateProcessW(exe.c_str(),args.data(),nullptr,nullptr,FALSE,
             EXTENDED_STARTUPINFO_PRESENT|CREATE_SUSPENDED|CREATE_NO_WINDOW,
             nullptr,stage.c_str(),&start.StartupInfo,&pi);
    DeleteProcThreadAttributeList(attrs);
    must(started!=FALSE,"Native SCM protected LTX child not created");
    h.process=pi.hProcess;h.thread=pi.hThread;
    must(AssignProcessToJobObject(h.job,h.process),"SCM did not own LTX child Job");
    BOOL in_job=FALSE;
    must(IsProcessInJob(h.process,h.job,&in_job)&&in_job&&
         assigned_token_appcontainer(h.process,h.sid),
         "Native LTX child Job/SID custody failed before resume");
    const DWORD pid=GetProcessId(h.process);
    must(pid>0,"SCM has no actual child PID");
    const std::string sid_hash=hex(hash_bytes(
       reinterpret_cast<const BYTE*>(h.sid),GetLengthSid(h.sid)).data(),32);
    must(ResumeThread(h.thread)!=DWORD(-1),"SCM cannot resume owned LTX child");
    // A user-authorized stop is observed only by the SCM custodian. STOP
    // does NOT imply Job empty, GPU quiescent or permission for Lu to reload.
    // Poll under the one-hour installed timeout so cancellation can terminate
    // exactly this original SCM Job and still issue a genuine empty-Job proof.
    DWORD waited=WAIT_TIMEOUT;
    for(int i=0;i<18000 && !g_stop_requested.load(std::memory_order_acquire);++i) {
        waited=WaitForSingleObject(h.process,200);
        if(waited==WAIT_OBJECT_0 || waited==WAIT_FAILED)break;
    }
    DWORD exit_code=1;
    const bool worker_succeeded=!g_stop_requested.load(std::memory_order_acquire) &&
        waited==WAIT_OBJECT_0 &&
        GetExitCodeProcess(h.process,&exit_code)!=FALSE && exit_code==0;
    // Kill ALL helper descendants and wait for empty Job before publication;
    // WFP and AppContainer protections remain in force. Even failure/timeout
    // must drain the SAME original Job before releasing Lu's GPU lease.
    must(TerminateJobObject(h.job,worker_succeeded?0:13),
         "SCM cannot terminate original protected LTX Job descendants");
    bool drained=false;
    for(int i=0;i<100;++i) {
        if(zero_active_processes(h.job)){drained=true;break;}
        Sleep(100);
    }
    must(drained,"SCM Job still has child processes after 10s drain");
    // Release the GPU independently of the film result, only AFTER original
    // Job is kernel-empty. A failed film never receives a positive picture.
    if(!a.gpu_ref.empty()) {
        const nvp_int_lu_gpu_stop::Original original{
            a.gpu_ref,a.gpu_device,"nvp.film",a.gpu_workspace,a.gpu_conversation,
            a.gpu_turn,a.gpu_task,a.gpu_epoch,a.gpu_session,a.gpu_job};
        // This is executed by the original running installed SCM service
        // while it still HOLDS its original Job and worker process handles.
        // Missing pin/key/immutable file/ACTIVE_ZERO fails before any film
        // success is reported. Lu independently verifies receipt + VRAM.
        nvp_int_lu_gpu_stop::issue_after_original_job_empty(
            h.job,h.process,original,a.job);
    }
    must(worker_succeeded,"Native LTX broker failed, timed out or was cancelled");
    const fs::path picture=regular(stage/L"picture.mp4");
    const fs::path result=regular(stage/L"result.json");
    encrypted(picture);encrypted(result);
    // Recheck creator consent source after the AppContainer job has fully exited.
    must(nvp_post01f_creator::verify(approved,approval_file,creator_cert),
         "Native creator approval expired/mutated before SCM picture sign");
    for(const auto& entry:fs::directory_iterator(stage)) {
        const std::wstring n=entry.path().filename().wstring();
        must((expected.count(n)==1||n==L"picture.mp4"||n==L"result.json")&&
              !entry.is_symlink(),"SCM model generated unapproved media/sidecar");
    }
    for(const auto& e:std::vector<std::pair<std::wstring,std::string>>{
          {L"plan.json",a.plan},{L"layout.mp4",a.layout},
          {L"look.png",a.look},{L"conditioning.json",a.conditioning}})
        must(file_sha(stage/e.first)==e.second,"Native child altered approved source");
    must(file_sha(exe)==a.bootstrap && file_sha(lock)==a.stack,
         "Installed code or model lock changed during actual child execution");
    const std::string pic=file_sha(picture);
    const std::string signed_body=std::string("{\"body\":")+
              body(a,pid,sid_hash,pic)+",\"format\":\""+FORMAT+"\"}";
    const std::string signature=sign_cng_machine(signed_body);
    const std::string envelope=signed_body.substr(0,signed_body.size()-1)+
                    ",\"signature\":\""+signature+"\"}";
    const fs::path receipts=fs::path(protected_root())/L"SCMReceipts";
    must(fs::is_directory(receipts) && !fs::is_symlink(receipts),
         "No installer-protected SCM result directory");
    encrypted(receipts);
    const fs::path receipt=receipts/(std::wstring(a.job.begin(),a.job.end())+L".v2.json");
    durable_new(receipt,envelope);
    encrypted(receipt);
    return 0;
}
void report(DWORD status,DWORD error=0){
    if(!g_handle)return;
    g_status.dwServiceType=SERVICE_WIN32_OWN_PROCESS;
    g_status.dwCurrentState=status;
    g_status.dwControlsAccepted=(status==SERVICE_RUNNING)?SERVICE_ACCEPT_STOP:0;
    g_status.dwWin32ExitCode=error;
    g_status.dwWaitHint=(status==SERVICE_START_PENDING)?3600000:
        ((status==SERVICE_STOP_PENDING)?30000:0);
    SetServiceStatus(g_handle,&g_status);
}
void WINAPI control(DWORD command) {
    // SCM ACLs, not model/UI-supplied flags, authorize this operation.
    // The service worker thread performs the actual terminate/reap/sign.
    if(command==SERVICE_CONTROL_STOP) {
        g_stop_requested.store(true,std::memory_order_release);
        report(SERVICE_STOP_PENDING);
    }
}
void WINAPI service_main(DWORD,LPWSTR*) {
    g_handle=RegisterServiceCtrlHandlerW(SERVICE,control);
    if(!g_handle)return;
    g_stop_requested.store(false,std::memory_order_release);
    report(SERVICE_START_PENDING);
    // Tell SCM this is a legitimately running long-lived (bounded) job;
    // leaving START_PENDING for a 60-minute model inference is invalid.
    report(SERVICE_RUNNING);
    DWORD code=0;
    try {code=static_cast<DWORD>(run_once());}
    catch(const std::exception& ex) {
        const fs::path error=fs::path(protected_root())/L"scm_ltx_last_error.txt";
        try {durable_new(error,std::string("NVP_SCM_LTX_DENIED: ")+ex.what()+"\n");}
        catch(const std::exception&) {}
        code=97;
    }
    report(SERVICE_STOPPED,code);
}
} // namespace
int wmain(int argc,wchar_t** argv) {
    // An ordinary desktop execution never runs the broker. Only SCM can call
    // ServiceMain through StartServiceCtrlDispatcherW for this fixed service.
    if(argc!=2 || std::wstring(argv[1])!=L"--service")return 96;
    SERVICE_TABLE_ENTRYW entries[]={{const_cast<LPWSTR>(SERVICE),service_main},{nullptr,nullptr}};
    if(!StartServiceCtrlDispatcherW(entries))return 96;
    return 0;
}
