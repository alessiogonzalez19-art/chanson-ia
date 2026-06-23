"""
World-Class Model Manager
Handles loading and offloading of the best open-source models
"""

import torch
import gc
import time
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path
from loguru import logger

from config import config
from models.orchestrator import OrchestratorLLM
from models.music_gen import MusicGenerator
from models.speech import SpeechProcessor
from models.separator import StemSeparator


class WorldClassModelManager:
    """
    Manages all world-class models with intelligent VRAM optimization
    """
    
    def __init__(self):
        self.loaded_models: Dict[str, Any] = {}
        self.last_used: Dict[str, float] = {}
        self.vram_manager = VRAMManager()
        
        logger.info("🎬 Initializing World-Class Model Manager")
        logger.info(f"💻 GPU: {config.get_vram_info()}")
        
        try:
            loop = asyncio.get_running_loop()
            self._cleanup_job = loop.create_task(self._cleanup_task())
        except RuntimeError:
            self._cleanup_job = None
    
    async def load_orchestrator(self, model_name: Optional[str] = None) -> OrchestratorLLM:
        """Load the best available orchestrator LLM"""
        if "orchestrator" in self.loaded_models:
            self.last_used["orchestrator"] = time.time()
            return self.loaded_models["orchestrator"]
        
        model_name = model_name or config.orchestrator_model
        logger.info(f"🧠 Loading Orchestrator: {model_name}")
        
        # Free other models if needed
        await self._optimize_vram_for_llm()
        
        orchestrator = OrchestratorLLM(model_name)
        await orchestrator.initialize()
        
        self.loaded_models["orchestrator"] = orchestrator
        self.last_used["orchestrator"] = time.time()
        return orchestrator
    
    async def load_music_generator(self) -> MusicGenerator:
        """Load music generation model"""
        if "music_gen" in self.loaded_models:
            self.last_used["music_gen"] = time.time()
            return self.loaded_models["music_gen"]
        
        logger.info(f"🎵 Loading Music Generator: {config.music_model}")
        
        # Free LLM if needed (music models are smaller)
        await self._optimize_vram_for_audio()
        
        music_gen = MusicGenerator(config.music_model)
        await music_gen.initialize()
        
        self.loaded_models["music_gen"] = music_gen
        self.last_used["music_gen"] = time.time()
        return music_gen
    
    async def load_speech_processor(self) -> SpeechProcessor:
        """Load speech recognition model"""
        if "speech" in self.loaded_models:
            self.last_used["speech"] = time.time()
            return self.loaded_models["speech"]
        
        logger.info(f"🎤 Loading Speech Processor: {config.speech_model}")
        
        speech = SpeechProcessor(config.speech_model)
        await speech.initialize()
        
        self.loaded_models["speech"] = speech
        self.last_used["speech"] = time.time()
        return speech
    
    async def load_separator(self) -> StemSeparator:
        """Load stem separation model"""
        if "separator" in self.loaded_models:
            self.last_used["separator"] = time.time()
            return self.loaded_models["separator"]
        
        logger.info(f"🎚️ Loading Stem Separator: {config.separation_model}")
        
        separator = StemSeparator(config.separation_model)
        await separator.initialize()
        
        self.loaded_models["separator"] = separator
        self.last_used["separator"] = time.time()
        return separator
    
    async def unload_model(self, model_key: str):
        """Unload a specific model to free VRAM"""
        if model_key in self.loaded_models:
            logger.info(f"🗑️ Unloading {model_key}")
            model = self.loaded_models.pop(model_key)
            self.last_used.pop(model_key, None)
            
            if hasattr(model, 'cleanup'):
                model.cleanup()
            elif hasattr(model, 'model') and hasattr(model.model, 'cpu'):
                model.model.cpu()
            elif hasattr(model, 'cpu'):
                model.cpu()
                
            del model
            gc.collect()
            torch.cuda.empty_cache()

    async def _cleanup_task(self):
        """Background task to automatically unload inactive models"""
        while True:
            await asyncio.sleep(60)  # Check every minute
            await self.cleanup_unused_models()

    async def cleanup_unused_models(self, timeout_minutes: float = 30.0):
        """Unload models that have been inactive for `timeout_minutes`"""
        current_time = time.time()
        timeout_seconds = timeout_minutes * 60
        
        for key, last_time in list(self.last_used.items()):
            if current_time - last_time > timeout_seconds:
                logger.info(f"⏰ Model {key} inactive for > {timeout_minutes} mins. Cleaning up...")
                await self.unload_model(key)
    
    async def _optimize_vram_for_llm(self):
        """Free VRAM for large language models"""
        # Music and speech models can be reloaded quickly
        for key in ["music_gen", "speech"]:
            await self.unload_model(key)
        
        available = self.vram_manager.get_available_vram_gb()
        needed = config.WORLD_CLASS_MODELS[config.orchestrator_model]["size_gb"]
        
        if available < needed:
            logger.warning(f"⚠️ Low VRAM: {available:.1f}GB available, {needed:.1f}GB needed")
            logger.warning("Using 4-bit quantization to fit model")
    
    async def _optimize_vram_for_audio(self):
        """Free VRAM for audio processing models"""
        # Orchestrator LLM is large, unload if needed
        if self.vram_manager.get_available_vram_gb() < 12:
            await self.unload_model("orchestrator")
    
    def get_status(self) -> Dict:
        """Get current model loading status"""
        return {
            "loaded_models": list(self.loaded_models.keys()),
            "vram": self.vram_manager.get_status(),
            "can_load_best": self.vram_manager.get_available_vram_gb() >= 24
        }


class VRAMManager:
    """GPU Memory Management"""
    
    def get_available_vram_gb(self) -> float:
        """Get available VRAM in GB"""
        if torch.cuda.is_available():
            total = torch.cuda.get_device_properties(0).total_memory
            allocated = torch.cuda.memory_allocated(0)
            return (total - allocated) / 1e9
        return 0.0
    
    def get_status(self) -> Dict:
        """Get detailed VRAM status"""
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            return {
                "device": props.name,
                "total_gb": props.total_memory / 1e9,
                "allocated_gb": torch.cuda.memory_allocated(0) / 1e9,
                "reserved_gb": torch.cuda.memory_reserved(0) / 1e9,
                "free_gb": self.get_available_vram_gb()
            }
        return {"device": "CPU only"}
    
    def optimize_memory(self):
        """Clear CUDA cache and garbage collect"""
        gc.collect()
        torch.cuda.empty_cache()
        logger.debug("🧹 Memory optimized")