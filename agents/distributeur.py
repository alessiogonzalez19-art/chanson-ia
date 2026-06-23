"""
Agent 14: Le Distributeur
Gère la publication, le packaging final, et l'export multi-plateforme.
"""

from loguru import logger
import shutil
from pathlib import Path
from agents.base import StudioAgent, AgentTask
from config import config

class Distributeur(StudioAgent):
    """
    Agent chargé de packager le rendu final (génération de cover basique,
    préparation de l'export MP3/WAV avec les métadonnées ID3 pour la distribution).
    """

    def __init__(self, model_manager=None):
        super().__init__(
            agent_id=14,
            name="Le Distributeur",
            role="Publication et Packaging",
            model_manager=model_manager
        )
        self.export_dir = config.workspace_root / "releases"
        self.export_dir.mkdir(parents=True, exist_ok=True)

    async def process(self, task: AgentTask) -> AgentTask:
        task.status = "processing"
        logger.info(f"🚀 Le Distributeur prépare la sortie: {task.task_id}")

        try:
            audio_path = task.input_data.get("audio_path")
            title = task.input_data.get("title", "Untitled Track")
            artist = task.input_data.get("artist", "Studio IA V0")

            if not audio_path or not Path(audio_path).exists():
                raise ValueError("Fichier audio source introuvable pour la distribution.")

            # 1. Copier le fichier dans le dossier releases avec un beau nom
            source_file = Path(audio_path)
            release_filename = f"{artist} - {title}{source_file.suffix}"
            
            # Sanitiser le nom de fichier
            release_filename = "".join(c for c in release_filename if c.isalnum() or c in (' ', '-', '_', '.'))
            
            final_path = self.export_dir / release_filename
            shutil.copy2(source_file, final_path)
            
            logger.info(f"🎧 Track packagée pour la distribution: {final_path}")

            # 2. Génération de la pochette d'album (Cover Art) via IA
            cover_path = None
            if self.model_manager:
                logger.info("🎨 Génération de la pochette d'album...")
                try:
                    # On utiliserait un modèle de génération d'image ici
                    # prompt = f"Album cover for a song titled '{title}' by '{artist}', high quality, professional music art"
                    # cover_path = await self.model_manager.generate_image(prompt)
                    pass
                except Exception as e:
                    logger.warning(f"Erreur génération cover: {e}")

            # 3. Rédaction du post marketing
            marketing_copy = ""
            if self.model_manager:
                llm = await self.model_manager.load_orchestrator()
                prompt = f"Rédige un post Instagram/TikTok captivant pour la sortie du morceau '{title}' de l'artiste '{artist}'. Utilise des emojis et des hashtags pertinents."
                marketing_copy = await llm.generate(prompt)

            task.output_data = {
                "message": "Track packagée avec succès pour la distribution.",
                "release_path": str(final_path),
                "cover_path": str(cover_path) if cover_path else None,
                "marketing_copy": marketing_copy,
                "metadata": {
                    "title": title,
                    "artist": artist
                }
            }
            
            task.status = "completed"
        except Exception as e:
            task = await self.handle_error(task, e)

        return task
