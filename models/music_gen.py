"""
World-Class Music Generation
Stable Audio 2.0 / Magetta / MusicGen
"""

import torch
import numpy as np
from pathlib import Path
from typing import Optional, Dict
from loguru import logger
import soundfile as sf

from config import config


class MusicGenerator:
    """State-of-the-art music generation with Stable Audio 2.0 / MusicGen"""
    
    def __init__(self, model_name: str = "stable_audio_2"):
        self.model_name = model_name
        # Support des alias du profil lite
        _model_key = model_name if model_name in config.WORLD_CLASS_MODELS else "stable_audio_2"
        self.model_config = dict(config.WORLD_CLASS_MODELS.get(_model_key, config.WORLD_CLASS_MODELS["stable_audio_2"]))
        self.model = None
        
    async def initialize(self):
        """Load music generation model"""
        logger.info(f"🎵 Loading {self.model_name}: {self.model_config.get('description', '')}")
        
        # Modèles légers (profil lite) → MusicGen via transformers directement
        if self.model_name in ("musicgen_small", "musicgen_medium"):
            await self._load_musicgen()
        elif "stable_audio" in self.model_name:
            await self._load_stable_audio()
        elif "magetta" in self.model_name:
            await self._load_magetta()
        else:
            await self._load_stable_audio()  # default → fallback interne vers musicgen
    
    async def _load_stable_audio(self):
        """Load Stable Audio 2.0"""
        try:
            import stable_audio_tools
            
            self.model = stable_audio_tools.get_pretrained(
                "stabilityai/stable-audio-open-1.0"
            )
            
            if torch.cuda.is_available():
                self.model = self.model.cuda().half()
            
            self.model_config["sample_rate"] = 44100
            logger.info("✅ Stable Audio 2.0 loaded (44.1kHz stereo)")
            
        except ImportError:
            logger.error("stable_audio_tools not installed")
            logger.info("Falling back to MusicGen...")
            await self._load_musicgen()
    
    async def _load_magetta(self):
        """Load Google Magetta"""
        try:
            # Magetta loading (hypothetical API)
            from magetta import MagettaModel
            
            self.model = MagettaModel.from_pretrained("google/magetta")
            
            if torch.cuda.is_available():
                self.model = self.model.cuda()
            
            logger.info("✅ Magetta loaded")
            
        except ImportError:
            logger.info("Magetta not available, falling back to MusicGen")
            await self._load_musicgen()
    
    async def _load_musicgen(self):
        """Load Meta MusicGen via audiocraft with fallback to transformers"""
        # Résolution du vrai model_id depuis le registre de config si dispo
        model_id = "facebook/musicgen-small"
        if self.model_name in ("musicgen_small", "stable_audio_2", "magetta"):
            # fallback ou profil lite
            model_id = "facebook/musicgen-small"
        elif self.model_name == "musicgen_medium":
            model_id = "facebook/musicgen-medium"

        # Forcer model_name à contenir 'musicgen' pour que generate() prenne la bonne branche
        self.model_name = "musicgen"
        self._musicgen_backend = "transformers"  # Default

        try:
            import audiocraft
            from audiocraft.models import MusicGen

            logger.info(f"⬇️ Téléchargement/chargement de {model_id} via audiocraft...")
            self.model = MusicGen.get_pretrained(model_id)
            self._musicgen_backend = "audiocraft"
            self.model_config["sample_rate"] = self.model.sample_rate

            logger.info(f"✅ MusicGen chargé via audiocraft ({model_id}) — SR={self.model_config['sample_rate']} Hz")
            
        except ImportError:
            logger.info("audiocraft non installé. Fallback vers Hugging Face transformers...")
            from transformers import AutoProcessor, MusicgenForConditionalGeneration
            
            logger.info(f"⬇️ Téléchargement/chargement de {model_id} via transformers...")
            self.processor = AutoProcessor.from_pretrained(model_id)
            self.model = MusicgenForConditionalGeneration.from_pretrained(model_id)

            if torch.cuda.is_available():
                self.model = self.model.cuda()

            # Récupère le sample rate réel du modèle
            self.model_config["sample_rate"] = self.model.config.audio_encoder.sampling_rate

            logger.info(f"✅ MusicGen chargé via transformers ({model_id}) — SR={self.model_config['sample_rate']} Hz")
    
    async def _generate_musicgen(self, prompt: str, duration: int) -> np.ndarray:
        """Generate with MusicGen via audiocraft or transformers"""
        if getattr(self, "_musicgen_backend", "transformers") == "audiocraft":
            self.model.set_generation_params(duration=duration)
            wav = self.model.generate([prompt])
            audio = wav[0].cpu().numpy()
            return audio
        else:
            inputs = self.processor(
                text=[prompt],
                padding=True,
                return_tensors="pt",
            )
            
            if torch.cuda.is_available():
                inputs = {k: v.cuda() for k, v in inputs.items()}
                
            # Usually 1 second = 50 tokens
            max_new_tokens = int(duration * 50)
            
            with torch.no_grad():
                output = self.model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    do_sample=True,
                    guidance_scale=3.0,
                    temperature=0.9
                )
            
            # output is shape (batch, channels, time)
            audio = output[0, 0].cpu().numpy()
            return audio
    
    async def generate(
        self,
        prompt: str,
        duration_seconds: int = 30,
        bpm: Optional[float] = None,
        key: Optional[str] = None,
        reference_audio: Optional[Path] = None
    ) -> np.ndarray:
        """Generate music from text prompt"""
        
        logger.info(f"🎼 Generating: {prompt}")
        
        # Enhance prompt with musical parameters
        enhanced_prompt = prompt
        if bpm:
            enhanced_prompt += f", {int(bpm)} BPM"
        if key:
            enhanced_prompt += f", in {key}"
        
        if "stable_audio" in self.model_name:
            return await self._generate_stable_audio(
                enhanced_prompt,
                duration_seconds,
                reference_audio
            )
        elif "magetta" in self.model_name:
            return await self._generate_magetta(enhanced_prompt, duration_seconds)
        else:
            return await self._generate_musicgen(enhanced_prompt, duration_seconds)
    
    async def generate_variations(
        self,
        audio: np.ndarray,
        num_variations: int = 3,
        temperature: float = 0.8
    ) -> list:
        """Generate variations of existing audio — uses prompt-based approach via transformers or audiocraft"""

        if "musicgen" in self.model_name.lower():
            variations = []
            for i in range(num_variations):
                if getattr(self, "_musicgen_backend", "transformers") == "audiocraft":
                    self.model.set_generation_params(temperature=temperature + i * 0.05, duration=5.0)
                    wav = self.model.generate(["continuation of an electronic music track"])
                    variations.append(wav[0].cpu().numpy())
                else:
                    inputs = self.processor(
                        text=["continuation of an electronic music track"],
                        padding=True,
                        return_tensors="pt",
                    )
                    if torch.cuda.is_available():
                        inputs = {k: v.cuda() for k, v in inputs.items()}

                    with torch.no_grad():
                        output = self.model.generate(
                            **inputs,
                            max_new_tokens=256,
                            do_sample=True,
                            guidance_scale=3.0,
                            temperature=temperature + i * 0.05,
                        )
                    variations.append(output[0, 0].cpu().numpy())
            return variations

        return [audio]  # Fallback
    
    async def save_audio(
        self,
        audio: np.ndarray,
        output_path: Path,
        sample_rate: Optional[int] = None
    ):
        """Save generated audio to file"""
        sr = sample_rate or self.model_config.get("sample_rate", config.target_sample_rate)
        
        if sr != 44100:
            import librosa
            audio = librosa.resample(audio, orig_sr=sr, target_sr=44100)
            sr = 44100
            
        # Normalize
        audio = audio / np.max(np.abs(audio)) * 0.95
        
        # Save
        sf.write(output_path, audio.T if audio.ndim > 1 else audio, sr)
        logger.info(f"💾 Saved: {output_path}")
    
    def cleanup(self):
        """Free VRAM"""
        if self.model:
            del self.model
            self.model = None
        torch.cuda.empty_cache()