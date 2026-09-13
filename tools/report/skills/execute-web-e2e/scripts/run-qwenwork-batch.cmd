@echo off
setlocal
node "%~dp0run-qwenwork-batch.mjs" %*
exit /b %errorlevel%
