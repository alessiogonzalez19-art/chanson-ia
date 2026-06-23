"""
Agent 4: Le Compositeur
Music generation and composition using Stable Audio 2.0 / MusicGen
"""

from pathlib import Path
from typing import Dict, Any, Optional
from loguru import logger

from agents.base import StudioAgent, AgentTask
from config import config


class Compositeur(StudioAgent):
    """Le Compositeur — Music generation specialist"""

    def __init__(self, model_manager=None):
        super().__init__(
            agent_id=4,
            name="Le Compositeur",
            role="Music Generation & Composition",
            model_manager=model_manager
        )
        self.generator = None

    async def initialize(self):
        """Load music generation model"""
        if self.model_manager:
            self.generator = await self.model_manager.load_music_generator()
            logger.info("✅ Compositeur initialized (Stable Audio 2.0)")

    async def process(self, task: AgentTask) -> AgentTask:
        """Generate music from task parameters"""
        task.status = "processing"

        try:
            prompt = task.input_data.get("prompt", "Electronic music")
            duration = task.input_data.get("duration", 30)
            bpm = task.input_data.get("bpm")
            key = task.input_data.get("key")
            output_path = task.input_data.get("output_path")

            result = await self.compose(
                prompt=prompt,
                duration_seconds=duration,
                bpm=bpm,
                key=key,
                output_path=Path(output_path) if output_path else None
            )

            task.output_data = result
            task.status = "completed"

        except Exception as e:
            task = await self.handle_error(task, e)

        return task

    async def compose(
        self,
        prompt: str,
        duration_seconds: int = 30,
        bpm: Optional[float] = None,
        key: Optional[str] = None,
        output_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """Compose music from a text description"""
        logger.info(f"🎼 Composing: {prompt}")

        if self.generator is None:
            logger.warning("Generator not loaded, loading now...")
            from models.music_gen import MusicGenerator
            self.generator = MusicGenerator(config.music_model)
            await self.generator.initialize()

        audio = await self.generator.generate(
            prompt=prompt,
            duration_seconds=duration_seconds,
            bpm=bpm,
            key=key
        )

        # Default output path
        if output_path is None:
            output_path = config.temp_folder / f"composed_{prompt[:20].replace(' ', '_')}.wav"

        await self.generator.save_audio(audio, output_path)

        logger.info(f"✅ Composition saved: {output_path}")
        return {
            "prompt": prompt,
            "duration_seconds": duration_seconds,
            "bpm": bpm,
            "key": key,
            "output_file": str(output_path),
        }

    async def compose_variation(
        self,
        source_audio_path: Path,
        num_variations: int = 3
    ) -> Dict[str, Any]:
        """Generate variations of an existing piece"""
        import soundfile as sf
        import numpy as np

        logger.info(f"🎵 Generating {num_variations} variations of: {source_audio_path.name}")

        audio, _ = sf.read(str(source_audio_path))
        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        if self.generator is None:
            from models.music_gen import MusicGenerator
            self.generator = MusicGenerator(config.music_model)
            await self.generator.initialize()

        variations = await self.generator.generate_variations(
            audio, num_variations=num_variations
        )

        output_files = []
        for i, var in enumerate(variations):
            out_path = source_audio_path.parent / f"{source_audio_path.stem}_variation_{i + 1}.wav"
            await self.generator.save_audio(np.array(var), out_path)
            output_files.append(str(out_path))

        return {
            "source_file": str(source_audio_path),
            "num_variations": len(output_files),
            "output_files": output_files,
        }
