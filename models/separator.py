"""
World-Class Stem Separation
Demucs HT / UVR5 / MVSep
"""

import torch
import torchaudio
import numpy as np
from pathlib import Path
from typing import Dict, Optional
from loguru import logger
import soundfile as sf
import librosa

from config import config


class StemSeparator:
    """State-of-the-art source separation"""
    
    def __init__(self, model_name: str = "demucs_ht"):
        self.model_name = model_name
        self.model_config = config.WORLD_CLASS_MODELS[model_name]
        self.model = None
        self.uvr_model = None  # Backup UVR5 for vocals
        
    async def initialize(self):
        """Load separation models"""
        logger.info(f"🎚️ Loading {self.model_name}: {self.model_config['description']}")
        
        await self._load_demucs()
        
        # Also load UVR5 for best vocal extraction
        try:
            await self._load_uvr5()
        except:
            logger.info("UVR5 not loaded (optional)")
    
    async def _load_demucs(self):
        """Load Demucs HT"""
        from demucs import pretrained
        from demucs.apply import apply_model
        
        self.demucs_model = pretrained.get_model('htdemucs')
        self.apply_model = apply_model
        
        if torch.cuda.is_available():
            self.demucs_model.cuda()
        
        logger.info("✅ Demucs HT loaded (4-stem separation)")
    
    async def _load_uvr5(self):
        """Load UVR5 for best vocal extraction"""
        try:
            import onnxruntime as ort
            
            # UVR5 MDX23C model path
            model_path = config.models_cache / "UVR_MDXNET_Main.onnx"
            
            if model_path.exists():
                self.uvr_model = ort.InferenceSession(
                    str(model_path),
                    providers=['CUDAExecutionProvider', 'CPUExecutionProvider']
                )
                logger.info("✅ UVR5 loaded (best vocal extraction)")
            else:
                logger.info("UVR5 model not found, download with: python scripts/download_models.py")
                
        except ImportError:
            logger.info("ONNX Runtime not available for UVR5")
    
    async def separate(
        self,
        audio_path: Path,
        stem_types: Optional[list] = None
    ) -> Dict[str, np.ndarray]:
        """Separate audio into stems"""
        
        logger.info(f"🔪 Separating: {audio_path.name}")
        
        # Load audio
        wav, sr = torchaudio.load(audio_path)
        
        # Convert mono to stereo (Demucs requires 2 channels)
        if wav.shape[0] == 1:
            wav = wav.repeat(2, 1)
        
        if sr != self.demucs_model.samplerate:
            wav = torchaudio.transforms.Resample(sr, self.demucs_model.samplerate)(wav)
        
        # Normalize
        ref = wav.mean(0)
        wav = (wav - ref.mean()) / ref.std()
        
        # Demucs separation
        with torch.no_grad():
            sources = self.apply_model(
                self.demucs_model,
                wav[None],
                device='cuda' if torch.cuda.is_available() else 'cpu',
                shifts=1,
                split=True,
                overlap=0.25
            )[0]
        
        # Map to stems
        source_names = self.demucs_model.sources
        stems = {}
        
        stem_mapping = {
            'vocals': 'vocals',
            'bass': 'bass',
            'drums': 'drums',
            'other': 'other'
        }
        
        for idx, name in enumerate(source_names):
            stem_name = stem_mapping.get(name, name)
            if stem_types is None or stem_name in stem_types:
                audio_array = sources[idx].cpu().numpy()
                if self.demucs_model.samplerate != 44100:
                    audio_array = librosa.resample(audio_array, orig_sr=self.demucs_model.samplerate, target_sr=44100)
                stems[stem_name] = audio_array
        
        # Use UVR5 for better vocal separation if available
        if self.uvr_model and 'vocals' in stems:
            vocals = await self._separate_vocals_uvr5(audio_path)
            if vocals is not None:
                stems['vocals'] = vocals
                instrumental = self._create_instrumental(wav, vocals)
                if self.demucs_model.samplerate != 44100:
                    instrumental = librosa.resample(instrumental, orig_sr=self.demucs_model.samplerate, target_sr=44100)
                stems['instrumental'] = instrumental
        
        return stems
    
    async def _separate_vocals_uvr5(self, audio_path: Path) -> Optional[np.ndarray]:
        """Use UVR5 for best vocal extraction"""
        if self.uvr_model is None:
            return None
        
        try:
            logger.warning(
                "UVR5 détecté mais l'intégration directe n'est pas activée dans cette build. "
                "La séparation vocale reste assurée par Demucs pour éviter un faux résultat."
            )
            return None
        except Exception as e:
            logger.error(f"UVR5 separation failed: {e}")
            return None
    
    def _create_instrumental(
        self,
        original: torch.Tensor,
        vocals: np.ndarray
    ) -> np.ndarray:
        """Create instrumental by subtracting vocals"""
        vocals_tensor = torch.from_numpy(vocals).to(original.device)
        instrumental = original - vocals_tensor
        return instrumental.cpu().numpy()
    
    async def separate_fine_grained(
        self,
        audio_path: Path,
        instruments: list = ["piano", "guitar", "strings", "brass"]
    ) -> Dict[str, np.ndarray]:
        """Fine-grained instrument separation using MVSep"""
        
        logger.info(f"🎻 Fine-grained separation: {instruments}")

        try:
            logger.warning(
                "MVSep n'est pas branché dans cette build. Fallback vers la séparation standard Demucs."
            )
            return await self.separate(audio_path)
        except Exception as e:
            logger.error(f"MVSep separation failed: {e}")
            return await self.separate(audio_path)  # Fallback to Demucs
    
    async def save_stems(
        self,
        stems: Dict[str, np.ndarray],
        output_dir: Path,
        sample_rate: int = 44100,
        format: str = "wav"
    ):
        """Save separated stems to disk"""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        saved_files = {}
        
        for stem_name, audio in stems.items():
            # Normalize
            if audio.max() > 0:
                audio = audio / np.abs(audio).max() * 0.95
            
            output_path = output_dir / f"{stem_name}.{format}"
            
            if format == "wav":
                sf.write(output_path, audio.T if audio.ndim > 1 else audio, sample_rate)
            else:
                sf.write(output_path, audio.T if audio.ndim > 1 else audio, sample_rate, format='mp3')
            
            saved_files[stem_name] = str(output_path)
            logger.info(f"💾 Saved: {stem_name} -> {output_path}")
        
        return saved_files
    
    def cleanup(self):
        """Free VRAM"""
        if self.demucs_model:
            if hasattr(self.demucs_model, 'cpu'):
                self.demucs_model.cpu()
            del self.demucs_model
            self.demucs_model = None
        if self.uvr_model:
            del self.uvr_model
            self.uvr_model = None
        import gc
        gc.collect()
        torch.cuda.empty_cache()
