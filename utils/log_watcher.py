"""
Watch logs en temps réel pour l'Agent 11 Gardien.
"""
import os
import time
import asyncio
from typing import Callable
from pathlib import Path
from loguru import logger

class LogWatcher:
    def __init__(self, log_dir: str):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._is_watching = False

    async def watch_logs(self, callback: Callable[[str, str], None]):
        """
        Surveille le dernier fichier de log pour des mots-clés d'erreur.
        Appelle callback(error_text, file_path) si erreur.
        """
        self._is_watching = True
        logger.info(f"👀 LogWatcher démarré sur {self.log_dir}")
        
        # Simule une écoute continue (idéalement via watchdog ou tail -f)
        while self._is_watching:
            # Simulation d'un check régulier
            await asyncio.sleep(5)
            # Implémentation réelle : lire le fichier log ligne par ligne et chercher 'ERROR' ou 'Exception'

    def stop(self):
        self._is_watching = False
