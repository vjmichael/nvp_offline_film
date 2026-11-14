// G03-S1 independent native Windows sandbox probe. Never handles original films.
// Build with MSVC; evidence is actual kernel token, a real restricted CreateFile,
// and a live localhost listening socket rather than mocked denials.
#define _WIN32_WINNT 0x0A00
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <stdio.h>
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
    int connected = connect(sock, reinterpret_cast<sockaddr*>(&address), sizeof(address));
    int error = WSAGetLastError();
    closesocket(sock);
    WSACleanup();
    if (connected == 0) {
        fputs("G03_UNAUTHORIZED_LOOPBACK_CONNECTED\n", stderr);
        return 48;
    }
    if (error == WSAECONNREFUSED) {
        fputs("G03_LOOPBACK_LISTENER_NOT_PROVED_REACHABLE\n", stderr);
        return 49;
    }
    printf("G03_NATIVE_UNGRANTED_NETWORK_DENIED_PASS WSA=%d\n", error);
    return 0;
}
