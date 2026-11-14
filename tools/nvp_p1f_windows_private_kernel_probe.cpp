// P1-F Windows first-party native AppContainer + WFP kernel admission probe.
// TEST-ONLY: does NOT accept Blender executable paths, creator sources,
// approvals, job requests or a general command. Production SCM broker remains
// a separately authorized component. A real kernel failure returns nonzero.
// Compile with VS C++17 Win10 SDK: userenv.lib fwpuclnt.lib advapi32.lib
// ws2_32.lib ole32.lib.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define _WIN32_WINNT 0x0A00
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <userenv.h>
#include <fwpmu.h>
#include <aclapi.h>
#include <sddl.h>
#include <objbase.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#pragma comment(lib,"userenv.lib")
#pragma comment(lib,"fwpuclnt.lib")
#pragma comment(lib,"advapi32.lib")
#pragma comment(lib,"ws2_32.lib")
#pragma comment(lib,"ole32.lib")

namespace fs=std::filesystem;

static std::wstring quoted(const std::wstring& s) {
    std::wstring q=L"\"";
    for(wchar_t c:s) {
        if(c==L'"') throw std::runtime_error("Quote in kernel probe pathname");
        q+=c;
    }
    return q+L"\"";
}

static void require(bool okay,const char* reason) {
    if(!okay) throw std::runtime_error(reason);
}

static bool readable(const std::wstring& path) {
    HANDLE h=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,
                         OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(h==INVALID_HANDLE_VALUE) return false;
    CloseHandle(h);
    return true;
}

static bool child_appcontainer() {
    HANDLE tok=nullptr;
    if(!OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&tok)) return false;
    DWORD state=0,bytes=0;
    BOOL ok=GetTokenInformation(tok,TokenIsAppContainer,
                                &state,sizeof(state),&bytes);
    CloseHandle(tok);
    return ok && state==1;
}

static bool denied_host_loopback(unsigned short port) {
    WSADATA d{};
    if(WSAStartup(MAKEWORD(2,2),&d)!=0) return false;
    SOCKET s=socket(AF_INET,SOCK_STREAM,IPPROTO_TCP);
    if(s==INVALID_SOCKET){WSACleanup();return false;}
    sockaddr_in target{};
    target.sin_family=AF_INET;
    target.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
    target.sin_port=htons(port);
    bool denied=(connect(s,reinterpret_cast<sockaddr*>(&target),
                         sizeof(target))==SOCKET_ERROR);
    closesocket(s);
    WSACleanup();
    return denied;
}

static int child(int argc,wchar_t** argv) {
    require(argc==6,"P1-F native child has a finite four-argument contract");
    const std::wstring approved=argv[2],hidden=argv[3],output=argv[5];
    const int port=_wtoi(argv[4]);
    require(port>0 && port<=65535,"Invalid parent-only witness port");
    // AppContainer token and real sandbox file/network effects must ALL pass.
    // The child cannot self-attest WFP policy installation; the trusted
    // parent must independently query successful FwpmFilterAdd receipts.
    const bool token=child_appcontainer();
    const bool own=readable(approved);
    const bool private_hidden=!readable(hidden);
    const bool net=denied_host_loopback(static_cast<unsigned short>(port));
    HANDLE h=CreateFileW(output.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,
                          FILE_ATTRIBUTE_NORMAL,nullptr);
    if(h==INVALID_HANDLE_VALUE) return 84;
    std::string result=std::string("token=")+(token?"1":"0")+
                       "\napproved="+(own?"1":"0")+
                       "\nhidden="+(private_hidden?"1":"0")+
                       "\nnet_denied="+(net?"1":"0")+"\n";
    DWORD written=0;
    BOOL wrote=WriteFile(h,result.data(),static_cast<DWORD>(result.size()),
                         &written,nullptr);
    FlushFileBuffers(h);
    CloseHandle(h);
    if(!wrote || written!=result.size()) return 85;
    return token&&own&&private_hidden&&net?0:86;
}

