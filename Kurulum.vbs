' Runs the Kelam setup wizard without a console window.

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

base = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = base

pythonw = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python312\pythonw.exe"
If Not fso.FileExists(pythonw) Then
    pythonw = "pythonw.exe"
End If

sh.Run """" & pythonw & """ -u wizard.py", 0, False
