@echo off
REM Runs hush. as admin so the system-wide (hosts file) site block works too.
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
for /f "delims=" %%i in ('%PY% -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))"') do set PYW=%%i
powershell -NoProfile -Command "Start-Process -FilePath '%PYW%' -ArgumentList '\"%~dp0app.py\"' -WorkingDirectory '%~dp0' -Verb RunAs"
