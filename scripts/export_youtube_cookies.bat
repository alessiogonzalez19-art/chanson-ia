@echo off
:: ╔══════════════════════════════════════════════════════╗
:: ║  Export des cookies YouTube pour éviter le ban      ║
:: ║  Lance depuis le dossier projet                     ║
:: ╚══════════════════════════════════════════════════════╝

title Export Cookies YouTube

cd /d "%~dp0.."
call venv\Scripts\activate.bat

echo.
echo  Exportation des cookies YouTube depuis Chrome...
echo  (vous devez etre connecte a YouTube dans Chrome)
echo.

yt-dlp --cookies-from-browser chrome --cookies youtube_cookies.txt --skip-download "https://www.youtube.com/watch?v=dQw4w9WgXcQ" 2>&1

if exist youtube_cookies.txt (
    echo.
    echo  [OK] Cookies sauvegardes dans youtube_cookies.txt
    echo  Le studio pourra maintenant telecharger sans se faire bloquer.
) else (
    echo.
    echo  [ERREUR] Essayons avec Firefox...
    yt-dlp --cookies-from-browser firefox --cookies youtube_cookies.txt --skip-download "https://www.youtube.com/watch?v=dQw4w9WgXcQ" 2>&1
    
    if exist youtube_cookies.txt (
        echo  [OK] Cookies Firefox sauvegardes !
    ) else (
        echo  [ECHEC] Essayez Edge :
        echo  yt-dlp --cookies-from-browser edge --cookies youtube_cookies.txt --skip-download "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    )
)

echo.
pause
