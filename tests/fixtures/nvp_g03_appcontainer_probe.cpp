// G03-S1 independent native Windows sandbox probe. Never handles original films.
// Build with MSVC; evidence is actual kernel token, a real restricted CreateFile,
// and a live localhost listening socket rather than mocked denials.
#define _WIN32_WINNT 0x0A00
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <stdio.h>
#include <vector>
#pragma comment(lib, "Ws2_32.lib")
#pragma comment(lib, "Advapi32.lib")

int wmain(int argc, wchar_t **argv) {
    if (argc < 2) return 40;
    HANDLE token = nullptr;
    DWORD app = 0, size = 0;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) return 41;
    if (!GetTokenInformation(token, TokenIsAppContainer, &app, sizeof(app), &size) || app != 1) {
        CloseHandle(token); return 42;
    }
    DWORD required=0;
    GetTokenInformation(token, TokenCapabilities, nullptr, 0, &required);
    if (GetLastError()!=ERROR_INSUFFICIENT_BUFFER ||
            required<sizeof(DWORD) || required>65536) {
        CloseHandle(token);return 53;
    }
    std::vector<unsigned char> capabilities(required);
    if (!GetTokenInformation(token, TokenCapabilities,
            capabilities.data(),required,&required)) {
        CloseHandle(token);return 54;
    }
    auto* groups=reinterpret_cast<const TOKEN_GROUPS*>(capabilities.data());
    if (groups->GroupCount!=0) {
        CloseHandle(token);
        fputs("G03_UNREVIEWED_NATIVE_NETWORK_CAPABILITY\n",stderr);
        return 55;
    }
    CloseHandle(token);
    puts("G03_NATIVE_KERNEL_APPCONTAINER_TOKEN_PASS");
    if (wcscmp(argv[1], L"--sleep") == 0) {
        fflush(stdout);
        Sleep(90000);
        return 0;
    }
    if (argc != 3) return 43;
    HANDLE fd = CreateFileW(argv[1], GENERIC_READ, FILE_SHARE_READ, nullptr,
                            OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (fd != INVALID_HANDLE_VALUE) {
        CloseHandle(fd);
        fputs("G03_UNAUTHORIZED_FILE_READ_SUCCEEDED\n", stderr);
        return 44;
    }
    if (GetLastError() != ERROR_ACCESS_DENIED) {
        fprintf(stderr, "Unexpected file error %lu\n", GetLastError());
        return 45;
    }
    puts("G03_NATIVE_UNGRANTED_FILE_DENIED_PASS");
    WSADATA ws{};
    if (WSAStartup(MAKEWORD(2,2), &ws) != 0) return 46;
    SOCKET sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (sock == INVALID_SOCKET) {
        puts("G03_NATIVE_UNGRANTED_NETWORK_DENIED_PASS");
        WSACleanup();
        return 0;
    }
    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    unsigned long port = wcstoul(argv[2], nullptr, 10);
    if (!port || port > 65535) { closesocket(sock);WSACleanup(); return 47; }
    address.sin_port = htons(static_cast<u_short>(port));
    // Never let Winsock's default blocking connect hide the OS security
    // result behind an unbounded 20-75 second TCP retry. The real host
    // listener was proven reachable before this zero-capability child ran.
    u_long nonblocking=1;
    if (ioctlsocket(sock,FIONBIO,&nonblocking)!=0) {
        closesocket(sock);WSACleanup();return 56;
    }
    int connected=connect(sock,reinterpret_cast<sockaddr*>(&address),
                          sizeof(address));
    int error=connected==0?0:WSAGetLastError();
    if (connected!=0 && error==WSAEWOULDBLOCK) {
        fd_set writable,excepted;
        FD_ZERO(&writable);FD_ZERO(&excepted);
        FD_SET(sock,&writable);FD_SET(sock,&excepted);
        timeval deadline{};
        deadline.tv_sec=4;
        int ready=select(0,nullptr,&writable,&excepted,&deadline);
        if (ready==SOCKET_ERROR) error=WSAGetLastError();
        else if (ready==0) error=WSAETIMEDOUT;
        else {
            int socket_error=0;
            int error_size=sizeof(socket_error);
            if (getsockopt(sock,SOL_SOCKET,SO_ERROR,
                    reinterpret_cast<char*>(&socket_error),&error_size)==0)
                error=socket_error;
            else error=WSAGetLastError();
        }
    }
    closesocket(sock);
    WSACleanup();
    if (connected==0 || error==0) {
        fputs("G03_UNAUTHORIZED_LOOPBACK_CONNECTED\n",stderr);
        return 48;
    }
    if (error==WSAECONNREFUSED) {
        fputs("G03_LOOPBACK_LISTENER_NOT_PROVED_REACHABLE\n",stderr);
        return 49;
    }
    // A policy refusal (WSAEACCES) or bounded connection timeout, together
    // with TokenCapabilities GroupCount==0 and the proven live host socket,
    // is the required kernel-backed negative acceptance. Other unexpected
    // network errors are inconclusive, never silently treated as denial.
    if (error!=WSAEACCES && error!=WSAETIMEDOUT) {
        fprintf(stderr,"G03_UNEXPECTED_NATIVE_NETWORK_ERROR=%d\n",error);
        return 57;
    }
    printf("G03_NATIVE_UNGRANTED_NETWORK_DENIED_PASS WSA=%d\n",error);
    return 0;
}
