"""
Configuration for Studio IA Local et Autonome
World-class models only
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import torch


BASE_DIR = Path(__file__).resolve().parent

@dataclass
class StudioConfig:
    """Global studio configuration"""
    
    # Paths
    workspace_root: Path = Path(os.getenv("STUDIO_WORKSPACE", str(BASE_DIR / ".local_workspace")))
    fl_studio_watch_folder: Path = Path(os.getenv("FL_WATCH_FOLDER", str(BASE_DIR / ".local_watch")))
    fl_studio_output_folder: Path = Path(os.getenv("FL_OUTPUT_FOLDER", str(BASE_DIR / ".local_exports")))
    temp_folder: Path = Path(os.getenv("STUDIO_TEMP", str(BASE_DIR / ".local_temp")))
    models_cache: Path = Path(os.getenv("MODELS_CACHE", str(BASE_DIR / ".models_cache")))
    
    # Hardware
    gpu_device: str = "cuda" if torch.cuda.is_available() else "cpu"
    max_vram_usage_gb: float = float(os.getenv("MAX_VRAM_GB", "24.0"))
    enable_model_offloading: bool = os.getenv("ENABLE_OFFLOADING", "true").lower() == "true"
    use_4bit_quantization: bool = os.getenv("USE_4BIT", "true").lower() == "true"
    
    # Model Selection (World-Class Only)
    orchestrator_model: str = os.getenv("ORCHESTRATOR_MODEL", "deepseek_v3")
    music_model: str = os.getenv("MUSIC_MODEL", "stable_audio_2")
    speech_model: str = os.getenv("SPEECH_MODEL", "whisper_large_v3")
    separation_model: str = os.getenv("SEPARATION_MODEL", "demucs_ht")
    
    # Audio Defaults
    target_sample_rate: int = 44100
    target_lufs: float = -14.0
    max_duration_seconds: int = 600  # 10 minutes
    
    # API
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))
    
    # Redis/Celery
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    celery_broker_url: str = os.getenv("CELERY_BROKER", "sqla+sqlite:///celerydb.sqlite?timeout=20")
    celery_result_backend: str = os.getenv("CELERY_BACKEND", "db+sqlite:///celeryresults.sqlite?timeout=20")
    
    # World-Class Model Configs
    WORLD_CLASS_MODELS: Dict = field(default_factory=lambda: {
        "deepseek_v3": {
            "name": "deepseek-ai/DeepSeek-V3",
            "type": "llm",
            "size_gb": 40,
            "requires_4bit": True,
            "context_length": 128000,
            "description": "GPT-4 class performance, best open-source LLM"
        },
        "qwen_25_72b": {
            "name": "Qwen/Qwen2.5-72B-Instruct",
            "type": "llm",
            "size_gb": 36,
            "requires_4bit": True,
            "context_length": 131072,
            "description": "Best Llama alternative, superior benchmarks"
        },
        "mixtral_8x22b": {
            "name": "mistralai/Mixtral-8x22B-Instruct-v0.1",
            "type": "llm",
            "size_gb": 24,
            "requires_4bit": False,
            "context_length": 65536,
            "description": "Most efficient MoE architecture"
        },
        "stable_audio_2": {
            "name": "stabilityai/stable-audio-open-1.0",
            "type": "music",
            "size_gb": 8,
            "requires_4bit": False,
            "max_duration": 95,
            "description": "Commercial-grade music generation"
        },
        "magetta": {
            "name": "google/magetta",
            "type": "music",
            "size_gb": 6,
            "requires_4bit": False,
            "max_duration": 30,
            "description": "Google's best open music model"
        },
        "whisper_large_v3": {
            "name": "openai/whisper-large-v3",
            "type": "speech",
            "size_gb": 6,
            "requires_4bit": False,
            "languages": 99,
            "description": "State-of-the-art speech recognition"
        },
        "demucs_ht": {
            "name": "facebook/demucs",
            "variant": "htdemucs",
            "type": "separation",
            "size_gb": 4,
            "requires_4bit": False,
            "stems": ["drums", "bass", "other", "vocals"],
            "description": "Best source separation quality"
        }
    })
    
    # Agent Team Configuration
    AGENT_TEAM: List[Dict] = field(default_factory=lambda: [
        {
            "id": 1,
            "name": "L'Orchestrateur",
            "role": "Workflow coordination and task distribution",
            "model": "deepseek_v3",
            "priority": 1
        },
        {
            "id": 2,
            "name": "L'Analyste",
            "role": "BPM, key, and structure detection",
            "model": "librosa_madmom",
            "priority": 2
        },
        {
            "id": 3,
            "name": "Le Chirurgien",
            "role": "Stem separation and audio surgery",
            "model": "demucs_ht",
            "priority": 3
        },
        {
            "id": 4,
            "name": "Le Compositeur",
            "role": "Music generation and composition",
            "model": "stable_audio_2",
            "priority": 4
        },
        {
            "id": 5,
            "name": "L'Arrangeur",
            "role": "Track arrangement and structure",
            "model": "deepseek_v3",
            "priority": 5
        },
        {
            "id": 6,
            "name": "L'Ingénieur Son",
            "role": "Professional mixing",
            "model": "pedalboard",
            "priority": 6
        },
        {
            "id": 7,
            "name": "L'Ingénieur Mastering",
            "role": "LUFS standardization and mastering",
            "model": "matchering",
            "priority": 7
        },
        {
            "id": 8,
            "name": "Le DJ Pro",
            "role": "Beatmatching and transitions",
            "model": "custom",
            "priority": 8
        },
        {
            "id": 9,
            "name": "L'Expert Vocal",
            "role": "Vocal processing and transcription",
            "model": "whisper_large_v3",
            "priority": 9
        },
        {
            "id": 10,
            "name": "Le Superviseur",
            "role": "Quality control and validation",
            "model": "deepseek_v3",
            "priority": 10
        },
        {
            "id": 11,
            "name": "Le Gardien",
            "role": "Surveillance et Auto-correction",
            "model": "deepseek_v3",
            "priority": 11
        },
        {
            "id": 12,
            "name": "Le Compositeur Autonome",
            "role": "Génération d'instrumentales et Scraping",
            "model": "stable_audio_2",
            "priority": 12
        },
        {
            "id": 13,
            "name": "Le Chef Suprême",
            "role": "Orchestration Globale et Décision",
            "model": "deepseek_v3",
            "priority": 13
        },
        {
            "id": 14,
            "name": "Le Distributeur",
            "role": "Publication et Packaging",
            "model": "deepseek_v3",
            "priority": 14
        },
        {
            "id": 15,
            "name": "Le Transcripteur",
            "role": "Extraction Audio-to-MIDI",
            "model": "deepseek_v3",
            "priority": 15
        },
        {
            "id": 16,
            "name": "L'Ingénieur VST",
            "role": "Manipulation de Plugins Externes",
            "model": "deepseek_v3",
            "priority": 16
        },
        {
            "id": 17,
            "name": "Le Directeur Artistique",
            "role": "Analyse Hit Potential",
            "model": "deepseek_v3",
            "priority": 17
        }
    ])
    
    def setup_directories(self):
        """Create all necessary directories"""
        for folder in [
            self.workspace_root,
            self.fl_studio_watch_folder,
            self.fl_studio_output_folder,
            self.temp_folder,
            self.models_cache,
            self.workspace_root / "plans",
            self.workspace_root / "library"
        ]:
            folder.mkdir(parents=True, exist_ok=True)
    
    def get_vram_info(self) -> Dict:
        """Get GPU VRAM information"""
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            total = props.total_memory / 1e9
            reserved = torch.cuda.memory_reserved(0) / 1e9
            allocated = torch.cuda.memory_allocated(0) / 1e9
            free = total - allocated
            
            return {
                "device": props.name,
                "total_gb": round(total, 2),
                "used_gb": round(allocated, 2),
                "free_gb": round(free, 2),
                "can_run_best_models": total >= 24
            }
        return {"device": "CPU", "total_gb": 0, "used_gb": 0, "free_gb": 0}


# Global config instance
config = StudioConfig()
