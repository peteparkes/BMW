@echo off
:: =============================================================================
:: BMW E90 Diagnostics -- Windows installer
:: =============================================================================
:: Creates a desktop shortcut and installs Python dependencies.
::
:: Usage: Double-click install.bat  -OR-  run from Command Prompt
::
:: What it does:
::   1. Checks for Python 3.10+
::   2. Installs python-can and pyserial via pip
::   3. Creates a desktop shortcut (.lnk) via PowerShell
:: =============================================================================

setlocal enabledelayedexpansion

title BMW E90 Diagnostics - Installer

echo.
echo  ###########################################################
echo  #    BMW E90 320i N46B20B -- ECU Diagnostics Installer   #
echo  ###########################################################
echo.

:: ---------------------------------------------------------------------------
:: 1. Find Python 3.10+
:: ---------------------------------------------------------------------------
set "PYTHON="
for %%P in (python python3) do (
    if "!PYTHON!"=="" (
        where %%P >nul 2>&1 && (
            for /f "tokens=2 delims= " %%V in ('%%P --version 2^>^&1') do (
                set "PY_VER=%%V"
            )
            :: Check major.minor >= 3.10
            for /f "tokens=1,2 delims=." %%A in ("!PY_VER!") do (
                if %%A GEQ 3 (
                    if %%B GEQ 10 (
                        set "PYTHON=%%P"
                    )
                )
            )
        )
    )
)

if "%PYTHON%"=="" (
    echo [ERROR] Python 3.10 or higher is required but was not found.
    echo         Download from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [OK]   Found Python %PY_VER% at:
%PYTHON% -c "import sys; print('       ' + sys.executable)"
echo.

:: ---------------------------------------------------------------------------
:: 2. Install / upgrade Python packages
:: ---------------------------------------------------------------------------
echo [INFO] Installing Python packages...

%PYTHON% -m pip install --quiet --upgrade pip
if %errorlevel% neq 0 (
    echo [WARN] Could not upgrade pip. Continuing anyway.
)

%PYTHON% -m pip install --quiet --upgrade python-can pyserial
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install python-can or pyserial.
    echo         Try running manually: %PYTHON% -m pip install python-can pyserial
    pause
    exit /b 1
)
echo [OK]   python-can and pyserial installed.

:: Check tkinter (built-in on Windows Python but verify)
%PYTHON% -c "import tkinter" >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] tkinter not found. Try reinstalling Python from python.org and
    echo        ensure the "tcl/tk and IDLE" optional feature is checked.
) else (
    echo [OK]   tkinter is available.
)
echo.

:: ---------------------------------------------------------------------------
:: 3. Create desktop shortcut via PowerShell
:: ---------------------------------------------------------------------------
set "SCRIPT_DIR=%~dp0"
set "GUI_SCRIPT=%SCRIPT_DIR%bmw_e90_gui.py"
set "DESKTOP=%USERPROFILE%\Desktop"
set "SHORTCUT=%DESKTOP%\BMW E90 Diagnostics.lnk"

echo [INFO] Creating desktop shortcut...

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ws = New-Object -ComObject WScript.Shell;" ^
    "$sc = $ws.CreateShortcut('%SHORTCUT%');" ^
    "$sc.TargetPath = '%PYTHON%';" ^
    "$sc.Arguments = ([char]34 + '%GUI_SCRIPT%' + [char]34 + ' --demo');" ^
    "$sc.WorkingDirectory = '%SCRIPT_DIR%';" ^
    "$sc.Description = 'BMW E90 N46B20B ECU Diagnostics Dashboard';" ^
    "$sc.Save()"

if %errorlevel% neq 0 (
    echo [WARN] Could not create desktop shortcut via PowerShell.
    echo        Run the GUI manually: %PYTHON% "%GUI_SCRIPT%" --demo
) else (
    echo [OK]   Desktop shortcut created: %SHORTCUT%
    echo        NOTE: The shortcut uses --demo (offline) mode.
    echo        To use a real K+DCAN cable, change the shortcut target to:
    echo          %PYTHON% "%GUI_SCRIPT%" --interface kdcan --port COM3
)
echo.

:: ---------------------------------------------------------------------------
:: Done
:: ---------------------------------------------------------------------------
echo  ###########################################################
echo  #  Installation complete!                                #
echo  #                                                         #
echo  #  Launch GUI:  %PYTHON% bmw_e90_gui.py --demo           #
echo  #  CLI tool:    %PYTHON% bmw_e90_diagnostics.py --demo   #
echo  ###########################################################
echo.
pause
endlocal
