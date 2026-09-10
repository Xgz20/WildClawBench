@echo off
setlocal
set "DRIVER_DIR=%~dp0..\drivers\codex-desktop"
if not exist "%DRIVER_DIR%\node_modules\playwright-core" (
  echo 尚未安装依赖，请先在 orchestrate-web-e2e\drivers\codex-desktop 目录执行 npm ci 1>&2
  exit /b 2
)
node "%DRIVER_DIR%\register-projects.mjs" %*
exit /b %errorlevel%
