@echo off
setlocal
node "%~dp0run-workbuddy-batch.mjs" %*
exit /b %errorlevel%
