@echo off
setlocal
set HERE=%~dp0..
start "" pythonw "%HERE%\setup\motif_setup.py"
if errorlevel 1 python "%HERE%\setup\motif_setup.py"
