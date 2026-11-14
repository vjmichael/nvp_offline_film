// P1-F SCM-OWNED WINDOWS KERNEL CHILD — FIXED PUBLIC NO-MEDIA TEST ONLY.
// This proves Service Control Manager custody of an AppContainer+WFP+Job
// worker and one-use independently provisioned ADMIN/SYSTEM registry ticket.
//
// NO producer-specific command, Blender, studio, project assets, script paths
// or long-lived privileged execute API are accepted. A real, independently
// authorized finite Blender production request broker remains a separate
// security/release gate. This can NEVER attest private film delivery.
#define NVP_P1F_EMBEDDED_IN_SCM_SERVICE 1
#include "nvp_p1f_windows_private_kernel_probe.cpp"
#include <algorithm>

static constexpr wchar_t SERVICE_NAME[]=L"NVP-P1F-Kernel-Broker-Probe";
static constexpr wchar_t KEY_NAME[]=L"SOFTWARE\\NVP\\P1F\\KernelTicket";
static SERVICE_STATUS_HANDLE status_handle=nullptr;
static SERVICE_STATUS status_value{};
static DWORD checkpoint=1;

static void status(DWORD state,DWORD code=0) {
    if(!status_handle) return;
    status_value.dwServiceType=SERVICE_WIN32_OWN_PROCESS;
    status_value.dwCurrentState=state;
    status_value.dwControlsAccepted=0; // never allow STOP to bypass job cleanup
    status_value.dwWin32ExitCode=code?ERROR_SERVICE_SPECIFIC_ERROR:ERROR_SUCCESS;
    status_value.dwServiceSpecificExitCode=code;
    status_value.dwCheckPoint=(state==SERVICE_START_PENDING)?checkpoint++:0;
    status_value.dwWaitHint=(state==SERVICE_START_PENDING)?15000:0;
    SetServiceStatus(status_handle,&status_value);
}

static void WINAPI service_control(DWORD) {
    // SCM termination on shutdown closes Job and dynamic WFP handles.
    // No external client may tell this finite authorized test to stop
    // before the one-use transaction has finished.
}

static std::wstring read_ticket(HKEY key,LPCWSTR name,bool required) {
    DWORD type=0,size=0;
    LONG rc=RegQueryValueExW(key,name,nullptr,&type,nullptr,&size);
    if(rc==ERROR_FILE_NOT_FOUND && !required) return L"";
    require(rc==ERROR_SUCCESS && type==REG_SZ && size>=4 && size<256,
            "Missing/invalid independent admin-only one-use kernel ticket");
    std::vector<wchar_t> buf((size/sizeof(wchar_t))+1,0);
    rc=RegQueryValueExW(key,name,nullptr,&type,
       reinterpret_cast<LPBYTE>(buf.data()),&size);
    require(rc==ERROR_SUCCESS,"Creator-service ticket read failed");
    return std::wstring(buf.data());
}

static std::wstring consume_one_use_service_ticket() {
    HKEY key=nullptr;
    LONG opened=RegOpenKeyExW(HKEY_LOCAL_MACHINE,KEY_NAME,0,
                             KEY_QUERY_VALUE|KEY_SET_VALUE,&key);
    require(opened==ERROR_SUCCESS,
            "Independently provisioned SCM authorization registry key unavailable");
    std::wstring pending,used;
    try {
        pending=read_ticket(key,L"PendingId",true);
        used=read_ticket(key,L"ConsumedId",false);
        require(pending.size()==32 &&
                std::all_of(pending.begin(),pending.end(),[](wchar_t c){
                    return (c>=L'0'&&c<=L'9')||
                           (c>=L'a'&&c<=L'f');
                }),"Invalid one-use admin/SCM ticket identity");
        require(pending!=used,"Previously consumed admin/SCM ticket replay");
        // Commit CONSUMED BEFORE launching an AppContainer/WFP worker:
        // failure/crash must never make the same scope executable again.
        DWORD bytes=static_cast<DWORD>((pending.size()+1)*sizeof(wchar_t));
        LONG rc=RegSetValueExW(key,L"ConsumedId",0,REG_SZ,
                              reinterpret_cast<const BYTE*>(pending.c_str()),bytes);
        require(rc==ERROR_SUCCESS,"SCM one-use durable consumption failed");
        rc=RegDeleteValueW(key,L"PendingId");
        require(rc==ERROR_SUCCESS,"SCM one-use pending ticket deletion failed");
        require(RegFlushKey(key)==ERROR_SUCCESS,
                "SCM one-use registry transaction could not be flushed");
    } catch(...) {
        RegCloseKey(key);
        throw;
    }
    RegCloseKey(key);
    return pending;
}

