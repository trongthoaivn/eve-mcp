@echo off
setlocal enabledelayedexpansion

echo.
echo  =========================================================
echo   EVE-MCP Server  ^|  Install Script  (source + venv)
echo   Configures agent platforms to run from source
echo   Requires: build.bat to have been run first
echo  =========================================================
echo.

:: ================================================================
:: CONFIGURATION
:: ================================================================
set PROJECT_DIR=%~dp0
if "%PROJECT_DIR:~-1%"=="\" set PROJECT_DIR=%PROJECT_DIR:~0,-1%

set BUILD_DIR=%PROJECT_DIR%\build
set VENV_PYTHON_BUILD=%BUILD_DIR%\.venv\Scripts\python.exe
set SERVER_SCRIPT_BUILD=%BUILD_DIR%\server.py

set TARGET_DIR=%USERPROFILE%\AppData\Local\eve-mcp
set VENV_PYTHON=%TARGET_DIR%\.venv\Scripts\python.exe
set SERVER_SCRIPT=%TARGET_DIR%\server.py

set SKILLS_SOURCE=%PROJECT_DIR%\skills

:: Platform paths
set AGY_IDE_CONFIG_DIR=%USERPROFILE%\.gemini\config
set AGY_IDE_MCP_CONFIG=%AGY_IDE_CONFIG_DIR%\mcp_config.json
set AGY_IDE_SKILLS_DIR=%AGY_IDE_CONFIG_DIR%\skills

set AGY_CLI_CONFIG_DIR=%USERPROFILE%\.gemini\antigravity-cli
set AGY_CLI_MCP_CONFIG=%AGY_CLI_CONFIG_DIR%\mcp_config.json
set AGY_CLI_SKILLS_DIR=%AGY_CLI_CONFIG_DIR%\skills

set CLAUDE_CONFIG_DIR=%APPDATA%\Claude
set CLAUDE_MCP_CONFIG=%CLAUDE_CONFIG_DIR%\claude_desktop_config.json


:: ================================================================
:: PRE-CHECK: .venv must exist in build directory
:: ================================================================
if not exist "%VENV_PYTHON_BUILD%" (
    echo [Error] Virtual environment not found in build: %VENV_PYTHON_BUILD%
    echo         Please run build.bat first.
    pause & exit /b 1
)
echo [OK] Found build venv: %VENV_PYTHON_BUILD%

if not exist "%SERVER_SCRIPT_BUILD%" (
    echo [Error] server.py not found in build: %SERVER_SCRIPT_BUILD%
    echo         Please run build.bat first.
    pause & exit /b 1
)
echo [OK] Found build server: %SERVER_SCRIPT_BUILD%
echo.


:: ================================================================
:: PLATFORM SELECTION
:: ================================================================
echo  =========================================================
echo   Select platforms to configure:
echo  =========================================================
echo.
echo   [1] Antigravity IDE   %AGY_IDE_CONFIG_DIR%
echo   [2] Antigravity CLI   %AGY_CLI_CONFIG_DIR%
echo   [3] Claude Desktop    %CLAUDE_CONFIG_DIR%
echo   [a] All platforms
echo.
set /p CHOICE=  Enter choices (e.g: 1 2 or a): 

set DO_AGY_IDE=0
set DO_AGY_CLI=0
set DO_CLAUDE=0

echo !CHOICE! | findstr /i "a" >nul && (set DO_AGY_IDE=1 & set DO_AGY_CLI=1 & set DO_CLAUDE=1)
echo !CHOICE! | findstr "1" >nul && set DO_AGY_IDE=1
echo !CHOICE! | findstr "2" >nul && set DO_AGY_CLI=1
echo !CHOICE! | findstr "3" >nul && set DO_CLAUDE=1

echo.
echo  Selected:
if %DO_AGY_IDE%==1 echo    [x] Antigravity IDE
if %DO_AGY_CLI%==1 echo    [x] Antigravity CLI
if %DO_CLAUDE%==1  echo    [x] Claude Desktop
if %DO_AGY_IDE%==0 if %DO_AGY_CLI%==0 if %DO_CLAUDE%==0 (
    echo    [!] No platform selected. Exiting.
    pause & exit /b 0
)
echo.


:: ================================================================
:: STEP 1: Copy build to AppData and prepare .env
:: ================================================================
echo [Step 1/2] Copying build to AppData and preparing configuration...

echo          Copying files to %TARGET_DIR% ...
if not exist "%TARGET_DIR%" mkdir "%TARGET_DIR%"
xcopy /E /I /Y /R /Q "%BUILD_DIR%\*" "%TARGET_DIR%\" >nul

if exist "%PROJECT_DIR%\.env" (
    copy /Y "%PROJECT_DIR%\.env" "%TARGET_DIR%\" >nul
    echo          [OK] Using .env from project directory
) else (
    echo          [--] No .env found, skipping
)
echo.


