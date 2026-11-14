// P1-F FINITE SCM-OWNED BLENDER SOURCE-BOUND BROKER, PUBLIC NATIVE GATE.
//
// This is a first-party fixed Blender/PNG/actor PCM fixture runner under
// actual SCM LocalSystem + AppContainer package SID + WFP + Job Object.
// It deliberately requires a separate HKLM admin one-use ticket, original
// input hashes and PublicFixtureOnly=1; it is NOT approved for private film.
//
// Production must replace the public-fixture requirement with an independently
// signed one-use creator approval verified in this SCM authority. No model or
// project can supply arbitrary executables, scripts, argv, or host file paths.
#define NVP_P1F_EMBEDDED_IN_SCM_SERVICE 1
#include "nvp_p1f_windows_private_kernel_probe.cpp"
#include <wincrypt.h>
#include <algorithm>
#include <array>
#include <cctype>
#include <iomanip>
#include <stdexcept>
#include <vector>
#pragma comment(lib,"crypt32.lib")

static constexpr wchar_t NAME[]=L"NVP-P1F-SourceBound-Blender-Preview";
static constexpr wchar_t REG[]=L"SOFTWARE\\NVP\\P1F\\ApprovedPreview";
static SERVICE_STATUS_HANDLE scm_handle=nullptr;
static SERVICE_STATUS scm_status{};

