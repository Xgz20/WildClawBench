@echo off
setlocal
chcp 65001 >nul
set "PACKAGE_ROOT=%~dp0"
set "HELPER=%PACKAGE_ROOT%tools\prepare_scoring_workspace.py"

where py >nul 2>nul
if errorlevel 1 goto try_python
py -3 "%HELPER%" --package-root "%PACKAGE_ROOT%"
set "STATUS=%ERRORLEVEL%"
goto done

:try_python
where python >nul 2>nul
if errorlevel 1 goto no_python
python "%HELPER%" --package-root "%PACKAGE_ROOT%"
set "STATUS=%ERRORLEVEL%"
goto done

:no_python
echo FAIL: 未找到 Python。请使用支持目录合并的 ZIP 工具手工准备评分工作空间。
set "STATUS=2"

:done
echo.
pause
exit /b %STATUS%
