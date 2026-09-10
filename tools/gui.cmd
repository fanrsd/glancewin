@echo off
REM Double-click to open the Face Unlock tray control panel.
REM --no-presence: no camera probes, so the webcam LED stays off until you
REM unlock. Enable walk-away locking from the tray menu if you want it.
start "" "%~dp0..\.venv\Scripts\pythonw.exe" -m presence_monitor --no-presence