:: ================================================================
:: STEP 2: Configure platforms
:: ================================================================
echo [Step 2/2] Configuring selected platforms...
echo.

:: Read EVE-NG settings from .env (from installed folder)
set EVE_HOST=
set EVE_USERNAME=
set EVE_PASSWORD=
set EVE_PROTOCOL=http
set EVE_SSL_VERIFY=false
set EVE_DISABLE_INSECURE_WARNINGS=true

if exist "%TARGET_DIR%\.env" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%TARGET_DIR%\.env") do (
        set "KEY=%%A"
        set "VAL=%%B"
        set "KEY=!KEY: =!"
        if "!KEY:~0,1!" neq "#" (
            if "!KEY!"=="EVE_HOST"                      set EVE_HOST=!VAL!
            if "!KEY!"=="EVE_USERNAME"                  set EVE_USERNAME=!VAL!
            if "!KEY!"=="EVE_PASSWORD"                  set EVE_PASSWORD=!VAL!
            if "!KEY!"=="EVE_PROTOCOL"                  set EVE_PROTOCOL=!VAL!
            if "!KEY!"=="EVE_SSL_VERIFY"                set EVE_SSL_VERIFY=!VAL!
            if "!KEY!"=="EVE_DISABLE_INSECURE_WARNINGS" set EVE_DISABLE_INSECURE_WARNINGS=!VAL!
        )
    )
)

:: Convert backslashes to forward slashes for JSON compatibility
set _MCP_CMD=%VENV_PYTHON:\=/%
set _MCP_ARG=%SERVER_SCRIPT:\=/%
set PY_SCRIPT=%TARGET_DIR%\configure_mcp.py

:: ---- Antigravity IDE ----
if %DO_AGY_IDE%==1 (
    echo  [Platform] Antigravity IDE
    if not exist "%AGY_IDE_CONFIG_DIR%" mkdir "%AGY_IDE_CONFIG_DIR%"
    if exist "%SKILLS_SOURCE%" (
        if not exist "%AGY_IDE_SKILLS_DIR%" mkdir "%AGY_IDE_SKILLS_DIR%"
        xcopy /E /I /Y /R /K /H "%SKILLS_SOURCE%\*" "%AGY_IDE_SKILLS_DIR%\" >nul 2>&1
        echo          [OK] Skills -> %AGY_IDE_SKILLS_DIR%
    )
    "%VENV_PYTHON%" "%PY_SCRIPT%" --config-file "%AGY_IDE_MCP_CONFIG%" --command "%_MCP_CMD%" --arg "%_MCP_ARG%" --with-env
    if !ERRORLEVEL! equ 0 (echo          [OK] %AGY_IDE_MCP_CONFIG%) else (echo          [Error] Failed)
    echo.
)

:: ---- Antigravity CLI ----
if %DO_AGY_CLI%==1 (
    echo  [Platform] Antigravity CLI
    if not exist "%AGY_CLI_CONFIG_DIR%" mkdir "%AGY_CLI_CONFIG_DIR%"
    if exist "%SKILLS_SOURCE%" (
        if not exist "%AGY_CLI_SKILLS_DIR%" mkdir "%AGY_CLI_SKILLS_DIR%"
        xcopy /E /I /Y /R /K /H "%SKILLS_SOURCE%\*" "%AGY_CLI_SKILLS_DIR%\" >nul 2>&1
        echo          [OK] Skills -> %AGY_CLI_SKILLS_DIR%
    )
    "%VENV_PYTHON%" "%PY_SCRIPT%" --config-file "%AGY_CLI_MCP_CONFIG%" --command "%_MCP_CMD%" --arg "%_MCP_ARG%" --with-env
    if !ERRORLEVEL! equ 0 (echo          [OK] %AGY_CLI_MCP_CONFIG%) else (echo          [Error] Failed)
    echo.
)

:: ---- Claude Desktop ----
if %DO_CLAUDE%==1 (
    echo  [Platform] Claude Desktop
    if not exist "%CLAUDE_CONFIG_DIR%" (
        echo          [--] %CLAUDE_CONFIG_DIR% not found. Skipping.
    ) else (
        "%VENV_PYTHON%" "%PY_SCRIPT%" --config-file "%CLAUDE_MCP_CONFIG%" --command "%_MCP_CMD%" --arg "%_MCP_ARG%"
        if !ERRORLEVEL! equ 0 (echo          [OK] %CLAUDE_MCP_CONFIG%) else (echo          [Error] Failed)
    )
    echo.
)


echo  =========================================================
echo   Installation Complete!
echo  =========================================================
echo.
echo   Python : %VENV_PYTHON%
echo   Server : %SERVER_SCRIPT%
echo.
echo  =========================================================
pause