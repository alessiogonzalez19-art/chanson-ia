"""
Agent 2: L'Analyste
BPM, key, and structure detection using librosa + madmom
"""

import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional
from loguru import logger

import librosa
import librosa.display

from agents.base import StudioAgent, AgentTask


class Analyste(StudioAgent):
    """L'Analyste — Audio analysis specialist"""

    def __init__(self, model_manager=None):
        super().__init__(
            agent_id=2,
            name="L'Analyste",
            role="BPM, Key & Structure Detection",
            model_manager=model_manager
        )

    async def initialize(self):
        """Initialize analysis models"""
        logger.info("✅ Analyste initialized (librosa + madmom)")

    async def process(self, task: AgentTask) -> AgentTask:
        """Analyze audio files"""
        task.status = "processing"

        try:
            audio_path = task.input_data.get("audio_path")
            if audio_path:
                result = await self.analyze(Path(audio_path))
                task.output_data = result
                task.status = "completed"
            else:
                task.output_data = {"error": "No audio_path provided"}
                task.status = "failed"
        except Exception as e:
            task = await self.handle_error(task, e)

        return task

    async def analyze(self, audio_path: Path) -> Dict[str, Any]:
        """Full audio analysis pipeline"""
        logger.info(f"🔍 Analyzing: {audio_path.name}")

        # Load audio
        y, sr = librosa.load(str(audio_path), sr=None, mono=True)

        bpm = await self._detect_bpm(y, sr)
        key = await self._detect_key(y, sr)
        structure = await self._detect_structure(y, sr)
        spectral = await self._spectral_analysis(y, sr)
        beat_grid = await self._detect_beat_grid(y, sr, bpm)
        vocal_bpm = await self._detect_vocal_tempo(y, sr)
        chords = await self._detect_chords(y, sr)

        result = {
            "file": str(audio_path),
            "duration_seconds": float(len(y) / sr),
            "sample_rate": sr,
            "bpm": bpm,
            "vocal_bpm": vocal_bpm,          # BPM mesuré sur bande fréq vocale
            "key": key,
            "chords": chords,
            "structure": structure,
            "spectral": spectral,
            "beat_grid": beat_grid,           # Timestamps de chaque battement
        }

        logger.info(f"✅ Analysis complete: {bpm} BPM (vocal: {vocal_bpm}), key={key}")
        return result

    async def _detect_bpm(self, y: np.ndarray, sr: int) -> float:
        """Detect tempo using librosa beat tracking — double-check via onset strength."""
        try:
            # Méthode 1 : beat_track classique
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            if hasattr(tempo, "__len__"):
                tempo = float(tempo[0])
            bpm_classic = round(float(tempo), 2)

            # Méthode 2 : PLP (Predominant Local Pulse) — plus robuste sur voix
            onset_env = librosa.onset.onset_strength(y=y, sr=sr, aggregate=np.median)
            pulse = librosa.beat.plp(onset_envelope=onset_env, sr=sr)
            tempo_plp, _ = librosa.beat.beat_track(onset_envelope=pulse, sr=sr)
            if hasattr(tempo_plp, "__len__"):
                tempo_plp = float(tempo_plp[0])
            bpm_plp = round(float(tempo_plp), 2)

            # On prend la moyenne si les deux sont cohérents (< 5 BPM d'écart)
            if abs(bpm_classic - bpm_plp) < 5.0:
                bpm = round((bpm_classic + bpm_plp) / 2, 2)
            else:
                # On préfère PLP si la différence est grande (voix sans beat)
                bpm = bpm_plp

            return bpm
        except Exception as e:
            logger.warning(f"BPM detection failed: {e}")
            return 120.0

    async def _detect_vocal_tempo(self, y: np.ndarray, sr: int) -> float:
        """
        Détecte le tempo dans la bande fréquentielle vocale (200-2000 Hz).
        Utile pour les enregistrements a cappella sans percussion.
        """
        try:
            import scipy.signal as signal

            # Bandpass 200–2000 Hz
            nyq = sr / 2.0
            low, high = 200.0 / nyq, min(2000.0 / nyq, 0.99)
            b, a = signal.butter(4, [low, high], btype="band")
            y_vocal = signal.filtfilt(b, a, y.astype(np.float64)).astype(np.float32)

            onset_env = librosa.onset.onset_strength(y=y_vocal, sr=sr)
            tempo, _ = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
            if hasattr(tempo, "__len__"):
                tempo = float(tempo[0])
            return round(float(tempo), 2)

        except Exception as e:
            logger.warning(f"Vocal tempo detection failed: {e}")
            return 0.0

    async def _detect_beat_grid(self, y: np.ndarray, sr: int, bpm: float) -> Dict:
        """
        Génère la grille de battements (beat timestamps).
        Utile pour synchroniser le beat généré avec la voix.
        """
        try:
            _, beat_frames = librosa.beat.beat_track(y=y, sr=sr, bpm=bpm)
            beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
            return {
                "beat_times": [round(t, 4) for t in beat_times],
                "num_beats": len(beat_times),
                "beat_interval_sec": round(60.0 / bpm, 4) if bpm > 0 else 0.0,
            }
        except Exception as e:
            logger.warning(f"Beat grid detection failed: {e}")
            return {"beat_times": [], "num_beats": 0, "beat_interval_sec": 0.0}

    async def _detect_key(self, y: np.ndarray, sr: int) -> str:
        """Detect musical key using chroma features"""
        try:
            chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
            chroma_mean = chroma.mean(axis=1)
            pitch_classes = ['C', 'C#', 'D', 'D#', 'E', 'F',
                             'F#', 'G', 'G#', 'A', 'A#', 'B']
            root = pitch_classes[np.argmax(chroma_mean)]

            # Simple major/minor determination via spectral rolloff
            rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr).mean()
            mode = "major" if rolloff > 3000 else "minor"
            return f"{root} {mode}"
        except Exception as e:
            logger.warning(f"Key detection failed: {e}")
            return "C minor"

    async def _detect_chords(self, y: np.ndarray, sr: int) -> list:
        """Detect chord progression using chroma features"""
        try:
            chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
            pitch_classes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
            _, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
            if len(beat_frames) == 0:
                return []
            
            chords = []
            chroma_sync = librosa.util.sync(chroma, beat_frames, aggregate=np.median)
            for i in range(chroma_sync.shape[1]):
                root_idx = np.argmax(chroma_sync[:, i])
                chords.append(pitch_classes[root_idx])
            
            # Remove consecutive duplicates
            progression = []
            for c in chords:
                if not progression or progression[-1] != c:
                    progression.append(c)
                    
            return progression[:16] # Limit to 16 chord changes to avoid huge payloads
        except Exception as e:
            logger.warning(f"Chord detection failed: {e}")
            return []

    async def _detect_structure(self, y: np.ndarray, sr: int) -> Dict:
        """Detect song structure sections"""
        try:
            hop_length = 512
            mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13,
                                         hop_length=hop_length)
            bounds = librosa.segment.agglomerative(mfcc, k=6)
            bound_times = librosa.frames_to_time(bounds, sr=sr,
                                                  hop_length=hop_length)

            sections = []
            labels = ["intro", "verse", "chorus", "bridge", "outro", "end"]
            for i, t in enumerate(bound_times):
                sections.append({
                    "label": labels[i] if i < len(labels) else f"section_{i}",
                    "time": round(float(t), 2)
                })

            return {"sections": sections, "num_sections": len(sections)}
        except Exception as e:
            logger.warning(f"Structure detection failed: {e}")
            return {"sections": [], "num_sections": 0}

    async def _spectral_analysis(self, y: np.ndarray, sr: int) -> Dict:
        """Compute spectral characteristics"""
        try:
            centroid = librosa.feature.spectral_centroid(y=y, sr=sr).mean()
            bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr).mean()
            rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr).mean()
            zcr = librosa.feature.zero_crossing_rate(y).mean()
            rms = librosa.feature.rms(y=y).mean()

            return {
                "spectral_centroid_hz": round(float(centroid), 2),
                "spectral_bandwidth_hz": round(float(bandwidth), 2),
                "spectral_rolloff_hz": round(float(rolloff), 2),
                "zero_crossing_rate": round(float(zcr), 4),
                "rms_energy": round(float(rms), 4),
            }
        except Exception as e:
            logger.warning(f"Spectral analysis failed: {e}")
            return {}
