@echo off
setlocal
node "%~dp0run-workbuddy.mjs" %*
exit /b %errorlevel%
