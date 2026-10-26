@echo off
rem ---------------------------------------------------------------------------
rem  Remise a zero de l'application de paie (suppression de la demonstration).
rem  Une sauvegarde verifiee est creee avant toute modification ; l'ancienne base
rem  est conservee dans le dossier des sauvegardes (data\backups par defaut).
rem
rem  Prerequis : fermer l'application (fenetre Streamlit) et activer
rem  l'environnement Python, par exemple :
rem      C:\python3.10\py310_env\Scripts\activate.bat
rem ---------------------------------------------------------------------------
setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python est introuvable. Activez d'abord l'environnement, par exemple :
    echo     C:\python3.10\py310_env\Scripts\activate.bat
    goto fin
)

python scripts\reset_production.py %*
if errorlevel 2 echo. & echo La remise a zero a ete interrompue : aucune donnee n'a ete modifiee.

:fin
echo.
pause
endlocal
