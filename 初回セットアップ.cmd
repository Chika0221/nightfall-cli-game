@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\setup.ps1" %*
if errorlevel 1 (
  echo.
  echo NIGHTFALL could not complete the operation. Review the message above.
)
pause
