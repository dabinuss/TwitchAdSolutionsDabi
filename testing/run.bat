@echo off
echo ============================================
echo   Twitch Capture Tool
echo ============================================
echo.
echo Verwendung:
echo   run.bat              (Standard: esl_csgo, 90s)
echo   run.bat xqc          (Channel xqc, 90s)
echo   run.bat xqc 120      (Channel xqc, 120s)
echo.

set CHANNEL=%1
if "%CHANNEL%"=="" set CHANNEL=esl_csgo

set DURATION=%2
if "%DURATION%"=="" set DURATION=90

echo [+] Starte Capture: Channel=%CHANNEL%  Dauer=%DURATION%s
echo.

python capture.py %CHANNEL% %DURATION%

echo.
echo [+] Fertig. Ergebnisse in: captures\
echo ============================================
pause
