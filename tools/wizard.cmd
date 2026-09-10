@echo off
REM Double-click to open the step-by-step setup wizard.
start "" "%~dp0..\.venv\Scripts\pythonw.exe" -m presence_monitor.wizard
