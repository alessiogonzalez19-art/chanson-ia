@echo off
:: ╔══════════════════════════════════════════════════════╗
:: ║     Studio IA — Lanceur Windows (.bat)               ║
:: ║     Double-cliquez sur ce fichier pour démarrer      ║
:: ╚══════════════════════════════════════════════════════╝

title Studio IA — Launcher

echo.
echo  ============================================
echo   Studio IA — Local AI Music Production
echo  ============================================
echo.

:: Force l'utilisation de Python 3.11 (installé automatiquement)
set PYTHON_CMD="C:\Users\moi\AppData\Local\Programs\Python\Python311\python.exe"

if not exist %PYTHON_CMD% (
    echo [ERREUR CRITIQUE] Python 3.11 n'a pas ete trouve a l'emplacement attendu.
    pause
    exit /b 1
)

:: Vérification stricte de la version (3.10, 3.11 ou 3.12)
%PYTHON_CMD% -c "import sys; sys.exit(0 if sys.version_info[:2] in [(3,10), (3,11), (3,12)] else 1)"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERREUR CRITIQUE] Version de Python incompatible !
    echo L'Intelligence Artificielle ^(PyTorch^) ne supporte pas encore Python 3.13 ou 3.14.
    echo Vous utilisez une version trop recente qui bloque l'installation.
    echo.
    echo Veuillez DESINSTALLER Python depuis vos parametres Windows,
    echo puis installer Python 3.11 depuis ce lien :
    echo https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
    echo.
    echo ^(N'oubliez pas de cocher "Add Python.exe to PATH" !^)
    echo.
    pause
    exit /b 1
)

:: 1. Création de l'environnement virtuel
if not exist "venv\Scripts\activate.bat" (
    echo [INFO] Creation de l'environnement virtuel avec Python 3.11...
    %PYTHON_CMD% -m venv venv
)

:: 2. Activation de l'environnement virtuel
call venv\Scripts\activate.bat

:: 3. Installation des dependances si necessaire
python -c "import transformers, demucs" >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [INFO] Premiere execution detectee avec le nouvel environnement.
    echo [INFO] Installation des dependances... (Cela peut prendre quelques minutes)
    python -m pip install --upgrade pip -q
    
    echo [INFO] Installation de PyTorch...
    python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121 -q
    
    echo [INFO] Installation des outils de compilation...
    python -m pip install setuptools wheel importlib_resources numpy cython -q
    
    echo [INFO] Installation de Whisper (contournement du bug Python 3.11+)...
    python -m pip install openai-whisper==20240930 --no-build-isolation -q
    
    echo [INFO] Installation des autres modules...
    python -m pip install -r requirements.txt -q
    python -m pip install rich loguru -q
    echo [INFO] Installation terminee !
    echo.
)

:: 4. Lance le launcher interactif
echo  Demarrage du launcher...
echo.
python launcher.py

pause
