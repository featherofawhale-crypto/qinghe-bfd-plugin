Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
appPath = scriptDir & "\app.py"

pythonw = ""
On Error Resume Next
pythonw = shell.RegRead("HKCU\Software\Python\PyLauncher\InstallDir")
On Error GoTo 0

If pythonw <> "" Then
    candidate = fso.BuildPath(pythonw, "pyw.exe")
    If fso.FileExists(candidate) Then
        shell.Run """" & candidate & """ -3 """ & appPath & """", 0, False
        WScript.Quit 0
    End If
End If

shell.Run "pyw.exe -3 """ & appPath & """", 0, False
