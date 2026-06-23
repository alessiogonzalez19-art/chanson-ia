"""
World-Class Speech Processing
Whisper V3 Large / NVIDIA Canary
"""

import os
import torch
import whisper
import numpy as np
import platform
from pathlib import Path
from typing import Dict, List, Optional
from loguru import logger

from config import config


class SpeechProcessor:
    """State-of-the-art speech recognition and processing"""
    
    def __init__(self, model_name: str = "whisper_large_v3"):
        self.model_name = model_name
        self.model_config = config.WORLD_CLASS_MODELS[model_name]
        self.model = None
        self.device = "cpu"
        
    async def initialize(self):
        """Load speech recognition model"""
        logger.info(f"🎤 Loading {self.model_name}: {self.model_config['description']}")
        
        if "whisper" in self.model_name:
            await self._load_whisper()
        elif "canary" in self.model_name:
            await self._load_canary()
    
    async def _load_whisper(self):
        """Load the configured Whisper variant with a safe device selection."""
        whisper_name = self._resolve_whisper_name()
        self.device = self._select_whisper_device()
        self.model = whisper.load_model(whisper_name, device=self.device)
        logger.info(
            f"✅ Whisper chargé: {whisper_name} sur {self.device} "
            f"({self.model_config['languages']} langues)"
        )

    def _resolve_whisper_name(self) -> str:
        mapping = {
            "whisper_small": "small",
            "whisper_medium": "medium",
            "whisper_large_v3": "large-v3",
        }
        return mapping.get(self.model_name, "small")

    def _select_whisper_device(self) -> str:
        if os.getenv("WHISPER_FORCE_CPU", "").lower() in {"1", "true", "yes"}:
            logger.warning("WHISPER_FORCE_CPU actif: Whisper tournera sur CPU")
            return "cpu"

        if not torch.cuda.is_available():
            return "cpu"

        try:
            props = torch.cuda.get_device_properties(0)
            total_gb = props.total_memory / 1e9
            compute = (props.major, props.minor)
            if platform.system() == "Windows" and (total_gb < 4 or compute <= (5, 2)):
                logger.warning(
                    f"GPU ancien détecté pour Whisper ({props.name}, {total_gb:.1f} GB, "
                    f"compute {props.major}.{props.minor}) -> fallback CPU pour stabilité"
                )
                return "cpu"
        except Exception as e:
            logger.warning(f"Détection GPU Whisper incertaine, fallback CPU: {e}")
            return "cpu"

        return "cuda"
    
    async def _load_canary(self):
        """Load NVIDIA Canary"""
        try:
            from nemo.collections.asr.models import ASRModel
            
            self.model = ASRModel.from_pretrained("nvidia/canary-1b")
            
            if torch.cuda.is_available():
                self.model = self.model.cuda()
            
            logger.info("✅ NVIDIA Canary-1B loaded")
            
        except ImportError:
            logger.info("NVIDIA NeMo not available, falling back to Whisper")
            await self._load_whisper()
    
    async def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
        task: str = "transcribe"
    ) -> Dict:
        """Transcribe audio to text"""
        
        logger.info(f"📝 Transcribing: {audio_path.name}")
        
        if "whisper" in self.model_name:
            return await self._transcribe_whisper(audio_path, language, task)
        else:
            return await self._transcribe_canary(audio_path, language)
    
    async def _transcribe_whisper(
        self,
        audio_path: Path,
        language: Optional[str],
        task: str
    ) -> Dict:
        """Whisper transcription with word-level timestamps"""
        
        options = {
            "task": task,
            "verbose": False,
            "word_timestamps": True,
            "fp16": self.device == "cuda",
        }
        
        if language:
            options["language"] = language
        
        result = self.model.transcribe(str(audio_path), **options)
        
        return {
            "text": result["text"],
            "language": result.get("language", "unknown"),
            "segments": result.get("segments", []),
            "duration": result.get("duration", 0)
        }
    
    async def _transcribe_canary(self, audio_path: Path, language: Optional[str]) -> Dict:
        """NVIDIA Canary transcription with diarization"""
        if self.model is None:
            raise RuntimeError("Le modèle de transcription n'est pas chargé.")

        transcribe_method = getattr(self.model, "transcribe", None)
        if callable(transcribe_method):
            try:
                result = transcribe_method(str(audio_path))
                if isinstance(result, dict):
                    return {
                        "text": result.get("text", ""),
                        "language": result.get("language", language or "unknown"),
                        "segments": result.get("segments", []),
                        "duration": result.get("duration", 0),
                    }
            except Exception as e:
                logger.warning(f"Transcription Canary indisponible, fallback Whisper: {e}")

        logger.warning("Canary non exploitable dans cette configuration, fallback Whisper.")
        return await self._transcribe_whisper(audio_path, language, "transcribe")
    
    async def detect_language(self, audio_path: Path) -> str:
        """Detect audio language"""
        if "whisper" in self.model_name:
            # Load audio and detect
            audio = whisper.load_audio(str(audio_path))
            audio = whisper.pad_or_trim(audio)
            mel = whisper.log_mel_spectrogram(audio).to(self.device)
            
            _, probs = self.model.detect_language(mel)
            detected = max(probs, key=probs.get)
            
            return detected
        
        return "en"  # Default
    
    async def transcribe_with_speakers(
        self,
        audio_path: Path,
        num_speakers: Optional[int] = None
    ) -> Dict:
        """Transcribe with speaker diarization"""
        
        logger.info(f"👥 Transcribing with speaker identification: {audio_path.name}")
        
        # First, transcribe with Whisper
        transcription = await self.transcribe(audio_path)
        
        # Add speaker diarization using pyannote or similar
        try:
            from pyannote.audio import Pipeline
            
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=os.getenv("HF_TOKEN")
            )
            
            if torch.cuda.is_available():
                pipeline = pipeline.to(torch.device("cuda"))
            
            diarization = pipeline(str(audio_path), num_speakers=num_speakers)
            
            # Merge transcription with diarization
            transcription["speakers"] = self._merge_speakers(
                transcription["segments"],
                diarization
            )
            
        except ImportError:
            logger.warning("pyannote not available, skipping speaker diarization")
            transcription["speakers"] = []
        
        return transcription
    
    def _merge_speakers(self, segments: List, diarization) -> List:
        """Merge transcription segments with speaker labels"""
        speaker_segments = []
        
        for segment in segments:
            segment_start = segment["start"]
            segment_end = segment["end"]
            
            # Find overlapping speaker
            speaker = "Unknown"
            for turn, _, speaker_label in diarization.itertracks(yield_label=True):
                if turn.start <= segment_start <= turn.end:
                    speaker = speaker_label
                    break
            
            speaker_segments.append({
                **segment,
                "speaker": speaker
            })
        
        return speaker_segments
    
    async def clean_audio(
        self,
        audio: np.ndarray,
        sample_rate: int
    ) -> np.ndarray:
        """Clean audio using DeepFilterNet"""
        try:
            from df import enhance, init_df
            
            model, df_state, _ = init_df()
            enhanced = enhance(model, df_state, audio)
            
            return enhanced
            
        except ImportError:
            logger.warning("DeepFilterNet not available, skipping cleaning")
            return audio
    
    def cleanup(self):
        """Free VRAM"""
        if self.model:
            del self.model
            self.model = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
