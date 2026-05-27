Set WshShell = CreateObject("WScript.Shell")
' Run the Python launcher completely invisibly (0 means hide window)
WshShell.Run "pythonw.exe nvp_launcher.py", 0, False