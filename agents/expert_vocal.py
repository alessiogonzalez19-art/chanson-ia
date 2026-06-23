"""
Agent 9: L'Expert Vocal
Vocal processing, transcription, autotune et traitement studio.

Capacités :
- Transcription Whisper (word-level timestamps)
- Nettoyage bruit DeepFilterNet
- Autotune (CREPE/pyin + pyrubberband)
- De-esser (réduction sibilantes)
- Reverb / Echo vocal
- Compression vocale (pedalboard)
- Détection langue
- Diarisation locuteurs
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
from loguru import logger
import numpy as np
import soundfile as sf

from agents.base import StudioAgent, AgentTask
from config import config


class ExpertVocal(StudioAgent):
    """L'Expert Vocal — Vocal processing and transcription specialist"""

    def __init__(self, model_manager=None):
        super().__init__(
            agent_id=9,
            name="L'Expert Vocal",
            role="Vocal Processing & Transcription",
            model_manager=model_manager
        )
        self.speech_processor = None

    async def initialize(self):
        """Load speech recognition model"""
        if self.model_manager:
            self.speech_processor = await self.model_manager.load_speech_processor()
            logger.info("✅ Expert Vocal initialized (Whisper Large V3)")

    async def process(self, task: AgentTask) -> AgentTask:
        """Process vocals"""
        task.status = "processing"

        try:
            audio_path = task.input_data.get("audio_path")
            operations = task.input_data.get("operations", ["transcribe"])

            if not audio_path:
                raise ValueError("No audio_path provided")

            result = {}
            path = Path(audio_path)

            if "transcribe" in operations:
                result["transcription"] = await self.transcribe(path)

            if "detect_language" in operations:
                result["language"] = await self.detect_language(path)

            if "clean" in operations:
                result["cleaned"] = await self.clean_vocals(path)

            if "diarize" in operations:
                num_speakers = task.input_data.get("num_speakers")
                result["diarization"] = await self.transcribe_with_speakers(
                    path, num_speakers
                )

            if "autotune" in operations:
                key   = task.input_data.get("key", "C")
                scale = task.input_data.get("scale", "minor")
                strength = float(task.input_data.get("autotune_strength", 0.7))
                result["autotuned"] = await self.apply_autotune(path, key=key,
                                                                  scale=scale,
                                                                  strength=strength)

            if "studio_process" in operations:
                key   = task.input_data.get("key", "C")
                scale = task.input_data.get("scale", "minor")
                bpm   = task.input_data.get("bpm", 120.0)
                result["studio"] = await self.studio_vocal_chain(path, key=key,
                                                                    scale=scale,
                                                                    bpm=bpm)

            task.output_data = result
            task.status = "completed"

        except Exception as e:
            task = await self.handle_error(task, e)

        return task

    async def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None
    ) -> Dict[str, Any]:
        """Transcribe audio to text"""
        logger.info(f"📝 Transcribing: {audio_path.name}")

        if self.speech_processor is None:
            from models.speech import SpeechProcessor
            self.speech_processor = SpeechProcessor(config.speech_model)
            await self.speech_processor.initialize()

        return await self.speech_processor.transcribe(audio_path, language)

    async def detect_language(self, audio_path: Path) -> str:
        """Detect spoken language"""
        logger.info(f"🌍 Detecting language: {audio_path.name}")

        if self.speech_processor is None:
            from models.speech import SpeechProcessor
            self.speech_processor = SpeechProcessor(config.speech_model)
            await self.speech_processor.initialize()

        return await self.speech_processor.detect_language(audio_path)

    async def transcribe_with_speakers(
        self,
        audio_path: Path,
        num_speakers: Optional[int] = None
    ) -> Dict[str, Any]:
        """Transcribe with speaker identification"""
        logger.info(f"👥 Transcribing with speaker diarization: {audio_path.name}")

        if self.speech_processor is None:
            from models.speech import SpeechProcessor
            self.speech_processor = SpeechProcessor(config.speech_model)
            await self.speech_processor.initialize()

        return await self.speech_processor.transcribe_with_speakers(
            audio_path, num_speakers
        )

    async def clean_vocals(self, audio_path: Path) -> Dict[str, Any]:
        """Clean vocals using DeepFilterNet noise reduction"""
        logger.info(f"🎤 Cleaning vocals: {audio_path.name}")

        import numpy as np
        import soundfile as sf

        audio, sr = sf.read(str(audio_path))
        original_shape = audio.shape

        if audio.ndim > 1:
            audio_mono = audio.mean(axis=1)
        else:
            audio_mono = audio

        from models.speech import SpeechProcessor
        cleaned = await SpeechProcessor(config.speech_model).clean_audio(audio_mono, sr)

        out_path = audio_path.parent / f"{audio_path.stem}_cleaned{audio_path.suffix}"
        sf.write(str(out_path), cleaned, sr)

        return {
            "input_file": str(audio_path),
            "output_file": str(out_path),
            "sample_rate": sr,
        }

    async def extract_lyrics_timestamps(
        self,
        audio_path: Path,
        language: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Extract lyrics with word-level timestamps"""
        result = await self.transcribe(audio_path, language)

        word_timestamps = []
        for segment in result.get("segments", []):
            for word_info in segment.get("words", []):
                word_timestamps.append({
                    "word": word_info.get("word", "").strip(),
                    "start": word_info.get("start", 0),
                    "end": word_info.get("end", 0),
                    "probability": word_info.get("probability", 1.0),
                })

        return word_timestamps

    async def generate_srt(self, audio_path: Path) -> str:
        """Generate SRT subtitle file from transcription"""
        result = await self.transcribe(audio_path)
        segments = result.get("segments", [])

        srt_lines = []
        for i, segment in enumerate(segments, start=1):
            start = self._seconds_to_srt_time(segment.get("start", 0))
            end = self._seconds_to_srt_time(segment.get("end", 0))
            text = segment.get("text", "").strip()
            srt_lines.append(f"{i}\n{start} --> {end}\n{text}\n")

        srt_content = "\n".join(srt_lines)

        out_path = audio_path.with_suffix(".srt")
        out_path.write_text(srt_content, encoding="utf-8")
        logger.info(f"📄 SRT saved: {out_path}")

        return str(out_path)

    # ── Autotune ──────────────────────────────────────────────────────────────

    async def apply_autotune(
        self,
        audio_path: Path,
        key: str = "C",
        scale: str = "minor",
        strength: float = 0.7,
        formant_preserve: bool = True,
        output_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        Applique l'autotune sur la piste vocale.

        strength : 0.0 = aucune correction · 1.0 = snap dur (T-Pain)
        """
        logger.info(f"🎵 Autotune: {audio_path.name} | key={key} {scale} | force={strength}")

        try:
            from utils.autotune import autotune_file
        except ImportError:
            from autotune import autotune_file  # fallback import direct

        if output_path is None:
            output_path = audio_path.parent / f"{audio_path.stem}_autotuned.wav"

        out = autotune_file(
            audio_path,
            output_path=output_path,
            key=key,
            scale=scale,
            strength=strength,
            formant_preserve=formant_preserve,
        )

        return {
            "input_file": str(audio_path),
            "output_file": str(out),
            "key": key,
            "scale": scale,
            "strength": strength,
        }

    # ── Traitement studio complet ─────────────────────────────────────────────

    async def studio_vocal_chain(
        self,
        audio_path: Path,
        key: str = "C",
        scale: str = "minor",
        bpm: float = 120.0,
        autotune_strength: float = 0.7,
        output_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        Chaîne de traitement studio complète :
        1. Nettoyage bruit (DeepFilterNet)
        2. Autotune (CREPE + pyrubberband)
        3. De-esser (réduction sibilantes 5-9 kHz)
        4. Compression vocale (pedalboard)
        5. EQ présence (+3 dB 3-5 kHz)
        6. Reverb hall (pedalboard)
        7. Delay rythmique synchro BPM (1/8 note)
        8. Normalisation finale

        Retourne le chemin du fichier traité.
        """
        logger.info(f"🎤 Studio Vocal Chain: {audio_path.name}")

        audio, sr = sf.read(str(audio_path), always_2d=False)
        if audio.ndim == 2:
            audio = audio.mean(axis=1)
        audio = audio.astype(np.float32)

        steps_applied = []

        # ── 1. Nettoyage bruit ───────────────────────────────────────────
        try:
            from models.speech import SpeechProcessor
            audio = await SpeechProcessor(config.speech_model).clean_audio(audio, sr)
            steps_applied.append("noise_reduction")
        except Exception as e:
            logger.warning(f"Nettoyage bruit ignoré : {e}")

        # ── 2. Autotune ──────────────────────────────────────────────────
        try:
            from utils.autotune import AutotuneProcessor
            proc = AutotuneProcessor(key=key, scale=scale,
                                      strength=autotune_strength)
            audio = proc.process(audio, sr)
            steps_applied.append("autotune")
        except Exception as e:
            logger.warning(f"Autotune ignoré : {e}")

        # ── 3–7. Chaîne pedalboard ───────────────────────────────────────
        try:
            from pedalboard import (
                Pedalboard, Compressor, Gain, HighpassFilter, LowpassFilter,
                Reverb, Delay, PeakFilter, Limiter
            )

            # De-esser = réduction narrow à 6.5 kHz
            de_esser_gain = -8.0  # dB de réduction sur la bande sibilante

            # Delay rythmique 1/8 note
            eighth_note_sec = (60.0 / bpm) / 2.0

            board = Pedalboard([
                # Gate / HP pour couper les basses parasites
                HighpassFilter(cutoff_frequency_hz=100.0),
                # De-esser : atténuation des sibilantes
                PeakFilter(cutoff_frequency_hz=6500.0, gain_db=de_esser_gain, q=3.0),
                # Compression vocale : ratio 4:1, attack rapide
                Compressor(threshold_db=-22.0, ratio=4.0,
                           attack_ms=5.0, release_ms=80.0),
                # EQ présence : +3 dB à 3.5 kHz pour l'intelligibilité
                PeakFilter(cutoff_frequency_hz=3500.0, gain_db=3.0, q=1.2),
                # Couper les ultra-aigus (air band seulement si SR le supporte)
                LowpassFilter(cutoff_frequency_hz=min(16000.0, sr / 2.1)),
                # Gain de compensation
                Gain(gain_db=2.0),
                # Reverb salle medium (room_size 0.4 = studio vocal)
                Reverb(room_size=0.35, damping=0.6, wet_level=0.18,
                       dry_level=0.82, width=0.8),
                # Delay rythmique 1/8 (feedback 25 %, wet 15 %)
                Delay(delay_seconds=float(eighth_note_sec),
                      feedback=0.25, mix=0.15),
                # Limiteur final
                Limiter(threshold_db=-1.0, release_ms=100.0),
            ])

            audio_2d = audio[np.newaxis, :] if audio.ndim == 1 else audio.T
            processed = board(audio_2d.astype(np.float32), sr)
            audio = processed[0] if processed.ndim == 2 else processed
            steps_applied.extend(["de_esser", "compression", "eq_presence",
                                   "reverb", "delay", "limiter"])
        except ImportError:
            logger.warning("pedalboard non disponible, chaîne de traitement sautée")
        except Exception as e:
            logger.warning(f"Pedalboard error : {e}")

        # ── 8. Normalisation ─────────────────────────────────────────────
        peak = np.abs(audio).max()
        if peak > 0:
            audio = audio / peak * 0.93
        steps_applied.append("normalize")

        if output_path is None:
            output_path = audio_path.parent / f"{audio_path.stem}_studio.wav"

        sf.write(str(output_path), audio.astype(np.float32), sr)
        logger.info(f"✅ Studio vocal chain done → {output_path}")
        logger.info(f"   Steps: {' → '.join(steps_applied)}")

        return {
            "input_file": str(audio_path),
            "output_file": str(output_path),
            "steps_applied": steps_applied,
            "key": key,
            "scale": scale,
            "bpm": bpm,
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _seconds_to_srt_time(seconds: float) -> str:
        """Convert seconds to SRT timestamp format HH:MM:SS,mmm"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
