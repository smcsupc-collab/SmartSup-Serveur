@echo off
title SmartSup — Incidents
cd /d "%~dp0"
echo.
echo  SmartSup - Demarrage en cours...
echo  Le navigateur s'ouvrira automatiquement dans quelques secondes.
echo  Acces depuis ce PC : http://127.0.0.1:5000
echo  Acces depuis le reseau local : http://[IP_DE_CE_PC]:5000
echo.
if exist ".venv\Scripts\python.exe" (
	".venv\Scripts\python.exe" app.py
) else (
	python app.py
)
pause
