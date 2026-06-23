"""
Agent 5: L'Arrangeur
Track arrangement and structure planning using DeepSeek V3
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
from loguru import logger

from agents.base import StudioAgent, AgentTask
from config import config


class Arrangeur(StudioAgent):
    """L'Arrangeur — Track arrangement specialist"""

    def __init__(self, model_manager=None):
        super().__init__(
            agent_id=5,
            name="L'Arrangeur",
            role="Track Arrangement & Structure",
            model_manager=model_manager
        )
        self.llm = None

    async def initialize(self):
        """Load LLM for arrangement planning"""
        if self.model_manager:
            self.llm = await self.model_manager.load_orchestrator()
            logger.info("✅ Arrangeur initialized (DeepSeek V3)")

    async def process(self, task: AgentTask) -> AgentTask:
        """Create arrangement plan"""
        task.status = "processing"

        try:
            project_data = task.input_data
            arrangement = await self.create_arrangement(project_data)

            task.output_data = arrangement
            task.status = "completed"

        except Exception as e:
            task = await self.handle_error(task, e)

        return task

    async def create_arrangement(self, project_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a detailed arrangement structure"""
        logger.info("🎼 Creating arrangement plan...")

        genre = project_data.get("genre", "Electronic")
        bpm = project_data.get("bpm", 128)
        key = project_data.get("key", "C minor")
        duration = project_data.get("duration", 180)

        if self.llm:
            arrangement = await self._llm_arrangement(genre, bpm, key, duration)
        else:
            arrangement = self._default_arrangement(genre, bpm, key, duration)

        logger.info(f"✅ Arrangement created: {len(arrangement['sections'])} sections")
        return arrangement

    async def _llm_arrangement(
        self, genre: str, bpm: float, key: str, duration: int
    ) -> Dict[str, Any]:
        """Use LLM to create intelligent arrangement"""
        prompt = f"""Create a professional music arrangement for:
- Genre: {genre}
- BPM: {bpm}
- Key: {key}
- Target duration: {duration}s

Return a JSON structure with sections (intro, verse, chorus, bridge, outro),
each section having: bars, start_beat, energy_level (0-1), instruments list."""

        try:
            import json, re
            response = await self.llm.generate(
                prompt,
                system_prompt="You are a world-class music arranger. Respond only with JSON."
            )
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.warning(f"LLM arrangement failed, using default: {e}")

        return self._default_arrangement(genre, bpm, key, duration)

    def _default_arrangement(
        self, genre: str, bpm: float, key: str, duration: int
    ) -> Dict[str, Any]:
        """Default arrangement template"""
        seconds_per_bar = (60 / bpm) * 4

        sections = [
            {"name": "intro",  "bars": 8,  "energy": 0.3, "instruments": ["pad", "atmosphere"]},
            {"name": "verse",  "bars": 16, "energy": 0.6, "instruments": ["drums", "bass", "synth"]},
            {"name": "chorus", "bars": 16, "energy": 1.0, "instruments": ["drums", "bass", "lead", "pad"]},
            {"name": "verse2", "bars": 16, "energy": 0.65, "instruments": ["drums", "bass", "synth", "vocal"]},
            {"name": "chorus2","bars": 16, "energy": 1.0, "instruments": ["drums", "bass", "lead", "pad", "vocal"]},
            {"name": "bridge", "bars": 8,  "energy": 0.5, "instruments": ["atmospheric", "minimal"]},
            {"name": "outro",  "bars": 8,  "energy": 0.2, "instruments": ["pad", "fade"]},
        ]

        start_time = 0.0
        for sec in sections:
            sec["start_time_s"] = round(start_time, 2)
            sec_duration = sec["bars"] * seconds_per_bar
            sec["duration_s"] = round(sec_duration, 2)
            start_time += sec_duration

        return {
            "genre": genre,
            "bpm": bpm,
            "key": key,
            "total_duration_s": round(start_time, 2),
            "sections": sections,
        }

    async def arrange_stems(
        self,
        stems: Dict[str, Any],
        arrangement: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Map stems to arrangement sections"""
        logger.info("🎛️ Arranging stems into structure...")

        timeline = []
        for section in arrangement.get("sections", []):
            for instrument in section.get("instruments", []):
                # Find matching stem
                stem_key = next(
                    (k for k in stems.keys() if instrument.lower() in k.lower()),
                    None
                )
                timeline.append({
                    "section": section["name"],
                    "instrument": instrument,
                    "stem_file": stems.get(stem_key, ""),
                    "start_time_s": section.get("start_time_s", 0),
                    "duration_s": section.get("duration_s", 0),
                    "volume": section.get("energy", 0.8),
                })

        return timeline
