@echo off
setlocal
node "%~dp0run-astronstudio.mjs" %*
exit /b %errorlevel%
