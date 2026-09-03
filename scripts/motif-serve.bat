@echo off
REM Start the Motif.AI engine on Windows.
setlocal
set HERE=%~dp0..
set PYTHONPATH=%HERE%\engine;%PYTHONPATH%
if "%~1"=="" (
  python -m motif serve
) else (
  python -m motif %*
)
