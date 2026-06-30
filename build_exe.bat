@echo off
title MedDeck - Construction de l'executable
color 0B
echo.
echo  Construction de MedDeck.exe (executable autonome)...
echo.
cd /d %~dp0
pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --onefile --name MedDeck --add-data "MedDeck_v2_Terrain.html;." --collect-all waitress run.py
echo.
echo  Termine. L'executable se trouve dans :  dist\MedDeck.exe
echo.
pause
