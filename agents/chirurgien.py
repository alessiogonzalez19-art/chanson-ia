"""
Agent 3: Le Chirurgien
Stem separation and audio surgery using Demucs HT
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
from loguru import logger

from agents.base import StudioAgent, AgentTask


class Chirurgien(StudioAgent):
    """Le Chirurgien — Stem separation specialist"""

    def __init__(self, model_manager=None):
        super().__init__(
            agent_id=3,
            name="Le Chirurgien",
            role="Stem Separation & Audio Surgery",
            model_manager=model_manager
        )
        self.separator = None

    async def initialize(self):
        """Load stem separation model"""
        if self.model_manager:
            self.separator = await self.model_manager.load_separator()
            logger.info("✅ Chirurgien initialized (Demucs HT)")

    async def process(self, task: AgentTask) -> AgentTask:
        """Separate audio into stems"""
        task.status = "processing"

        try:
            audio_path = task.input_data.get("audio_path")
            stem_types = task.input_data.get("stem_types", None)
            output_dir = task.input_data.get("output_dir", "./stems_output")

            if not audio_path:
                raise ValueError("No audio_path provided in task input")

            stems = await self.separate(
                Path(audio_path),
                stem_types=stem_types,
                output_dir=Path(output_dir)
            )

            task.output_data = stems
            task.status = "completed"

        except Exception as e:
            task = await self.handle_error(task, e)

        return task

    async def separate(
        self,
        audio_path: Path,
        stem_types: Optional[List[str]] = None,
        output_dir: Optional[Path] = None
    ) -> Dict[str, Any]:
        """Separate audio into stems"""
        logger.info(f"🔪 Separating: {audio_path.name}")

        if self.separator is None:
            logger.warning("Separator not loaded, loading now...")
            from models.separator import StemSeparator
            self.separator = StemSeparator()
            await self.separator.initialize()

        stems = await self.separator.separate(audio_path, stem_types)

        result: Dict[str, Any] = {
            "source_file": str(audio_path),
            "stems_extracted": list(stems.keys()),
        }

        if output_dir:
            saved = await self.separator.save_stems(stems, output_dir)
            result["output_files"] = saved
        else:
            result["stems_data"] = {k: v.tolist() for k, v in stems.items()}

        logger.info(f"✅ Separation complete: {list(stems.keys())}")
        return result

    async def extract_vocals(self, audio_path: Path) -> Dict[str, Any]:
        """Extract only vocals from audio"""
        return await self.separate(audio_path, stem_types=["vocals"])

    async def extract_instrumental(self, audio_path: Path) -> Dict[str, Any]:
        """Extract instrumental (no vocals) from audio"""
        return await self.separate(audio_path, stem_types=["bass", "drums", "other"])
