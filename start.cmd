@echo off
rem Double-click or run "start" from a terminal. Arguments are passed through (e.g. start -Reset).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
