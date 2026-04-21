@echo off
echo ============================================
echo   Twitch Capture Tool
echo ============================================
echo.
echo Verwendung:
echo   run.bat              (Auto: findet live DE-Channel, 90s)
echo   run.bat xqc          (Channel xqc, 90s)
echo   run.bat xqc 120      (Channel xqc, 120s)
echo   run.bat --hunt       (Preroll-Hunt: testet mehrere Channels bis Ad gefunden)
echo   run.bat --hunt 45    (Preroll-Hunt mit 45s pro Channel)
echo.

if "%1"=="--hunt" (
    set DURATION=%2
    if "%DURATION%"=="" set DURATION=45
    echo [+] PREROLL-HUNT Modus: %DURATION%s pro Channel
    echo.
    python capture.py --hunt %DURATION%
) else (
    set CHANNEL=%1
    set DURATION=%2
    if "%DURATION%"=="" set DURATION=90

    if "%CHANNEL%"=="" (
        echo [+] Kein Channel angegeben - suche live DE-Channel
        python capture.py
    ) else (
        echo [+] Starte Capture: Channel=%CHANNEL%  Dauer=%DURATION%s
        python capture.py %CHANNEL% %DURATION%
    )
)

echo.
echo [+] Fertig. Ergebnisse in: captures\
echo ============================================
pause