struct Handles {
    HANDLE job=nullptr;
    HANDLE process=nullptr;
    HANDLE thread=nullptr;
    HANDLE token=nullptr;
    HANDLE wfp=nullptr;
    PACL new_acl=nullptr;
    PSECURITY_DESCRIPTOR old_sd=nullptr;
    PSID sid=nullptr;
    bool profile_created=false;
    std::wstring profile;
    ~Handles() {
        if(job) CloseHandle(job); // Kill any descendants in original Job.
        if(thread)CloseHandle(thread);
        if(process)CloseHandle(process);
        if(token)CloseHandle(token);
        if(wfp) FwpmEngineClose0(wfp); // Dynamic WFP blocks revoked on close.
        if(new_acl)LocalFree(new_acl);
        if(old_sd)LocalFree(old_sd);
        if(sid)FreeSid(sid);
        if(profile_created)DeleteAppContainerProfile(profile.c_str());
    }
};

static void add_wfp_block(HANDLE engine,PSID sid,const GUID& layer) {
    FWPM_FILTER_CONDITION0 condition{};
    condition.fieldKey=FWPM_CONDITION_ALE_PACKAGE_ID;
    condition.matchType=FWP_MATCH_EQUAL;
    condition.conditionValue.type=FWP_SID;
    condition.conditionValue.sid=reinterpret_cast<SID*>(sid);
    FWPM_FILTER0 filter{};
    filter.displayData.name=const_cast<wchar_t*>(L"NVP-P1F one-use no-egress native proof");
    filter.layerKey=layer;
    filter.subLayerKey=FWPM_SUBLAYER_UNIVERSAL;
    filter.action.type=FWP_ACTION_BLOCK;
    filter.weight.type=FWP_UINT8;
    filter.weight.uint8=15;
    filter.filterCondition=&condition;
    filter.numFilterConditions=1;
    UINT64 id=0;
    DWORD rc=FwpmFilterAdd0(engine,&filter,nullptr,&id);
    require(rc==ERROR_SUCCESS && id!=0,
            "Actual AppContainer-specific WFP BLOCK filter admission failed");
}

static void allow_one_job_root(const std::wstring& folder,PSID sid,Handles& h) {
    PACL old_acl=nullptr;
    DWORD rc=GetNamedSecurityInfoW(
        const_cast<wchar_t*>(folder.c_str()),SE_FILE_OBJECT,
        DACL_SECURITY_INFORMATION,nullptr,nullptr,&old_acl,nullptr,&h.old_sd);
    require(rc==ERROR_SUCCESS,"Cannot read existing one-job filesystem ACL");
    EXPLICIT_ACCESSW access{};
    access.grfAccessPermissions=FILE_GENERIC_READ|FILE_GENERIC_WRITE|
                                FILE_GENERIC_EXECUTE|DELETE;
    access.grfAccessMode=GRANT_ACCESS;
    access.grfInheritance=SUB_CONTAINERS_AND_OBJECTS_INHERIT;
    access.Trustee.TrusteeForm=TRUSTEE_IS_SID;
    access.Trustee.TrusteeType=TRUSTEE_IS_USER;
    access.Trustee.ptstrName=reinterpret_cast<LPWSTR>(sid);
    rc=SetEntriesInAclW(1,&access,old_acl,&h.new_acl);
    require(rc==ERROR_SUCCESS,"One-job AppContainer ACL construction failed");
    rc=SetNamedSecurityInfoW(const_cast<wchar_t*>(folder.c_str()),
                             SE_FILE_OBJECT,DACL_SECURITY_INFORMATION,
                             nullptr,nullptr,h.new_acl,nullptr);
    require(rc==ERROR_SUCCESS,"Cannot grant AppContainer access to exact job root");
}

