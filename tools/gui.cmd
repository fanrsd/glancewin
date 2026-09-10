@echo off
REM Double-click, or run from anywhere, to open the Face Unlock tray.
REM --no-presence: no camera probes, so the webcam LED stays off until you
REM unlock. Enable walk-away locking from the tray menu if you want it.
REM /D sets the working directory to the repo root - "python -m" resolves
REM packages against it, and pythonw reports nothing when that fails.
start "" /D "%~dp0.." "%~dp0..\.venv\Scripts\pythonw.exe" -m presence_monitor --no-presence
