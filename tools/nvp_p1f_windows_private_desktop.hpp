#pragma once
// Finite private window station/desktop for an SCM-owned USER32 workload.
// In non-interactive Windows Session 0, even otherwise correct AppContainer
// processes can fail USER32.dll's DLL_PROCESS_ATTACH with STATUS_DLL_INIT_FAILED
// if forced onto the inherited service station/desktop. This grants access
// ONLY to an ephemeral private low-integrity station/desktop, NEVER WinSta0.
//
// Original AppContainer token, WFP no-egress filters and Job Object remain
// unchanged. The objects belong to one random 32-hex, independently spent
// SCM ticket and are closed when the last child exits.
#include <windows.h>
#include <sddl.h>
#include <string>
#include <stdexcept>

namespace nvp_p1f_private_desktop {
struct PrivateDesktop {
    HWINSTA station=nullptr;
    HDESK desktop=nullptr;
    PSECURITY_DESCRIPTOR station_security=nullptr;
    PSECURITY_DESCRIPTOR desktop_security=nullptr;
    std::wstring qualified;

    static PSECURITY_DESCRIPTOR descriptor(const wchar_t* sddl) {
        PSECURITY_DESCRIPTOR p=nullptr;
        if(!ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl,SDDL_REVISION_1,&p,nullptr)||!p)
            throw std::runtime_error("Private low-integrity Win32 USER32 security descriptor unavailable");
        return p;
    }
    explicit PrivateDesktop(const std::wstring& ticket) {
        if(ticket.size()!=32)
            throw std::runtime_error("Invalid private desktop one-use SCM ticket");
        for(wchar_t x:ticket)
            if(!((x>=L'0'&&x<=L'9')||(x>=L'a'&&x<=L'f')))
                throw std::runtime_error("Private desktop ticket is not canonical");
        // Window-station rights follow the minimal USER32 lowbox contract
        // (0x20327). Desktop rights are restricted to this private object;
        // no public WinSta0/Default ACL or label is modified.
        static constexpr wchar_t station_sddl[]=
            L"D:(A;;GA;;;SY)(A;;GA;;;BA)"
            L"(A;;0x20327;;;AC)(A;;0x20327;;;S-1-15-2-2)"
            L"(A;;0xf037f;;;RC)"
            L"S:(ML;;NW;;;LW)";
        static constexpr wchar_t desktop_sddl[]=
            L"D:(A;;GA;;;SY)(A;;GA;;;BA)"
            L"(A;;0xf01ff;;;AC)(A;;0xf01ff;;;S-1-15-2-2)"
            L"(A;;0xf01ff;;;RC)"
            L"S:(ML;;NW;;;LW)";
        station_security=descriptor(station_sddl);
        desktop_security=descriptor(desktop_sddl);
        SECURITY_ATTRIBUTES attr{};
        attr.nLength=sizeof(attr);
        attr.lpSecurityDescriptor=station_security;
        attr.bInheritHandle=FALSE;
        const std::wstring name=L"NvpP1fPrivate_"+ticket;
        station=CreateWindowStationW(name.c_str(),0,WINSTA_ALL_ACCESS,&attr);
        if(!station)
            throw std::runtime_error("SCM cannot create unique private USER32 window station");
        HWINSTA original=GetProcessWindowStation();
        if(!original||!SetProcessWindowStation(station))
            throw std::runtime_error("SCM failed to switch to private station for desktop creation");
        try {
            attr.lpSecurityDescriptor=desktop_security;
            // WinUser exposes DESKTOP_* bits, but not a portable
            // DESKTOP_ALL_ACCESS macro across all Windows 10/11 SDKs.
            // Numeric 0xF01FF is STANDARD_RIGHTS_REQUIRED | 0x1FF
            // and matches the exact private object DACL below.
            static constexpr ACCESS_MASK PRIVATE_DESKTOP_ALL=0x000F01FF;
            desktop=CreateDesktopW(L"Default",nullptr,nullptr,0,
                                   PRIVATE_DESKTOP_ALL,&attr);
        } catch(...) {
            SetProcessWindowStation(original);
            throw;
        }
        BOOL restored=SetProcessWindowStation(original);
        if(!desktop||!restored)
            throw std::runtime_error("SCM could not isolate private low-integrity desktop");
        qualified=name+L"\\Default";
    }
    PrivateDesktop(const PrivateDesktop&)=delete;
    PrivateDesktop& operator=(const PrivateDesktop&)=delete;
    ~PrivateDesktop() {
        if(desktop)CloseDesktop(desktop);
        if(station)CloseWindowStation(station);
        if(station_security)LocalFree(station_security);
        if(desktop_security)LocalFree(desktop_security);
    }
};
}