static std::wstring reg_string(HKEY key,LPCWSTR name,bool optional=false) {
    DWORD type=0,size=0;
    LONG rc=RegQueryValueExW(key,name,nullptr,&type,nullptr,&size);
    if(optional&&rc==ERROR_FILE_NOT_FOUND)return L"";
    require(rc==ERROR_SUCCESS && type==REG_SZ && size>=2 && size<=1024,
            "SCM-only finite source authorization field missing or invalid");
    std::vector<wchar_t> buf(size/sizeof(wchar_t)+1,0);
    rc=RegQueryValueExW(key,name,nullptr,&type,
        reinterpret_cast<LPBYTE>(buf.data()),&size);
    require(rc==ERROR_SUCCESS,"SCM finite source authorization read failed");
    return std::wstring(buf.data());
}
static bool hexsha(const std::wstring& s) {
    return s.size()==64&&std::all_of(s.begin(),s.end(),[](wchar_t c){
        return (c>=L'0'&&c<=L'9')||(c>=L'a'&&c<=L'f');
    });
}
static bool safe_id(const std::wstring& s) {
    if(s.size()<2||s.size()>40)return false;
    if(!((s[0]>=L'A'&&s[0]<=L'Z')||(s[0]>=L'a'&&s[0]<=L'z')))
        return false;
    return std::all_of(s.begin()+1,s.end(),[](wchar_t c){
        return (c>=L'A'&&c<=L'Z')||(c>=L'a'&&c<=L'z')||
               (c>=L'0'&&c<=L'9')||c==L'_'||c==L'-';
    });
}
static std::wstring sha256(const fs::path& file) {
    HCRYPTPROV prov=0; HCRYPTHASH hash=0;
    require(CryptAcquireContextW(&prov,nullptr,nullptr,PROV_RSA_AES,
                                CRYPT_VERIFYCONTEXT)!=FALSE,
            "No trusted Windows SHA256 provider");
    try {
        require(CryptCreateHash(prov,CALG_SHA_256,0,0,&hash)!=FALSE,
                "Cannot create native original source SHA256");
        std::ifstream in(file,std::ios::binary);
        if(!in.good()) {
            // All operands are trusted, fixed filenames; never emit a
            // project-controlled host path or source content in the receipt.
            throw std::runtime_error("Pinned source open failed for reviewed file "+
                file.filename().string()+"; CRT errno="+std::to_string(errno));
        }
        std::array<char,1024*128> buffer{};
        while(in) {
            in.read(buffer.data(),buffer.size());
            const auto n=in.gcount();
            if(n>0)
                require(CryptHashData(hash,
                    reinterpret_cast<const BYTE*>(buffer.data()),
                    static_cast<DWORD>(n),0)!=FALSE,
                    "Windows SHA256 original source hash failed");
        }
        require(in.eof(),"Original source read failed during SHA256");
        BYTE digest[32]{};DWORD size=sizeof(digest);
        require(CryptGetHashParam(hash,HP_HASHVAL,digest,&size,0)!=FALSE
                && size==32,"Cannot read pinned Windows source digest");
        std::wostringstream out;
        out<<std::hex<<std::setfill(L'0');
        for(BYTE b:digest)out<<std::setw(2)<<static_cast<int>(b);
        CryptDestroyHash(hash);CryptReleaseContext(prov,0);
        return out.str();
    } catch(...) {
        if(hash)CryptDestroyHash(hash);
        CryptReleaseContext(prov,0);
        throw;
    }
}
static fs::path no_reparse_file(const fs::path& f) {
    DWORD attributes=GetFileAttributesW(f.c_str());
    require(attributes!=INVALID_FILE_ATTRIBUTES &&
            (attributes&FILE_ATTRIBUTE_REPARSE_POINT)==0 &&
            (attributes&FILE_ATTRIBUTE_DIRECTORY)==0,
            "Pinned original source must be regular, never a link");
    return f;
}
static void private_acl_proof(const fs::path& dir) {
    DWORD attr=GetFileAttributesW(dir.c_str());
    require(attr!=INVALID_FILE_ATTRIBUTES &&
            (attr&FILE_ATTRIBUTE_DIRECTORY)!=0 &&
            (attr&FILE_ATTRIBUTE_REPARSE_POINT)==0,
            "Service-approved source root must be real, not reparse");
    PACL acl=nullptr;PSECURITY_DESCRIPTOR sd=nullptr;
    DWORD rc=GetNamedSecurityInfoW(const_cast<wchar_t*>(dir.c_str()),
        SE_FILE_OBJECT,DACL_SECURITY_INFORMATION,
        nullptr,nullptr,&acl,nullptr,&sd);
    require(rc==ERROR_SUCCESS && acl!=nullptr,
            "SCM source workspace requires actual non-null DACL");
    BYTE sid_bytes[SECURITY_MAX_SID_SIZE]{};
    DWORD sid_size=sizeof(sid_bytes);
    require(CreateWellKnownSid(WinBuiltinUsersSid,nullptr,sid_bytes,&sid_size),
            "Cannot verify standard Users source ACL");
    TRUSTEE_W trustee{};
    trustee.TrusteeForm=TRUSTEE_IS_SID;
    trustee.ptstrName=reinterpret_cast<LPWSTR>(sid_bytes);
    ACCESS_MASK rights=0;
    rc=GetEffectiveRightsFromAclW(acl,&trustee,&rights);
    LocalFree(sd);
    require(rc==ERROR_SUCCESS &&
            !(rights&(FILE_WRITE_DATA|FILE_APPEND_DATA|WRITE_DAC|WRITE_OWNER)),
            "Private source staging root writable by standard users");
}
struct Request {
    std::wstring ticket,id,project,plan,binary,script,usda,pcm,spec;
};
static Request consume_approved_public_preview() {
    HKEY key=nullptr;
    require(RegOpenKeyExW(HKEY_LOCAL_MACHINE,REG,0,
            KEY_QUERY_VALUE|KEY_SET_VALUE,&key)==ERROR_SUCCESS,
            "No host-only HKLM one-use private worker authorization");
    Request r{};
    try {
        r.ticket=reg_string(key,L"PendingId");
        r.id=reg_string(key,L"JobId");
        r.project=reg_string(key,L"ProjectId");
        r.plan=reg_string(key,L"OriginalPlanSha256");
        r.binary=reg_string(key,L"BlenderSha256");
        r.script=reg_string(key,L"FixedScriptSha256");
        r.usda=reg_string(key,L"OriginalUsdSha256");
        r.pcm=reg_string(key,L"OriginalPcmSha256");
        r.spec=reg_string(key,L"FrameSpecSha256");
        const std::wstring fixture=reg_string(key,L"PublicFixtureOnly");
        const std::wstring used=reg_string(key,L"ConsumedId",true);
        require(r.ticket.size()==32&&
                std::all_of(r.ticket.begin(),r.ticket.end(),[](wchar_t c){
                    return (c>=L'0'&&c<=L'9')||(c>=L'a'&&c<=L'f');
                }) && r.ticket!=used && safe_id(r.id) &&
                r.project.size()==32 && hexsha(r.plan) &&
                hexsha(r.binary)&&hexsha(r.script)&&
                hexsha(r.usda)&&hexsha(r.pcm)&&hexsha(r.spec),
                "Wrong or replayed finite source/job/Blender identity");
        require(fixture==L"1",
                "Private film denied: no independent signed creator approval verifier");
        // Fail-stop before touching the installed Blender or original bytes.
        DWORD n=static_cast<DWORD>((r.ticket.size()+1)*sizeof(wchar_t));
        require(RegSetValueExW(key,L"ConsumedId",0,REG_SZ,
                reinterpret_cast<const BYTE*>(r.ticket.c_str()),n)==ERROR_SUCCESS,
                "Cannot durably consume SCM source approval");
        require(RegDeleteValueW(key,L"PendingId")==ERROR_SUCCESS &&
                RegFlushKey(key)==ERROR_SUCCESS,
                "SCM one-use native source approval consumption failed");
    } catch(...) {RegCloseKey(key);throw;}
    RegCloseKey(key);
    return r;
}
static void durable_file(const fs::path& path,const std::string& text) {
    HANDLE f=CreateFileW(path.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,
                         FILE_ATTRIBUTE_NORMAL,nullptr);
    require(f!=INVALID_HANDLE_VALUE,"Refuse replayed SCM worker output/receipt");
    DWORD n=0;BOOL ok=WriteFile(f,text.data(),static_cast<DWORD>(text.size()),&n,nullptr);
    BOOL flushed=FlushFileBuffers(f);
    CloseHandle(f);
    require(ok&&flushed&&n==text.size(),
            "SCM native journal was not durably fsynced");
}
static fs::path program_data() {
    wchar_t path[MAX_PATH+1]{};
    DWORD n=GetEnvironmentVariableW(L"ProgramData",path,MAX_PATH);
    require(n>0&&n<MAX_PATH,"Trusted OS ProgramData unavailable");
    return fs::path(path);
}
static fs::path installed_blender() {
    wchar_t path[MAX_PATH+1]{};
    DWORD n=GetEnvironmentVariableW(L"ProgramFiles",path,MAX_PATH);
    require(n>0&&n<MAX_PATH,"Trusted OS ProgramFiles unavailable");
    return fs::path(path)/L"NVP"/L"Blender"/L"blender.exe";
}
static int run_source_bound_blender() {
    Request r=consume_approved_public_preview();
    const fs::path job=program_data()/L"NVP"/L"P1F"/L"ApprovedJobs"/r.id;
    const fs::path binary=no_reparse_file(installed_blender());
    private_acl_proof(job);
    const fs::path script=no_reparse_file(job/L"fixed_cycles.py");
    const fs::path usd=no_reparse_file(job/L"original.usda");
    const fs::path pcm=no_reparse_file(job/L"original_pcm.wav");
    const fs::path spec=no_reparse_file(job/L"frame_spec.json");
    require(!fs::exists(job/L"original_frame.png") &&
            !fs::exists(job/L"cycles_audit.json") &&
            !fs::exists(job/L"scm_native_source_receipt.txt") &&
            !fs::exists(job/L"scm_native_started.txt"),
            "Never run once-consumed native source job/output twice");
    require(sha256(binary)==r.binary &&
            sha256(script)==r.script &&
            sha256(usd)==r.usda && sha256(pcm)==r.pcm &&
            sha256(spec)==r.spec,
            "Source, Python script, portable Blender or PCM hash changed");
    durable_file(job/L"scm_native_started.txt",
        "format=nvp.p1f.scm_source_start.v1\n"+
        std::string("ticket=")+
        std::string(r.ticket.begin(),r.ticket.end())+
        "\nstate=ONE_USE_AUTHORIZATION_SPENT_BEFORE_EXEC\n");
    Handles h;
    h.profile=L"NVP.P1F.Preview."+r.ticket;
    require(SUCCEEDED(CreateAppContainerProfile(
        h.profile.c_str(),L"NVP P1F finite actor source",
        L"Source-hashed supervised preview",nullptr,0,&h.sid)) && h.sid,
        "Native service unable to create lowbox AppContainer SID");
    h.profile_created=true;
    allow_one_job_root(job.wstring(),h.sid,h);
    FWPM_SESSION0 session{};session.flags=FWPM_SESSION_FLAG_DYNAMIC;
    require(FwpmEngineOpen0(nullptr,RPC_C_AUTHN_WINNT,nullptr,&session,
                            &h.wfp)==ERROR_SUCCESS && h.wfp,
            "No root-owned WFP dynamic source-specific filter session");
    add_wfp_block(h.wfp,h.sid,FWPM_LAYER_ALE_AUTH_CONNECT_V4);
    add_wfp_block(h.wfp,h.sid,FWPM_LAYER_ALE_AUTH_CONNECT_V6);
    add_wfp_block(h.wfp,h.sid,FWPM_LAYER_ALE_AUTH_RECV_ACCEPT_V4);
    add_wfp_block(h.wfp,h.sid,FWPM_LAYER_ALE_AUTH_RECV_ACCEPT_V6);
    h.job=CreateJobObjectW(nullptr,nullptr);
    require(h.job!=nullptr,"SCM native Blender Job Object absent");
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
    limits.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE|
                                           JOB_OBJECT_LIMIT_JOB_MEMORY;
    limits.JobMemoryLimit=8192ULL*1024ULL*1024ULL;
    require(SetInformationJobObject(h.job,JobObjectExtendedLimitInformation,
                &limits,sizeof(limits)),
            "Real Blender Job memory/kill-on-close limits failed");
    SECURITY_CAPABILITIES cap{};
    cap.AppContainerSid=h.sid;
    SIZE_T bytes=0;InitializeProcThreadAttributeList(nullptr,1,0,&bytes);
    require(bytes>0,"Native lowbox attribute unavailable");
    std::vector<BYTE> backing(bytes);
    auto attrs=reinterpret_cast<PPROC_THREAD_ATTRIBUTE_LIST>(backing.data());
    require(InitializeProcThreadAttributeList(attrs,1,0,&bytes),
            "Native lowbox startup attribute allocation failed");
    require(UpdateProcThreadAttribute(attrs,0,
            PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
            &cap,sizeof(cap),nullptr,nullptr),
            "No actual lowbox SCM worker token attachment");
    STARTUPINFOEXW startup{};
    startup.StartupInfo.cb=sizeof(startup);
    startup.lpAttributeList=attrs;
    std::wstring command=quoted(binary.wstring())+
        L" -b --factory-startup -t 2 --python-exit-code 70 --python "+
        quoted(script.wstring())+L" -- --plan "+quoted(spec.wstring())+
        L" --take "+quoted(usd.wstring())+
        L" --output "+quoted((job/L"original_frame.png").wstring())+
        L" --audit "+quoted((job/L"cycles_audit.json").wstring());
    std::vector<wchar_t> args(command.begin(),command.end());args.push_back(0);
    PROCESS_INFORMATION pi{};
    BOOL started=CreateProcessW(
        binary.c_str(),args.data(),nullptr,nullptr,FALSE,
        EXTENDED_STARTUPINFO_PRESENT|CREATE_SUSPENDED|CREATE_NO_WINDOW,
        nullptr,job.c_str(),&startup.StartupInfo,&pi);
    DeleteProcThreadAttributeList(attrs);
    require(started!=FALSE,"No actual suspended SCM-owned Blender execution");
    h.process=pi.hProcess;h.thread=pi.hThread;
    require(AssignProcessToJobObject(h.job,h.process),
            "Blender ran outside one-use Windows Job");
    BOOL in_job=FALSE;
    require(IsProcessInJob(h.process,h.job,&in_job)&&in_job,
            "Cannot independently verify Blender Job custody");
    require(assigned_token_appcontainer(h.process,h.sid),
            "Blender lowbox token/SID differs from WFP package rule");
    require(ResumeThread(h.thread)!=DWORD(-1),
            "Native AppContainer Blender worker cannot resume");
    DWORD waited=WaitForSingleObject(h.process,600000);
    if(waited!=WAIT_OBJECT_0) {
        TerminateJobObject(h.job,13);
        throw std::runtime_error("Original source Blender exceeded finite 600s execution");
    }
    DWORD exitcode=0;
    require(GetExitCodeProcess(h.process,&exitcode)&&exitcode==0,
            "Native SCM-owned Blender worker failed under real AppContainer/WFP");
    CloseHandle(h.job);h.job=nullptr; // Drain/kill descendants before audit.
    require(sha256(script)==r.script && sha256(usd)==r.usda &&
            sha256(pcm)==r.pcm && sha256(spec)==r.spec,
            "Original source changed during protected Blender execution");
    auto picture=no_reparse_file(job/L"original_frame.png");
    auto audit=no_reparse_file(job/L"cycles_audit.json");
    {
        std::ifstream image(picture,std::ios::binary);
        const char magic[8]={'\x89','P','N','G','\r','\n','\x1a','\n'};
        char head[8]{};
        image.read(head,sizeof(head));
        require(image.gcount()==8 && std::equal(head,head+8,magic),
                "Actual supervised source picture was not PNG");
    }
    const std::wstring picture_sha=sha256(picture),audit_sha=sha256(audit);
    const std::string receipt=
        "format=nvp.p1f.scm_native_public_blender_source_receipt.v1\n"
        "status=SCM_NATIVE_WORKER_OS_VERIFIED_NOT_FILM\n"
        "ticket="+std::string(r.ticket.begin(),r.ticket.end())+"\n"+
        "job_id="+std::string(r.id.begin(),r.id.end())+"\n"+
        "project_id="+std::string(r.project.begin(),r.project.end())+"\n"+
        "plan_sha256="+std::string(r.plan.begin(),r.plan.end())+"\n"+
        "original_png_sha256="+std::string(picture_sha.begin(),picture_sha.end())+"\n"+
        "blender_audit_sha256="+std::string(audit_sha.begin(),audit_sha.end())+"\n"+
        "actual_scm_owned_appcontainer_wfp_job=1\n"
        "private_source_approval_proved=0\n"
        "finished_film=0\n";
    durable_file(job/L"scm_native_source_receipt.txt",receipt);
    return 0;
}
static SERVICE_STATUS_HANDLE service_handle=nullptr;
static SERVICE_STATUS service_status{};
static void update_service(DWORD state,DWORD code=0) {
    if(!service_handle)return;
    service_status.dwServiceType=SERVICE_WIN32_OWN_PROCESS;
    service_status.dwCurrentState=state;
    service_status.dwControlsAccepted=0;
    service_status.dwWin32ExitCode=code?ERROR_SERVICE_SPECIFIC_ERROR:0;
    service_status.dwServiceSpecificExitCode=code;
    service_status.dwCheckPoint=state==SERVICE_START_PENDING?1:0;
    service_status.dwWaitHint=state==SERVICE_START_PENDING?15000:0;
    SetServiceStatus(service_handle,&service_status);
}
static void WINAPI service_control(DWORD) {
    // No caller may bypass one-use consumption or kill the worker while
    // the SCM service holds its Windows Job and four WFP filters.
}
static void WINAPI service_main(DWORD,LPWSTR*) {
    service_handle=RegisterServiceCtrlHandlerW(NAME,service_control);
    if(!service_handle)return;
    update_service(SERVICE_START_PENDING);
    int result=91;
    try {
        update_service(SERVICE_RUNNING);
        result=run_source_bound_blender();
    } catch(const std::exception& error) {
        OutputDebugStringA(error.what());
        // This binary categorically accepts PUBLIC fixtures only. Preserve
        // the exact failing native stage for independent SCM diagnostics;
        // never include source content or a creator path in this receipt.
        try {
            auto folder=program_data()/L"NVP"/L"P1F"/L"KernelOnly";
            fs::create_directories(folder);
            std::ofstream log(folder/L"scm_blender_last_error.txt",
                              std::ios::binary|std::ios::trunc);
            log<<error.what()<<std::endl;
            log.flush();
        } catch(...) {}
    }
    update_service(SERVICE_STOPPED,result);
}
int wmain(int argc,wchar_t** argv) {
    if(argc==2 && std::wstring(argv[1])==L"--service") {
        SERVICE_TABLE_ENTRYW services[]={
            {const_cast<LPWSTR>(NAME),service_main},{nullptr,nullptr}};
        return StartServiceCtrlDispatcherW(services)?0:95;
    }
    // Intentionally NO CLI dry-run, no command line job spec, no ability to
    // directly spawn a private Blender worker outside SCM/one-use approval.
    return 96;
}
