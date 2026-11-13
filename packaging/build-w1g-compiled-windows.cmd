@echo off
setlocal EnableExtensions
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" (
  echo No real Visual Studio 2022 MSVC installation discovered.
  exit /b 2
)
"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath > "%TEMP%\nvp-w1g-msvc-location.txt"
if errorlevel 1 exit /b 2
set /p "VSROOT=" < "%TEMP%\nvp-w1g-msvc-location.txt"
if not exist "%VSROOT%\VC\Auxiliary\Build\vcvars64.bat" (
  echo Missing actual x64 C++ build toolchain.
  exit /b 2
)
call "%VSROOT%\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 exit /b 2
where cl
if errorlevel 1 exit /b 2
if not exist acceptance_artifacts mkdir acceptance_artifacts
python -m tools.nvp_w1g_compile_first_party_workers --out acceptance_artifacts\w1g-compiled-windows --platform windows-amd64 --compiler cl
if errorlevel 1 exit /b 4
python -m tools.nvp_w1g_native_worker_functional_acceptance --binary-dir acceptance_artifacts\w1g-compiled-windows --platform windows-amd64 --evidence acceptance_artifacts\w1g-windows-native-functional.json
if errorlevel 1 exit /b 5
python -m tools.nvp_w1g_native_link_audit --binary-dir acceptance_artifacts\w1g-compiled-windows --platform windows-amd64 --output acceptance_artifacts\w1g-windows-native-imports.json
if errorlevel 1 exit /b 6
echo Five actual compiled Windows PE64 role slices verified under original native Job Objects.
exit /b 0
