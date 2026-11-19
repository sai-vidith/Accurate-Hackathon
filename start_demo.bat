@echo off
rem Disruption Copilot demo for Windows: four story accounts on fresh demo data.
rem   start_demo.bat        rebuild the demo data (dates move with today), then start the app
rem   start_demo.bat keep   start on the demo data as you left it
setlocal
cd /d "%~dp0"

set "PY=python"
where py >nul 2>nul && set "PY=py -3"

if not exist ".env" if exist ".env.example" (
  copy ".env.example" ".env" >nul
  echo Created .env from .env.example. Paste your Groq, Gemini and openrouteservice keys into it.
)
if not exist ".venv\Scripts\python.exe" (
  echo Setting up Python, first run only...
  %PY% -m venv .venv || goto :fail
  ".venv\Scripts\python.exe" -m pip install -q -r backend\requirements.txt || goto :fail
)
if not exist "frontend\node_modules" (
  echo Installing frontend packages, first run only...
  pushd frontend
  call npm install --no-fund --no-audit || goto :fail
  popd
)

set "COPILOT_DATA_DIR=%~dp0backend\data_demo"
if /i "%~1"=="keep" if exist "%COPILOT_DATA_DIR%\users.json" goto :run
echo Building fresh demo data...
pushd backend
"..\.venv\Scripts\python.exe" seed_demo.py --reset || goto :fail
popd

:run
start "Disruption Copilot - backend" /d "%~dp0backend" cmd /k ..\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
echo.
echo App: http://localhost:5173    Log in as meera, arjun, vikram or rohit (password demo1234)
echo Close this window and the backend window to stop.
echo.
start "" cmd /c "timeout /t 6 >nul && start http://localhost:5173"
cd frontend
call npm run dev
goto :eof

:fail
echo.
echo Something failed above. Check that Python 3.11+ and Node.js 20+ are installed.
pause
exit /b 1
