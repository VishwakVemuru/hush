@echo off
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% -c "import webview, psutil, pystray, PIL" >nul 2>nul
if errorlevel 1 (
  echo First run: installing what hush. needs...
  %PY% -m pip install --upgrade -r requirements.txt
  if errorlevel 1 ( echo. & echo Install failed. Make sure Python 3.10+ is installed from python.org. & pause & exit /b 1 )
)
for /f "delims=" %%i in ('%PY% -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))"') do set PYW=%%i
start "" "%PYW%" "%~dp0app.py"
