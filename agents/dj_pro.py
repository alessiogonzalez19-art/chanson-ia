"""
Agent 8: Le DJ Pro
Beatmatching, transitions and DJ mixing
"""

import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from loguru import logger

import soundfile as sf

from agents.base import StudioAgent, AgentTask
from config import config


class DJPro(StudioAgent):
    """Le DJ Pro — Beatmatching and transition specialist"""

    def __init__(self, model_manager=None):
        super().__init__(
            agent_id=8,
            name="Le DJ Pro",
            role="Beatmatching & Transitions",
            model_manager=model_manager
        )

    async def initialize(self):
        """Initialize DJ tools"""
        logger.info("✅ DJ Pro initialized (custom beatmatching)")

    async def process(self, task: AgentTask) -> AgentTask:
        """Create DJ mix from tracks"""
        task.status = "processing"

        try:
            tracks = task.input_data.get("tracks", [])
            output_path = task.input_data.get("output_path")
            transition_duration = task.input_data.get("transition_duration_s", 8)

            if not tracks:
                raise ValueError("No tracks provided for DJ mix")

            result = await self.create_mix(
                tracks=tracks,
                output_path=Path(output_path) if output_path else None,
                transition_duration_s=transition_duration
            )

            task.output_data = result
            task.status = "completed"

        except Exception as e:
            task = await self.handle_error(task, e)

        return task

    async def create_mix(
        self,
        tracks: List[str],
        output_path: Optional[Path] = None,
        transition_duration_s: float = 8.0
    ) -> Dict[str, Any]:
        """Create a seamless DJ mix from multiple tracks"""
        logger.info(f"🎧 Creating DJ mix from {len(tracks)} tracks")

        if output_path is None:
            output_path = config.temp_folder / "dj_mix.wav"

        sample_rate = config.target_sample_rate
        mixed_segments = []
        track_info = []

        for i, track_path in enumerate(tracks):
            if not Path(track_path).exists():
                logger.warning(f"Track not found: {track_path}")
                continue

            audio, sr = sf.read(track_path)
            if sr != sample_rate:
                import librosa
                audio = librosa.resample(
                    audio.T, orig_sr=sr, target_sr=sample_rate
                ).T

            # Time-stretch to match target BPM if needed
            bpm = await self._detect_bpm(audio, sample_rate)
            track_info.append({"file": track_path, "bpm": bpm})

            mixed_segments.append(audio)
            logger.info(f"  Track {i+1}: {Path(track_path).name} @ {bpm} BPM")

        if not mixed_segments:
            raise ValueError("No valid tracks loaded")

        # Create transitions between tracks
        final_mix = await self._blend_tracks(
            mixed_segments, sample_rate, transition_duration_s
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output_path), final_mix, sample_rate)

        duration = len(final_mix) / sample_rate
        logger.info(f"✅ DJ mix created: {duration:.1f}s → {output_path}")

        return {
            "tracks_mixed": len(mixed_segments),
            "total_duration_s": round(duration, 2),
            "track_info": track_info,
            "output_file": str(output_path),
        }

    async def _detect_bpm(self, audio: np.ndarray, sample_rate: int) -> float:
        """Detect BPM of a track"""
        try:
            import librosa
            mono = audio.mean(axis=1) if audio.ndim > 1 else audio
            tempo, _ = librosa.beat.beat_track(y=mono, sr=sample_rate)
            tempo_val = float(tempo[0]) if hasattr(tempo, "__len__") else float(tempo)
            return round(tempo_val, 1)
        except Exception:
            return 128.0

    async def _blend_tracks(
        self,
        segments: List[np.ndarray],
        sample_rate: int,
        transition_s: float
    ) -> np.ndarray:
        """Blend tracks together with crossfade transitions"""
        if not segments:
            return np.array([])

        transition_samples = int(transition_s * sample_rate)
        result = segments[0].copy()

        for i in range(1, len(segments)):
            next_track = segments[i]

            # Ensure consistent channels
            result, next_track = self._match_channels(result, next_track)

            # Crossfade
            fade_out = np.linspace(1.0, 0.0, min(transition_samples, len(result)))
            fade_in  = np.linspace(0.0, 1.0, min(transition_samples, len(next_track)))

            if result.ndim > 1:
                fade_out = fade_out[:, np.newaxis]
                fade_in  = fade_in[:, np.newaxis]

            overlap_len = min(len(fade_out), len(result), len(next_track))
            result[-overlap_len:] *= fade_out[:overlap_len]
            next_trimmed = next_track.copy()
            next_trimmed[:overlap_len] *= fade_in[:overlap_len]

            # Concatenate with overlap
            combined = np.concatenate([result, next_trimmed[overlap_len:]])
            combined[-overlap_len:] += next_trimmed[:overlap_len]
            result = combined

        return result

    def _match_channels(
        self,
        a: np.ndarray,
        b: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Ensure two arrays have the same number of channels"""
        if a.ndim == 1 and b.ndim > 1:
            a = np.stack([a, a], axis=1)
        elif b.ndim == 1 and a.ndim > 1:
            b = np.stack([b, b], axis=1)
        return a, b

    async def beatmatch(
        self,
        source_path: Path,
        target_bpm: float
    ) -> Dict[str, Any]:
        """Time-stretch a track to match target BPM"""
        import librosa

        logger.info(f"🥁 Beatmatching {source_path.name} → {target_bpm} BPM")

        audio, sr = sf.read(str(source_path))
        mono = audio.mean(axis=1) if audio.ndim > 1 else audio

        source_bpm = await self._detect_bpm(mono, sr)
        ratio = target_bpm / source_bpm

        stretched = librosa.effects.time_stretch(mono, rate=ratio)

        out_path = source_path.parent / f"{source_path.stem}_beatmatched_{int(target_bpm)}bpm.wav"
        sf.write(str(out_path), stretched, sr)

        return {
            "source_bpm": source_bpm,
            "target_bpm": target_bpm,
            "stretch_ratio": round(ratio, 4),
            "output_file": str(out_path),
        }
