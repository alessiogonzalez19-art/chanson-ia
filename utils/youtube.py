"""
utils/youtube.py
────────────────
Téléchargement YouTube via yt-dlp avec ffmpeg automatiquement détecté.

Priorité ffmpeg :
1. imageio_ffmpeg (bundled dans le venv, toujours disponible)
2. ffmpeg système (PATH)
"""

import os
import time
from pathlib import Path
from loguru import logger
from config import config
import yt_dlp

class YouTubeAuthRequired(RuntimeError):
    pass

class YouTubeBlocked(RuntimeError):
    pass


def _resolve_cookie_file() -> Path | None:
    """Return the optional cookie file configured by the user."""
    configured = os.getenv("YOUTUBE_COOKIES_FILE", "").strip()
    if not configured:
        return None

    cookie_file = Path(configured).expanduser().resolve()
    if not cookie_file.exists():
        logger.warning(f"⚠️ Fichier de cookies introuvable : {cookie_file}")
        return None

    return cookie_file


def _get_ffmpeg_path() -> str:
    """
    Retourne le chemin vers ffmpeg.exe (yt-dlp prendra le parent pour ffprobe).
    
    Priorité :
    1. ffmpeg système (PATH) — vérifie que ffprobe existe aussi
    2. imageio_ffmpeg — fallback limité
    """
    import shutil
    import subprocess

    # 1. Cherche ffmpeg dans le PATH Windows
    try:
        result = subprocess.run(
            ["where.exe", "ffmpeg"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            # where.exe peut retourner plusieurs lignes, on prend la première
            sys_ffmpeg = result.stdout.strip().split('\n')[0].strip()
            if sys_ffmpeg and Path(sys_ffmpeg).exists():
                # Vérifie que ffprobe est dans le même dossier
                ffprobe_path = Path(sys_ffmpeg).parent / "ffprobe.exe"
                if ffprobe_path.exists():
                    logger.debug(f"✅ ffmpeg système trouvé : {sys_ffmpeg}")
                    logger.debug(f"✅ ffprobe trouvé : {ffprobe_path}")
                    return sys_ffmpeg
                else:
                    logger.warning(f"⚠️ ffprobe manquant dans {Path(sys_ffmpeg).parent}")
    except Exception as e:
        logger.debug(f"where.exe ffmpeg échoué : {e}")

    # 2. Fallback: imageio_ffmpeg (pas de ffprobe, limité)
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).exists():
            logger.warning(
                "⚠️ imageio_ffmpeg utilisé (sans ffprobe) — "
                "la conversion peut échouer. "
                "Installez ffmpeg complet : winget install Gyan.FFmpeg"
            )
            return exe
    except Exception:
        pass

    raise RuntimeError(
        "❌ ffmpeg introuvable ! Installez-le : winget install Gyan.FFmpeg\n"
        "Puis redémarrez le studio."
    )


class YouTubeDownloader:

    def __init__(self):
        base = config.temp_folder
        base.mkdir(parents=True, exist_ok=True)
        self.output_dir = base / "youtube_downloads"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ffmpeg_path = _get_ffmpeg_path()
        self.cookie_file = _resolve_cookie_file()
        logger.info(f"✅ Dossier temporaire YouTube : {self.output_dir}")

    def _build_opts(self, outtmpl: str, browser: str | None = None) -> dict:
        """Construit les options yt-dlp communes avec formats audio flexibles."""
        opts = {
            # Format audio le plus simple : laisse yt-dlp choisir automatiquement
            # bestaudio = meilleur flux audio disponible (peu importe le format)
            # worst = fallback absolu si rien d'autre ne marche
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "ffmpeg_location": str(Path(self.ffmpeg_path).parent),
            "extract_audio": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "wav",
                    "preferredquality": "192",
                    "nopostoverwrites": False,
                }
            ],
            "quiet": False,  # Active les logs pour debug
            "no_warnings": False,
            "retries": 3,
            "fragment_retries": 3,
            # Anti rate-limit : pause aléatoire entre les requêtes
            "sleep_interval": 1,
            "max_sleep_interval": 3,
            "sleep_interval_requests": 1,
            # Timeout socket pour éviter les blocages
            "socket_timeout": 30,
            # ⚠️ CRITIQUE : Ne télécharge QUE la vidéo, pas toute la playlist !
            "noplaylist": True,
            # Ignore les avertissements de cookies expirés
            "ignoreerrors": False,
            # Pour les vidéos YouTube Music ou premium, et contourner certaines restrictions
            "extractor_args": {
                "youtube": {
                    "player_client": ["tv", "mweb", "android", "web", "ios"],
                    "skip": ["hls", "dash"],
                }
            },
            # Préfère les formats libres (sans DRM)
            "prefer_free_formats": True,
            # Utilise l'API mobile et divers bypass pour geo/age
            "geo_bypass": True,
            "geo_bypass_country": "US",
            "nocheckcertificate": True
        }

        if self.cookie_file is not None:
            opts["cookiefile"] = str(self.cookie_file)
            logger.debug(f"🍪 Cookies YouTube chargés depuis fichier : {self.cookie_file}")
        elif browser:
            opts["cookiesfrombrowser"] = (browser,)
            logger.debug(f"🍪 Cookies extraits automatiquement depuis {browser.capitalize()}")

        return opts

    def download_audio(self, url: str, timeout_seconds: int = 180) -> str:
        """
        Télécharge l'audio YouTube et le convertit en WAV.
        
        Args:
            url: URL YouTube ou ytsearch query
            timeout_seconds: Timeout max pour le téléchargement (défaut 3 min)
        """
        # Nettoie l'URL pour extraire seulement le video ID (ignore playlist, etc.)
        if "youtube.com" in url or "youtu.be" in url:
            # Extrait le video ID depuis l'URL
            import re
            match = re.search(r'(?:v=|/)([0-9A-Za-z_-]{11})', url)
            if match:
                video_id = match.group(1)
                url = f"https://www.youtube.com/watch?v={video_id}"
                logger.debug(f"🔗 URL nettoyée : {url}")
        
        logger.info(f"📥 Téléchargement YouTube : {url}")

        outtmpl = str(self.output_dir / "%(id)s.%(ext)s")
        browser_sources = [None] if self.cookie_file is not None else ["firefox", "chrome", "edge", "brave", "opera", "vivaldi", None]
        last_error = None
        start_ts = time.time()

        for browser in browser_sources:
            opts = self._build_opts(outtmpl, browser=browser)
            opts["socket_timeout"] = 30
            try:
                if browser:
                    logger.info(f"🍪 Tentative YouTube avec cookies {browser.capitalize()}")
                else:
                    logger.info("🍪 Tentative YouTube sans cookies navigateur")

                with yt_dlp.YoutubeDL(opts) as ydl:
                    logger.debug(f"⏱️ Timeout configuré : {timeout_seconds}s")
                    info = ydl.extract_info(url, download=True)
                    video_id = info.get("id", "")

                    elapsed = time.time() - start_ts
                    logger.info(f"⏱️ Téléchargement terminé en {elapsed:.1f}s")

                wav_path = self.output_dir / f"{video_id}.wav"
                if wav_path.exists():
                    logger.info(f"✅ Audio téléchargé : {wav_path}")
                    return str(wav_path)

                for f in sorted(self.output_dir.glob("*.wav"),
                                key=lambda p: p.stat().st_mtime, reverse=True):
                    if f.stat().st_mtime >= start_ts - 5:
                        logger.info(f"✅ Audio trouvé : {f}")
                        return str(f)

                raise FileNotFoundError(
                    f"Fichier WAV introuvable après téléchargement (id={video_id})"
                )

            except yt_dlp.utils.DownloadError as e:
                last_error = e
                message = str(e)
                lowered = message.lower()
                
                # Check for bot block, age gates, or geo-restrictions
                is_blocked = any(kw in lowered for kw in [
                    "sign in to confirm", 
                    "age-restricted", 
                    "sign in to verify", 
                    "bot", 
                    "unavailable",
                    "whoops, something went wrong",
                    "private video",
                    "geo-restricted"
                ])
                
                if is_blocked:
                    logger.warning(f"⚠️ Blocage YouTube (geo/age/bot) avec source cookies={browser or 'aucune'}: {message}")
                    continue
                raise
            except Exception as e:
                last_error = e
                if browser in {"firefox", "chrome", "edge"}:
                    logger.warning(f"⚠️ Echec avec cookies {browser.capitalize()} : {e}")
                    continue
                raise

        elapsed = time.time() - start_ts
        if last_error is not None:
            message = str(last_error)
            lowered = message.lower()
            if any(kw in lowered for kw in ["sign in to confirm", "age-restricted", "bot"]):
                logger.error(f"❌ Erreur YouTube Auth/Age après {elapsed:.1f}s : {last_error}")
                raise YouTubeAuthRequired(message) from last_error
            elif "unavailable" in lowered:
                logger.error(f"❌ Erreur YouTube (Vidéo indisponible) : {last_error}")
                raise YouTubeBlocked(message) from last_error
            logger.error(f"❌ Erreur YouTube après {elapsed:.1f}s : {last_error}")
            raise last_error

        raise RuntimeError("Téléchargement YouTube impossible sans détail exploitable.")

    def auto_search_and_download(self, query: str) -> str:
        """Recherche YouTube et télécharge le premier résultat."""
        logger.info(f"🔎 Recherche YouTube : {query}")
        search_url = f"ytsearch1:{query} sample loop audio"
        return self.download_audio(search_url)