static void durable_service_receipt(const std::wstring& ticket,int code) {
    wchar_t program[MAX_PATH+1]{};
    DWORD count=GetEnvironmentVariableW(L"ProgramData",program,MAX_PATH);
    require(count>0 && count<MAX_PATH,"Trusted Windows ProgramData location unavailable");
    fs::path root=fs::path(program)/L"NVP"/L"P1F"/L"KernelOnly";
    fs::create_directories(root);
    fs::path receipt=root/(L"scm_receipt_"+ticket+L".txt");
    // CREATE_NEW deliberately refuses a previously reported ticket.
    HANDLE out=CreateFileW(receipt.c_str(),GENERIC_WRITE,0,nullptr,
                           CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
    require(out!=INVALID_HANDLE_VALUE,"Refuse duplicate SCM custody receipt");
    const std::string body=
        std::string("format=nvp.p1f.scm_native_kernel_probe.v1\n")+
        "ticket="+std::string(ticket.begin(),ticket.end())+"\n"+
        "scm_service_owned=1\n"+
        "appcontainer_wfp_job_kernel_probe="+std::to_string(code)+"\n"+
        "creator_film_approved=0\n"+
        "private_blender_execution=0\n"+
        "production_ready=0\n";
    DWORD written=0;
    BOOL saved=WriteFile(out,body.data(),
                         static_cast<DWORD>(body.size()),&written,nullptr);
    BOOL synced=FlushFileBuffers(out);
    CloseHandle(out);
    require(saved&&synced&&written==body.size(),
            "SCM ownership receipt not durably written");
}

static void WINAPI service_main(DWORD,LPWSTR*) {
    status_handle=RegisterServiceCtrlHandlerW(SERVICE_NAME,service_control);
    if(!status_handle) return;
    status(SERVICE_START_PENDING);
    int code=95;
    try {
        std::wstring ticket=consume_one_use_service_ticket();
        status(SERVICE_RUNNING);
        code=parent();  // Actual fixed AppContainer + 4 WFP filters + Job
        durable_service_receipt(ticket,code);
    } catch(const std::exception& ex) {
        OutputDebugStringA(ex.what());
        code=95;
    }
    status(SERVICE_STOPPED,static_cast<DWORD>(code));
}

int wmain(int argc,wchar_t** argv) {
    try {
        if(argc==6&&std::wstring(argv[1])==L"--child")
            return child(argc,argv);
        if(argc==2&&std::wstring(argv[1])==L"--service") {
            SERVICE_TABLE_ENTRYW table[]={
                {const_cast<LPWSTR>(SERVICE_NAME),service_main},
                {nullptr,nullptr}};
            if(!StartServiceCtrlDispatcherW(table))
                throw std::runtime_error("SCM dispatcher did not launch service");
            return 0;
        }
        throw std::runtime_error("Finite SCM service accepts only --service/--child");
    } catch(const std::exception& ex) {
        std::cerr<<"NVP_P1F_SCM_KERNEL_ADMISSION_FAILED: "<<ex.what()
                 <<" GetLastError="<<GetLastError()<<"\n";
        return 96;
    }
}
