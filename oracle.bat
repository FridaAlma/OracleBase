@echo off
title Oracle - AI Coding Agent
cd /d "%~dp0"

:: ─── Parse arguments ───────────────────────────────────────────
set MODE=ui
set PORT=8000
set MODEL_FLAG=

:parse
if "%~1"=="--cli" set MODE=cli& shift & goto parse
if "%~1"=="--ui" set MODE=ui& shift & goto parse
if "%~1"=="--port" set PORT=%~2& shift & shift & goto parse
if "%~1"=="--deep" set MODEL_FLAG=--deep& shift & goto parse
if "%~1"=="--pro" set MODEL_FLAG=--model-tier pro& shift & goto parse
if "%~1"=="--flash" set MODEL_FLAG=--model-tier flash& shift & goto parse
if "%~1"=="--help" goto help

:: ─── Check Python ──────────────────────────────────────────────
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERRORE] Python non trovato. Assicurati di aver installato Python e che sia nel PATH.
    echo         Scarica Python da: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: ─── Check .env ─────────────────────────────────────────────────
if not exist ".env" (
    echo [AVVISO] File .env non trovato.
    echo          Copia .env.example in .env e configura la tua API key.
    echo.
    choice /c CN /N /M "[C]ontinua comunque o [N]on uscire? (C/N) "
    if errorlevel 2 exit /b 1
)

:: ─── UI Mode (default) ─────────────────────────────────────────
if "%MODE%"=="ui" goto ui_mode

:: ─── CLI Mode ───────────────────────────────────────────────────
:cli_mode
echo.
echo  ^|  Oracle CLI - AI Coding Agent
if "%MODEL_FLAG%"=="--deep" echo  ^|  Modalita' PRO (DeepSeek V4 Pro)
echo  ^|  Scrivi 'exit' o premi Ctrl+C per uscire
echo.
python cli.py %MODEL_FLAG%

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERRORE] Oracle si e' chiuso con codice %ERRORLEVEL%
    pause
)
exit /b %ERRORLEVEL%

:: ─── UI Mode ────────────────────────────────────────────────────
:ui_mode
echo.
echo  ^|  Oracle - AI Coding Agent
if "%MODEL_FLAG%"=="--deep" echo  ^|  Modalita' PRO (DeepSeek V4 Pro)
echo  ^|  Server in avvio su http://localhost:%PORT%
echo  ^|  Premi Ctrl+C per fermare tutto
echo.

:: Installa dipendenze mancanti per il modulo chat (solo primo avvio)
pip install httpx fastapi uvicorn python-multipart -q 2>nul

:: Avvia il server in una nuova finestra minimizzata
start "Oracle Server" /MIN cmd /c "cd /d "%~dp0" && python coding_agent.py --port %PORT% %MODEL_FLAG%"

:: Aspetta che il server sia pronto
echo Attendendo l'avvio del server...
:waitloop
timeout /t 2 /nobreak >nul
python -c "import urllib.request; urllib.request.urlopen('http://localhost:%PORT%/health')" >nul 2>&1
if errorlevel 1 (
    echo . Server non ancora pronto, aspetto...
    goto waitloop
)

:: Apri il browser
echo Server pronto! Apro il browser...
start http://localhost:%PORT%/ui

echo.
echo  ┌─────────────────────────────────────────────────────────────┐
echo  │  Oracle e' in esecuzione su http://localhost:%PORT%/ui          │
if "%MODEL_FLAG%"=="--deep" echo  │  MODALITA' PRO ATTIVA                                           │
echo  │  Premi Ctrl+C per fermare tutto...                         │
echo  └─────────────────────────────────────────────────────────────┘
echo.

:: Attendere Ctrl+C con Python (gestisce correttamente i segnali
:: senza il fastidioso prompt "Terminate batch job (Y/N)" di cmd.exe)
python -c "import time, itertools; any(time.sleep(1) for _ in itertools.repeat(0))" >nul 2>&1

:: ─── Cleanup ─────────────────────────────────────────────────────
echo.
echo Arresto in corso...

:: Chiude le schede del browser aperte su localhost:%PORT%
echo Chiusura interfaccia web...
powershell -NoProfile -Command "try { $w = (New-Object -ComObject Shell.Application).Windows(); $w | Where-Object { $_.LocationURL -like '*localhost:%PORT%*' } | ForEach-Object { $_.Quit(); Start-Sleep -Milliseconds 100 } } catch {}" >nul 2>&1

:: Ferma il server
echo Fermo il server...
taskkill /f /fi "WINDOWTITLE eq Oracle Server" >nul 2>&1
echo Server arrestato.

exit /b 0

:: ─── Help ───────────────────────────────────────────────────────
:help
echo Oracle - AI Coding Agent
echo.
echo Utilizzo:  oracle.bat [opzioni]
echo.
echo Opzioni:
echo   --cli          Avvia l'interfaccia a riga di comando (CLI)
echo   --ui           Avvia l'interfaccia web (default)
echo   --deep, --pro  Usa DeepSeek V4 Pro (massima qualita')
echo   --flash        Usa DeepSeek V4 Flash (economico, default)
echo   --port PORT    Usa una porta specifica (default: 8000)
echo   --help         Mostra questo messaggio
echo.
echo Esempi:
echo   oracle.bat                  Avvia interfaccia web (Auto mode)
echo   oracle.bat --deep           Avvia con DeepSeek V4 Pro
echo   oracle.bat --cli --deep     Avvia CLI con DeepSeek V4 Pro
echo   oracle.bat --port 8080      Avvia su porta 8080
echo.
pause
exit /b 0