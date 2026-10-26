@echo off
rem ---------------------------------------------------------------------------
rem  Suppression du seul salarie de demonstration (0001 EXEMPLE).
rem  La societe et les salaries reels, avec leurs paies, sont conserves.
rem  Une sauvegarde verifiee est creee avant toute modification.
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

python scripts\supprimer_demo.py %*
if errorlevel 2 echo. & echo Operation interrompue : aucune donnee n'a ete modifiee.

:fin
echo.
pause
endlocal
