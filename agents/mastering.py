"""
Agent 7: L'Ingénieur Mastering
LUFS standardization and mastering using matchering
"""

import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional
from loguru import logger

import soundfile as sf

from agents.base import StudioAgent, AgentTask
from config import config


class MasteringEngineer(StudioAgent):
    """L'Ingénieur Mastering — Reference-quality mastering specialist"""

    def __init__(self, model_manager=None):
        super().__init__(
            agent_id=7,
            name="L'Ingénieur Mastering",
            role="LUFS Standardization & Mastering",
            model_manager=model_manager
        )

    async def initialize(self):
        """Initialize mastering tools"""
        logger.info("✅ Ingénieur Mastering initialized (matchering 2.0)")

    async def process(self, task: AgentTask) -> AgentTask:
        """Master audio to professional standards"""
        task.status = "processing"

        try:
            target_file = task.input_data.get("target_file")
            reference_file = task.input_data.get("reference_file")
            output_path = task.input_data.get("output_path")
            target_lufs = task.input_data.get("target_lufs", config.target_lufs)

            if not target_file:
                raise ValueError("No target_file provided")

            result = await self.master(
                target_path=Path(target_file),
                reference_path=Path(reference_file) if reference_file else None,
                output_path=Path(output_path) if output_path else None,
                target_lufs=target_lufs,
            )

            task.output_data = result
            task.status = "completed"

        except Exception as e:
            task = await self.handle_error(task, e)

        return task

    async def master(
        self,
        target_path: Path,
        reference_path: Optional[Path] = None,
        output_path: Optional[Path] = None,
        target_lufs: float = -14.0,
    ) -> Dict[str, Any]:
        """Master audio to professional standards"""
        logger.info(f"🎛️ Mastering: {target_path.name}")

        if output_path is None:
            output_path = target_path.parent / f"{target_path.stem}_mastered.wav"

        if reference_path and reference_path.exists():
            result = await self._master_with_reference(target_path, reference_path, output_path)
        else:
            result = await self._master_lufs_normalize(target_path, output_path, target_lufs)

        logger.info(f"✅ Mastering complete: {output_path}")
        return result

    async def _master_with_reference(
        self,
        target_path: Path,
        reference_path: Path,
        output_path: Path
    ) -> Dict[str, Any]:
        """Use matchering to match reference track characteristics"""
        try:
            import matchering as mg

            mg.process(
                target=str(target_path),
                reference=str(reference_path),
                results=[mg.pcm16(str(output_path))]
            )

            return {
                "method": "matchering",
                "target_file": str(target_path),
                "reference_file": str(reference_path),
                "output_file": str(output_path),
            }

        except ImportError:
            logger.warning("matchering not available, falling back to LUFS normalization")
            return await self._master_lufs_normalize(target_path, output_path, config.target_lufs)

        except Exception as e:
            logger.error(f"Matchering failed: {e}")
            return await self._master_lufs_normalize(target_path, output_path, config.target_lufs)

    async def _master_lufs_normalize(
        self,
        input_path: Path,
        output_path: Path,
        target_lufs: float = -14.0
    ) -> Dict[str, Any]:
        """Normalize audio to target LUFS"""
        audio, sr = sf.read(str(input_path))

        current_lufs = self._measure_lufs(audio, sr)
        gain_db = target_lufs - current_lufs
        gain_linear = 10 ** (gain_db / 20)

        audio_normalized = audio * gain_linear

        # Hard limit to -1 dBFS
        peak = np.abs(audio_normalized).max()
        if peak > 0.891:  # -1 dBFS
            audio_normalized = audio_normalized / peak * 0.891

        output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output_path), audio_normalized, sr, subtype="PCM_24")

        final_lufs = self._measure_lufs(audio_normalized, sr)

        return {
            "method": "lufs_normalization",
            "target_lufs": target_lufs,
            "original_lufs": round(current_lufs, 2),
            "final_lufs": round(final_lufs, 2),
            "gain_applied_db": round(gain_db, 2),
            "output_file": str(output_path),
        }

    def _measure_lufs(self, audio: np.ndarray, sample_rate: int) -> float:
        """Measure integrated LUFS (simplified ITU-R BS.1770)"""
        try:
            import pyloudnorm as pyln

            meter = pyln.Meter(sample_rate)
            if audio.ndim == 1:
                audio = audio[:, np.newaxis]
            loudness = meter.integrated_loudness(audio)
            return loudness
        except ImportError:
            # Fallback: RMS-based approximation
            rms = np.sqrt(np.mean(audio ** 2))
            return 20 * np.log10(rms + 1e-9)

    async def check_quality(self, audio_path: Path) -> Dict[str, Any]:
        """Run quality control checks on mastered audio"""
        audio, sr = sf.read(str(audio_path))

        lufs = self._measure_lufs(audio, sr)
        peak_db = 20 * np.log10(np.abs(audio).max() + 1e-9)
        rms_db = 20 * np.log10(np.sqrt(np.mean(audio ** 2)) + 1e-9)
        dynamic_range = peak_db - rms_db

        return {
            "lufs": round(lufs, 2),
            "peak_db": round(peak_db, 2),
            "rms_db": round(rms_db, 2),
            "dynamic_range_db": round(dynamic_range, 2),
            "is_broadcast_ready": -18.0 <= lufs <= -10.0,
            "is_streaming_ready": -16.0 <= lufs <= -12.0,
            "is_clipping": peak_db >= 0.0,
        }
