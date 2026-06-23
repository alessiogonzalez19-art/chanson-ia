"""
Agent 12: Le Compositeur Autonome
Génération de musiques instrumentales et scraping de samples pour la bibliothèque.
"""

import asyncio
import uuid
from pathlib import Path
from typing import Dict, Any, Optional
from loguru import logger

from agents.base import StudioAgent, AgentTask
from config import config

class CompositeurAutonome(StudioAgent):
    """
    Agent dédié à la création d'instrus pures et au remplissage de la bibliothèque.
    """

    def __init__(self, model_manager=None):
        super().__init__(
            agent_id=12,
            name="Le Compositeur Autonome",
            role="Génération d'instrumentales et Scraping",
            model_manager=model_manager
        )
        self.library_dir = config.workspace_root / "library"
        self.library_dir.mkdir(parents=True, exist_ok=True)

    async def process(self, task: AgentTask) -> AgentTask:
        task.status = "processing"
        logger.info(f"🎹 Compositeur Autonome en action: {task.task_id}")

        try:
            action = task.input_data.get("action", "generate")
            
            if action == "generate":
                prompt = task.input_data.get("prompt", "Lo-fi hip hop beat, chill, instrumental")
                duration = task.input_data.get("duration", 30)
                result = await self._generate_instrumental(prompt, duration)
                task.output_data = result
            elif action == "scrape":
                query = task.input_data.get("query", "drum loop 120 bpm")
                result = await self._scrape_samples(query)
                task.output_data = result
            else:
                task.output_data = {"error": f"Action inconnue: {action}"}
                
            task.status = "completed"
        except Exception as e:
            task = await self.handle_error(task, e)

        return task

    async def _generate_instrumental(self, prompt: str, duration: int) -> Dict:
        """Génère un audio via le Music Generator et le sauvegarde dans la bibliothèque."""
        logger.info(f"Génération auto: {prompt}")
        if not self.model_manager:
            return {"error": "Model Manager non disponible."}

        generator = await self.model_manager.load_music_generator()
        audio_array = await generator.generate(prompt, duration)
        
        file_name = f"gen_instru_{uuid.uuid4().hex[:8]}.wav"
        output_path = self.library_dir / file_name
        
        await generator.save_audio(audio_array, output_path)
        
        return {
            "status": "success",
            "source": "generated",
            "prompt": prompt,
            "duration": duration,
            "path": str(output_path),
            "url": f"/api/library/stream/{file_name}"
        }

    async def _scrape_samples(self, query: str) -> Dict:
        """Simulation du scraping de samples."""
        logger.info(f"Recherche de samples: {query}")
        # L'implémentation réelle appellera yt-dlp ou freesound API
        return {
            "status": "success",
            "source": "scraped",
            "query": query,
            "message": "Scraping non encore implémenté via API."
        }
