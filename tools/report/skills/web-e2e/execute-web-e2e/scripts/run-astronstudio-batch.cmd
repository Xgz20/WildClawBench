@echo off
setlocal
node "%~dp0run-astronstudio-batch.mjs" %*
exit /b %errorlevel%
