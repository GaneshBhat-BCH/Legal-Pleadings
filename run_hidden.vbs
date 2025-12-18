Set WshShell = CreateObject("WScript.Shell")
Set Http = CreateObject("MSXML2.XMLHTTP")
Set FSO = CreateObject("Scripting.FileSystemObject")

' Get the directory where this script is located
ScriptPath = FSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = ScriptPath

' Function to check if the API is healthy
Function IsApiHealthy()
    IsApiHealthy = False
    On Error Resume Next
    Http.Open "GET", "http://localhost:8000/", False
    Http.Send
    If Err.Number = 0 Then
        If Http.Status = 200 Then
            IsApiHealthy = True
        End If
    End If
    On Error GoTo 0
End Function

' 1. Initial Health Check
If Not IsApiHealthy() Then
    ' 2. Cold Start Logic: Setup -> Init DB -> Run
    ' Run setup_env.bat --auto (Wait for completion)
    WshShell.Run "cmd /c setup_env.bat --auto", 0, True
    
    ' Run init_db.bat --auto (Wait for completion)
    WshShell.Run "cmd /c init_db.bat --auto", 0, True
    
    ' Run run_backend.bat --background (Don't wait)
    WshShell.Run "cmd /c run_backend.bat --background", 0, False
End If

' 3. Wait and check for health (Wait for project to be fully up)
' We will check every 2 seconds for up to 60 seconds (cold start takes longer)
MaxRetries = 30
RetryCount = 0
Success = False

Do While RetryCount < MaxRetries
    WScript.Sleep 2000
    If IsApiHealthy() Then
        Success = True
        Exit Do
    End If
    RetryCount = RetryCount + 1
Loop

' 4. Final confirmation popup
If Success Then
    MsgBox "Project is now UP and Ready!" & vbCrLf & _
           "API Documentation: http://localhost:8000/docs", 64, "Startup Success"
Else
    MsgBox "Project failed to start automatically." & vbCrLf & _
           "Please run 'run_backend.bat' manually to see what's wrong.", 16, "Startup Error"
End If
