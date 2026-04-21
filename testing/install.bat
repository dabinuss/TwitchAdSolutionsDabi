@echo off
echo ============================================
echo   Twitch Capture Tool - Installation
echo ============================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [FEHLER] Python nicht gefunden.
    echo Bitte von https://python.org installieren ^(Haken bei "Add to PATH"^).
    pause
    exit /b 1
)

echo [+] Python gefunden:
python --version
echo.

echo [+] Installiere Playwright...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [FEHLER] pip install fehlgeschlagen.
    pause
    exit /b 1
)

echo.
echo [+] Installiere Chromium Browser...
python -m playwright install chromium
if errorlevel 1 (
    echo [FEHLER] playwright install fehlgeschlagen.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Installation abgeschlossen!
echo   Weiter mit: run.bat [channel] [sekunden]
echo ============================================
pause
