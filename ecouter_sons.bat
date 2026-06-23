@echo off
echo.
echo ════════════════════════════════════════════════
echo   🎵 ÉCOUTE TES SONS - Studio IA
echo ════════════════════════════════════════════════
echo.
echo Recherche des fichiers audio...
echo.

REM Cherche dans temp_processing
set FOUND=0

echo 📁 Fichiers dans temp_processing:
echo.

for /r "temp_processing" %%f in (*.wav) do (
    echo %%~nxf
    set FOUND=1
)

echo.
echo ────────────────────────────────────────────────
echo.

if %FOUND%==0 (
    echo ❌ Aucun fichier audio trouvé dans temp_processing
    echo.
    echo Tu dois d'abord lancer un remix !
    echo.
    pause
    exit /b
)

echo Choisis quel type de fichier écouter:
echo.
echo 1. Voix traitées (vocals_studio.wav)
echo 2. Stems séparés (bass, drums, vocals, other)
echo 3. Ouvrir le dossier dans l'explorateur
echo 4. Tout ouvrir
echo.

choice /C 1234 /N /M "Ton choix (1-4): "

if errorlevel 4 goto OUVRIR_TOUT
if errorlevel 3 goto OUVRIR_DOSSIER
if errorlevel 2 goto OUVRIR_STEMS
if errorlevel 1 goto OUVRIR_VOCALS

:OUVRIR_VOCALS
echo.
echo 🎤 Ouverture des voix traitées...
for /r "temp_processing" %%f in (vocals_studio.wav) do (
    start "" "%%f"
)
goto FIN

:OUVRIR_STEMS
echo.
echo 🎸 Ouverture des stems...
for /r "temp_processing\stems_orig*" %%f in (*.wav) do (
    start "" "%%f"
)
goto FIN

:OUVRIR_DOSSIER
echo.
echo 📁 Ouverture de l'explorateur...
start "" "temp_processing"
goto FIN

:OUVRIR_TOUT
echo.
echo 🎵 Ouverture de tous les fichiers audio...
for /r "temp_processing" %%f in (*.wav) do (
    start "" "%%f"
    timeout /t 1 /nobreak >nul
)
goto FIN

:FIN
echo.
echo ✅ Fichiers ouverts dans ton lecteur par défaut !
echo.
pause
