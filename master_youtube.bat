@echo off
REM Mastering rapide pour YouTube
REM Usage: Glissez-déposez un fichier WAV/MP3 sur ce .bat

setlocal EnableDelayedExpansion

if "%~1"=="" (
    echo.
    echo ════════════════════════════════════════════════
    echo   🎬 MASTERING YOUTUBE - Studio IA
    echo ════════════════════════════════════════════════
    echo.
    echo Usage: Glissez-déposez un fichier audio sur ce .bat
    echo.
    echo Options:
    echo   1. Standard    : Mastering professionnel classique
    echo   2. Creative    : Mastering avec boost vocal et elargissement stereo
    echo.
    pause
    exit /b
)

set "INPUT_FILE=%~1"
set "FILE_EXT=%~x1"

echo.
echo ════════════════════════════════════════════════
echo   🎬 MASTERING YOUTUBE - Studio IA
echo ════════════════════════════════════════════════
echo.
echo Fichier: %~nx1
echo.

REM Choix du mode
choice /C SC /N /M "Choisissez [S]tandard ou [C]reatif : "
if errorlevel 2 (
    set "MODE=--creative"
    echo Mode: Creative ^(boost vocal + stereo widening^)
) else (
    set "MODE="
    echo Mode: Standard ^(mastering professionnel^)
)

echo.
echo ⏳ Traitement en cours...
echo.

REM Lance le mastering
python311.exe -m utils.youtube_mastering "%INPUT_FILE%" %MODE%

if errorlevel 1 (
    echo.
    echo ❌ Erreur lors du mastering
    pause
    exit /b 1
)

echo.
echo ✅ Mastering termine !
echo.
echo 📁 Le fichier masterise se trouve dans le meme dossier
echo    avec le suffixe _MASTERED_YT.wav
echo.
echo Standards YouTube appliques:
echo   • LUFS: -14.0 dB
echo   • True Peak: -1.0 dB
echo   • De-esser + reduction de bruit
echo   • Limiteur final sans distorsion
echo.
pause
