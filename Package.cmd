@echo off
rem Build the distribution ZIP. Tries Python in this order:
rem   1) py launcher  2) python in PATH  3) the bundled Python installed by Setup.cmd
setlocal
cd /d "%~dp0"
where py >nul 2>nul && (py -3 tools\package.py %* & goto done)
where python >nul 2>nul && (python tools\package.py %* & goto done)
if exist "%LOCALAPPDATA%\VideoButton\python\python.exe" ("%LOCALAPPDATA%\VideoButton\python\python.exe" tools\package.py %* & goto done)
echo Python was not found. Install Python or run Setup.cmd first.
:done
pause
