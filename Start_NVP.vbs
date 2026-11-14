' NVP developer preview launcher. Not a packaged desktop installer.
Set Shell = CreateObject("WScript.Shell")
Set Fso = CreateObject("Scripting.FileSystemObject")
BaseDir = Fso.GetParentFolderName(WScript.ScriptFullName)
Shell.Run Chr(34) & BaseDir & "\launch_npv.bat" & Chr(34), 1, False
