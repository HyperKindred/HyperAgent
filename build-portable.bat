@echo off
cd /d "%~dp0"

echo ===========================================
echo  HyperAgent Portable Build Script
echo ===========================================
echo.

set VERSION=0.2.1
echo Version: %VERSION%

rem ---- (1/5) Build frontend -------------------------------------------
echo === (1/5) Build frontend ===
cd frontend
call npm run build
if %errorlevel% neq 0 exit /b %errorlevel%

rem ---- (2/5) Prepare backend resources -------------------------------
echo === (2/5) Prepare backend resources ===
cd ..
if not exist frontend\backend-resources mkdir frontend\backend-resources
copy .env frontend\backend-resources\.env >nul

rem ---- (3/5) Build backend executable --------------------------------
echo === (3/5) Build backend exe ===
uv run pyinstaller --onefile --name hyperagent-backend --distpath frontend/backend-resources --noconfirm --hidden-import=uvicorn.logging --hidden-import=uvicorn.loops.auto --hidden-import=uvicorn.protocols.http.auto backend_launcher.py
if %errorlevel% neq 0 exit /b %errorlevel%

rem ---- (3.5/5) Copy frontend dist alongside backend exe --------------
echo === (3.5/5) Copy frontend dist ===
xcopy /E /I /Y frontend\dist frontend\backend-resources\dist

rem ---- (4/5) Package Electron portable -------------------------------
echo === (4/5) Package Electron portable ===
cd frontend
if exist electron rmdir /s /q electron
mkdir electron
copy ..\electron\main.cjs electron\
copy ..\electron\preload.cjs electron\
copy ..\electron\icon.ico electron\ >nul 2>&1
copy ..\electron\icon.png electron\ >nul 2>&1
copy ..\electron\tray-icon.png electron\ >nul 2>&1

call npx electron-builder --win --x64 --dir
if %errorlevel% neq 0 exit /b %errorlevel%

rem ---- (5/5) Copy config --------------------------------------------
echo === (5/5) Copy config ===
copy backend-resources\.env ..\electron-dist\win-unpacked\.env
copy backend-resources\.env.example ..\electron-dist\win-unpacked\.env.example

if exist "..\electron-dist\HyperAgent" rmdir /s /q "..\electron-dist\HyperAgent"
rename ..\electron-dist\win-unpacked "HyperAgent"

echo ===========================================
echo  Done!
echo ===========================================
echo.
echo  Portable:  ..\electron-dist\HyperAgent\   (double-click HyperAgent.exe)
echo.
echo  Version:   v%VERSION%
echo  Time:      %DATE% %TIME%
echo ===========================================
if not "%1"=="--no-pause" pause
