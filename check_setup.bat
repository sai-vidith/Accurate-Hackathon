@echo off
rem Checks your keys, the AI (with web search) and the map lookups. Run start_demo.bat once first.
cd /d "%~dp0backend"
"..\.venv\Scripts\python.exe" check_setup.py
pause
