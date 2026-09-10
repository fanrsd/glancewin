@echo off
REM Double-click, or run from anywhere, to open the setup wizard.
REM /D sets the working directory to the repo root: "python -m presence_monitor"
REM resolves packages against the current directory, so launching this from
REM tools\ used to fail with ModuleNotFoundError - silently, under pythonw.
start "" /D "%~dp0.." "%~dp0..\.venv\Scripts\pythonw.exe" -m presence_monitor.wizard
