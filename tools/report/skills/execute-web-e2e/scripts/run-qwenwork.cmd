@echo off
setlocal
node "%~dp0run-qwenwork.mjs" %*
exit /b %errorlevel%
