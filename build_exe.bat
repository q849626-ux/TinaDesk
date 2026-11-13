@echo off
rem Build TinaDesk.exe on Windows. Needs Python 3 (with tkinter) and internet for PyInstaller.
rem If "python" is not on PATH, run first:  set TINA_PY=C:\path\to\python.exe
cd /d "%~dp0"
if defined TINA_PY goto custom
python --version >nul 2>nul
if not errorlevel 1 goto usepython
py -3 --version >nul 2>nul
if not errorlevel 1 goto usepy
goto nopy

:custom
set PYCMD="%TINA_PY%"
goto build
:usepython
set PYCMD=python
goto build
:usepy
set PYCMD=py -3

:build
%PYCMD% -m pip install --upgrade pyinstaller
if errorlevel 1 goto fail
%PYCMD% -m PyInstaller --noconfirm --clean --onefile --noconsole --name TinaDesk desk_widgets.py
if errorlevel 1 goto fail
copy /y "dist\TinaDesk.exe" "%~dp0TinaDesk.exe" >nul
echo.
echo DONE: %~dp0TinaDesk.exe
echo (You may delete the build and dist folders and TinaDesk.spec.)
pause
exit /b 0

:nopy
echo Python not found. Install Python 3 or set TINA_PY to your python.exe, then run again.
pause
exit /b 1

:fail
echo.
echo BUILD FAILED. Please check the messages above.
pause
exit /b 1
