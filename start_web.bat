@echo off
cd /d "%~dp0"
start "KOL Email Finder" http://127.0.0.1:8010
python web_app.py
pause