static bool assigned_token_appcontainer(HANDLE process,PSID expected) {
    HANDLE token=nullptr;
    if(!OpenProcessToken(process,TOKEN_QUERY,&token)) return false;
    DWORD state=0,bytes=0;
    BOOL valid=GetTokenInformation(token,TokenIsAppContainer,
                                   &state,sizeof(state),&bytes);
    DWORD needed=0;
    GetTokenInformation(token,TokenAppContainerSid,nullptr,0,&needed);
    std::vector<BYTE> backing(needed);
    bool same=false;
    if(needed && valid && state==1 &&
       GetTokenInformation(token,TokenAppContainerSid,
                            backing.data(),needed,&needed)) {
        auto* data=reinterpret_cast<TOKEN_APPCONTAINER_INFORMATION*>(backing.data());
        same=data->TokenAppContainer && EqualSid(expected,data->TokenAppContainer);
    }
    CloseHandle(token);
    return same;
}

static int parent() {
    wchar_t executable[MAX_PATH+1]{};
    require(GetModuleFileNameW(nullptr,executable,MAX_PATH)!=0,
            "Native first-party executable path missing");
    const fs::path self(executable);
    const fs::path root=fs::temp_directory_path()/
        (L"nvp_p1f_private_kernel_"+std::to_wstring(GetCurrentProcessId()));
    const fs::path job=root/L"approved";
    fs::create_directories(job);
    fs::path child_exe=job/L"nvp_p1f_private_probe.exe";
    fs::copy_file(self,child_exe,fs::copy_options::none);
    const fs::path allowed=job/L"approved_input.txt";
    const fs::path hidden=root/L"host_private_sentinel.txt";
    const fs::path output=job/L"kernel_observed.txt";
    {std::ofstream f(allowed,std::ios::binary);f<<"NVP_PUBLIC_TEST";}
    {std::ofstream f(hidden,std::ios::binary);f<<"NOT_IN_APPCONTAINER";}
    Handles h;
    h.profile=L"NVP.P1F.FiniteProbe."+std::to_wstring(GetCurrentProcessId());
    HRESULT app=CreateAppContainerProfile(
        h.profile.c_str(),L"NVP P1F finite native test",
        L"Public source-free kernel isolation acceptance",nullptr,0,&h.sid);
    require(SUCCEEDED(app) && h.sid,
            "Real Windows AppContainer profile creation failed");
    h.profile_created=true;
    allow_one_job_root(job.wstring(),h.sid,h);
    FWPM_SESSION0 session{};
    session.flags=FWPM_SESSION_FLAG_DYNAMIC;
    DWORD net=FwpmEngineOpen0(nullptr,RPC_C_AUTHN_WINNT,nullptr,&session,&h.wfp);
    require(net==ERROR_SUCCESS && h.wfp,
            "Windows service lacks independent kernel WFP filter admission");
    add_wfp_block(h.wfp,h.sid,FWPM_LAYER_ALE_AUTH_CONNECT_V4);
    add_wfp_block(h.wfp,h.sid,FWPM_LAYER_ALE_AUTH_CONNECT_V6);
    add_wfp_block(h.wfp,h.sid,FWPM_LAYER_ALE_AUTH_RECV_ACCEPT_V4);
    add_wfp_block(h.wfp,h.sid,FWPM_LAYER_ALE_AUTH_RECV_ACCEPT_V6);

    WSADATA d{};
    require(WSAStartup(MAKEWORD(2,2),&d)==0,"Host witness socket unavailable");
    SOCKET listener=socket(AF_INET,SOCK_STREAM,IPPROTO_TCP);
    require(listener!=INVALID_SOCKET,"Host witness listener unavailable");
    sockaddr_in addr{};
    addr.sin_family=AF_INET;
    addr.sin_port=0;
    addr.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
    require(bind(listener,reinterpret_cast<sockaddr*>(&addr),
                 sizeof(addr))==0,"Host loopback witness bind failed");
    require(listen(listener,1)==0,"Host loopback witness listen failed");
    int addrlen=sizeof(addr);
    require(getsockname(listener,reinterpret_cast<sockaddr*>(&addr),
                        &addrlen)==0,"Host loopback witness port unknown");
    unsigned short port=ntohs(addr.sin_port);

    HANDLE job_handle=CreateJobObjectW(nullptr,nullptr);
    require(job_handle!=nullptr,"Windows Job Object creation failed");
    h.job=job_handle;
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION info{};
    info.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    require(SetInformationJobObject(h.job,JobObjectExtendedLimitInformation,
            &info,sizeof(info)),"Kernel kill-on-close Job limit failed");

    SECURITY_CAPABILITIES cap{};
    cap.AppContainerSid=h.sid;
    SIZE_T n=0;
    InitializeProcThreadAttributeList(nullptr,1,0,&n);
    require(n!=0,"AppContainer native startup attribute size unavailable");
    std::vector<BYTE> buf(n);
    auto attrs=reinterpret_cast<PPROC_THREAD_ATTRIBUTE_LIST>(buf.data());
    require(InitializeProcThreadAttributeList(attrs,1,0,&n),
            "AppContainer native attribute initialization failed");
    require(UpdateProcThreadAttribute(attrs,0,
            PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
            &cap,sizeof(cap),nullptr,nullptr),
            "Cannot attach genuine AppContainer lowbox token capabilities");
    STARTUPINFOEXW startup{};
    startup.StartupInfo.cb=sizeof(startup);
    startup.lpAttributeList=attrs;
    PROCESS_INFORMATION process{};
    std::wstring command=quoted(child_exe.wstring())+L" --child "+
        quoted(allowed.wstring())+L" "+quoted(hidden.wstring())+
        L" "+std::to_wstring(port)+L" "+quoted(output.wstring());
    std::vector<wchar_t> mutable_command(command.begin(),command.end());
    mutable_command.push_back(0);
    BOOL created=CreateProcessW(
        child_exe.c_str(),mutable_command.data(),nullptr,nullptr,FALSE,
        EXTENDED_STARTUPINFO_PRESENT|CREATE_SUSPENDED|CREATE_NO_WINDOW,
        nullptr,job.c_str(),&startup.StartupInfo,&process);
    DeleteProcThreadAttributeList(attrs);
    require(created!=0,"Native AppContainer child creation denied");
    h.process=process.hProcess;h.thread=process.hThread;
    require(AssignProcessToJobObject(h.job,h.process),
            "Cannot assign suspended AppContainer child to kill-on-close Job");
    BOOL in_job=FALSE;
    require(IsProcessInJob(h.process,h.job,&in_job)&&in_job,
            "Native kernel Job membership not independently verified");
    require(assigned_token_appcontainer(h.process,h.sid),
            "Suspended worker token is not the exact AppContainer SID");
    require(ResumeThread(h.thread)!=DWORD(-1),
            "AppContainer child could not resume under WFP+Job custody");
    DWORD waited=WaitForSingleObject(h.process,20000);
    require(waited==WAIT_OBJECT_0,"Native AppContainer child timed out");
    DWORD exit_code=0;
    require(GetExitCodeProcess(h.process,&exit_code)&&exit_code==0,
            "Private AppContainer file/network child verification failed");
    std::ifstream receipt(output,std::ios::binary);
    require(receipt.good(),"No real AppContainer child kernel receipt");
    std::stringstream data;data<<receipt.rdbuf();
    require(data.str()=="token=1\napproved=1\nhidden=1\nnet_denied=1\n",
            "Independent native AppContainer/WFP/ACL witness mismatch");
    closesocket(listener);
    WSACleanup();
    std::cout<<"NVP_P1F_REAL_WIN_APPCONTAINER_WFP_JOB_PASS\n";
    std::cout<<"all: AppContainer token, exact SID, 4 WFP blocks, job kernel membership, "
               "approved-only file, forbidden host file and denied host socket\n";
    return 0;
}

#ifndef NVP_P1F_EMBEDDED_IN_SCM_SERVICE
int wmain(int argc,wchar_t** argv) {
    try {
        if(argc==6&&std::wstring(argv[1])==L"--child")
            return child(argc,argv);
        require(argc==1,"Only fixed self-contained native witness supported");
        return parent();
    } catch(const std::exception& ex) {
        std::cerr<<"NVP_P1F_REAL_WIN_APPCONTAINER_WFP_JOB_FAILED: "<<ex.what()
                 <<" GetLastError="<<GetLastError()<<"\n";
        return 90;
    }
}
#endif // NVP_P1F_EMBEDDED_IN_SCM_SERVICE
