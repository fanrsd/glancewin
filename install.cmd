@echo off
REM Double-click this on a machine with nothing installed.
REM cmd.exe bypasses the PowerShell execution policy prompt for the user.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1" %*
echo.
pause
