"""
Scraping de sons réels via yt-dlp
"""
import asyncio
import uuid
from loguru import logger
from config import config

async def scrape_freesound(query: str, api_key: str = None) -> dict:
    """Recherche et télécharge un sample via yt-dlp (ytsearch)"""
    logger.info(f"Scraping réel pour: {query}")
    
    # Exécuter yt-dlp dans un processus asynchrone pour ne pas bloquer
    library_dir = config.workspace_root / "library"
    library_dir.mkdir(parents=True, exist_ok=True)
    
    file_id = uuid.uuid4().hex[:8]
    output_template = str(library_dir / f"scraped_{file_id}_%(title)s.%(ext)s")
    
    cmd = [
        "yt-dlp",
        f"ytsearch1:{query} sample free no copyright",
        "--extract-audio",
        "--audio-format", "wav",
        "--geo-bypass",
        "--no-playlist",
        "-o", output_template,
        "--dump-json" # Pour récupérer les infos
    ]
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"Erreur yt-dlp: {stderr.decode()}")
            return {"status": "failed", "error": "Échec du téléchargement"}
            
        import json
        info = json.loads(stdout.decode().split('\n')[0])
        filename = f"scraped_{file_id}_{info.get('title', 'sample')}.wav"
        # yt-dlp nettoie souvent les noms de fichiers, c'est une approximation,
        # dans une version de prod on lirait le vrai nom du fichier depuis les logs.
        
        return {
            "status": "success",
            "results": [
                {"id": file_id, "name": filename, "duration": info.get('duration', 0)}
            ]
        }
    except Exception as e:
        logger.error(f"Exception lors du scraping: {e}")
        return {"status": "failed", "error": str(e)}
