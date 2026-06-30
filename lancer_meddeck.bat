@echo off
title MedDeck — CHU Mohammed VI
color 0A
echo.
echo  ╔══════════════════════════════════════╗
echo  ║     MedDeck v2 — CHU Mohammed VI   ║
echo  ║     Service Biomedical (SEBM)        ║
echo  ╚══════════════════════════════════════╝
echo.

:: Récupérer l'IP Wi-Fi locale
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4" ^| findstr /v "169.254" ^| findstr /v "172."') do (
  set LOCAL_IP=%%a
)
set LOCAL_IP=%LOCAL_IP: =%

if exist "C:\Users\Home\meddeck\instance\certs\cert.pem" (set PROTO=https) else (set PROTO=http)
echo  Acces sur ce PC      : %PROTO%://localhost:5000
echo  Acces telephone/tablette : %PROTO%://%LOCAL_IP%:5000
if "%PROTO%"=="https" echo  Scan camera en direct : ACTIVE ^(HTTPS^)
echo.
echo  Demarrage du serveur...
cd /d C:\Users\Home\meddeck

:: Attendre 2 secondes puis ouvrir le navigateur
ping -n 3 127.0.0.1 > nul
start "" "%PROTO%://localhost:5000"

:: Lancer Flask
python run.py

echo.
echo  Serveur arrete. Appuyez sur une touche pour fermer.
pause > nul
