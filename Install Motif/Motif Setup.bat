@echo off
setlocal

set "HERE=%~dp0.."
set "TARGET=%HERE%\setup\motif_setup.py"

if not exist "%TARGET%" goto :incomplete

set "PY="
py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 set "PY=py -3"

if not defined PY (
  pythonw -c "import sys" >nul 2>nul
  if not errorlevel 1 set "PY=pythonw"
)
if not defined PY (
  python -c "import sys" >nul 2>nul
  if not errorlevel 1 set "PY=python"
)

if not defined PY goto :needpython

%PY% "%TARGET%" %*
if errorlevel 1 goto :problem
exit /b 0

:incomplete
mshta "javascript:new ActiveXObject('WScript.Shell').Popup('This copy of Motif Setup looks incomplete. Please re-download it and try again.',0,'Motif Setup',48);close();"
exit /b 1

:needpython
mshta "javascript:var s=new ActiveXObject('WScript.Shell');if(s.Popup('Motif needs a free component this computer does not have yet. Open the download page now?',0,'Motif Setup',36)==6){s.Run('https://www.python.org/downloads/windows/');}close();"
exit /b 1

:problem
mshta "javascript:new ActiveXObject('WScript.Shell').Popup('Setup ran into a problem. Details were saved to the .motif folder in your user profile. Please try again, or get in touch for help.',0,'Motif Setup',48);close();"
exit /b 1
