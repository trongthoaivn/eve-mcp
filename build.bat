@echo off
setlocal enabledelayedexpansion

echo.
echo  =========================================================
echo   EVE-MCP Server  ^|  Build Script  (source + venv)
echo   Sets up .venv and installs dependencies
echo  =========================================================
echo.

:: ================================================================
:: CONFIGURATION
:: ================================================================
set PROJECT_DIR=%~dp0
if "%PROJECT_DIR:~-1%"=="\" set PROJECT_DIR=%PROJECT_DIR:~0,-1%

set BUILD_DIR=%PROJECT_DIR%\build
set VENV_PYTHON=%BUILD_DIR%\.venv\Scripts\python.exe
set VENV_PIP=%BUILD_DIR%\.venv\Scripts\pip.exe


:: ================================================================
:: STEP 1: Create virtual environment and copy source
:: ================================================================
echo [Step 1/2] Setting up build directory and virtual environment...

if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%"

echo          Copying source files to build directory...
if exist "%PROJECT_DIR%\controllers" xcopy /E /I /Y /R /Q "%PROJECT_DIR%\controllers" "%BUILD_DIR%\controllers" >nul
if exist "%PROJECT_DIR%\services" xcopy /E /I /Y /R /Q "%PROJECT_DIR%\services" "%BUILD_DIR%\services" >nul
if exist "%PROJECT_DIR%\utilities" xcopy /E /I /Y /R /Q "%PROJECT_DIR%\utilities" "%BUILD_DIR%\utilities" >nul
if exist "%PROJECT_DIR%\skills" xcopy /E /I /Y /R /Q "%PROJECT_DIR%\skills" "%BUILD_DIR%\skills" >nul
copy /Y "%PROJECT_DIR%\server.py" "%BUILD_DIR%\" >nul
copy /Y "%PROJECT_DIR%\configure_mcp.py" "%BUILD_DIR%\" >nul
copy /Y "%PROJECT_DIR%\requirements.txt" "%BUILD_DIR%\" >nul
if exist "%PROJECT_DIR%\.env" copy /Y "%PROJECT_DIR%\.env" "%BUILD_DIR%\" >nul

python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [Error] Python not found. Install Python 3.10+ and add to PATH.
    pause & exit /b 1
)

if not exist "%VENV_PYTHON%" (
    echo          Creating .venv ...
    if exist "%BUILD_DIR%\.venv\" rmdir /S /Q "%BUILD_DIR%\.venv"
    python -m venv "%BUILD_DIR%\.venv"
    if %ERRORLEVEL% neq 0 (
        echo [Error] Failed to create virtual environment.
        pause & exit /b 1
    )
) else (
    echo          .venv already exists, skipping creation.
)

echo [OK] Virtual environment ready.
echo.


:: ================================================================
:: STEP 2: Install dependencies
:: ================================================================
echo [Step 2/2] Installing dependencies...

"%VENV_PYTHON%" -m pip install --upgrade pip --quiet

echo          Installing eve-ng (ignoring dependency conflicts)...
"%VENV_PYTHON%" -m pip install eve-ng==0.2.7 --no-deps --quiet
if %ERRORLEVEL% neq 0 (
    echo [Error] pip install failed for eve-ng.
    pause & exit /b 1
)

echo          Installing other requirements and resolving dependencies...
"%VENV_PYTHON%" -m pip install fastmcp==3.4.2 httpx==0.28.1 python-dotenv==1.2.2 netmiko==4.4.0 requests "Jinja2<3.1.0" --quiet
if %ERRORLEVEL% neq 0 (
    echo [Error] pip install failed.
    pause & exit /b 1
)

echo [OK] Dependencies installed.
echo.

echo  =========================================================
echo   Build completed!
echo.
echo   Python : %VENV_PYTHON%
echo   Server : %BUILD_DIR%\server.py
echo.
echo   Run install.bat to configure agent platforms.
echo  =========================================================
pause