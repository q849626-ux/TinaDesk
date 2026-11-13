@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYW="
if defined TINA_PYW (
  set "PYW=%TINA_PYW%"
  goto run
)
if defined TINA_PY (
  for %%I in ("%TINA_PY%") do (
    if exist "%%~dpIpythonw.exe" (set "PYW=%%~dpIpythonw.exe") else (set "PYW=%TINA_PY%")
  )
  goto run
)
where pythonw >nul 2>nul
if not errorlevel 1 (
  for /f "delims=" %%I in ('where pythonw') do (
    set "PYW=%%I"
    goto run
  )
)
where python >nul 2>nul
if not errorlevel 1 (
  for /f "delims=" %%I in ('where python') do (
    set "PY=%%I"
    goto havepy
  )
)
py -3 --version >nul 2>nul
if not errorlevel 1 (
  for /f "delims=" %%I in ('py -3 -c "import sys; print(sys.executable)"') do set "PY=%%I"
  goto havepy
)
goto nopy

:havepy
for %%I in ("%PY%") do (
  if exist "%%~dpIpythonw.exe" (set "PYW=%%~dpIpythonw.exe") else (set "PYW=%PY%")
)
goto run

:run
start "" "%PYW%" desk_widgets.py
exit /b 0

:nopy
echo Python not found. Install Python 3 and check "tcl/tk", or set TINA_PYW to pythonw.exe, then run again.
echo 未找到 Python。请安装 Python 3 并勾选 tcl/tk，或设置 TINA_PYW 后重试。
pause
exit /b 1
