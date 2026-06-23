"""
config_lite.py — Profil Projet 2 : Modèles légers pour PC standard
Injecte les modèles légers dans la config globale SANS modifier config.py
Chargé automatiquement par launcher.py quand STUDIO_PROFILE=lite
"""

from config import config
from pathlib import Path

# ── Redirection des dossiers temporaires vers D: ──────────────────────────
# Économise l'espace sur C: en mettant tous les fichiers temporaires sur D:
if Path("D:/").exists():
    config.temp_folder = Path("D:/studio_ia_temp/processing")
    config.temp_folder.mkdir(parents=True, exist_ok=True)
    print(f"✅ Traitement temporaire : {config.temp_folder}")
else:
    print("⚠️ Disque D: introuvable, utilisation de C: (temp_processing)")

# ── Injection des modèles légers dans le registre global ─────
LITE_MODELS = {
    "mistral_7b": {
        "name": "mistralai/Mistral-7B-Instruct-v0.3",
        "type": "llm",
        "size_gb": 4.1,
        "requires_4bit": True,
        "context_length": 32768,
        "description": "Mistral 7B Instruct — excellent pour PC standard (4-bit = ~4GB RAM)",
    },
    "mistral_7b_ollama": {
        "name": "mistral",
        "type": "llm_ollama",
        "size_gb": 4.1,
        "requires_4bit": False,
        "context_length": 32768,
        "description": "Mistral 7B via Ollama — le plus simple à installer localement",
    },
    "musicgen_small": {
        "name": "facebook/musicgen-small",
        "type": "music",
        "size_gb": 0.3,
        "requires_4bit": False,
        "max_duration": 30,
        "description": "MusicGen Small — génération musicale légère (~300 MB)",
    },
    "musicgen_medium": {
        "name": "facebook/musicgen-medium",
        "type": "music",
        "size_gb": 1.5,
        "requires_4bit": False,
        "max_duration": 30,
        "description": "MusicGen Medium — bon compromis qualité/taille (~1.5 GB)",
    },
    "whisper_small": {
        "name": "openai/whisper-small",
        "type": "speech",
        "size_gb": 0.5,
        "requires_4bit": False,
        "languages": 99,
        "description": "Whisper Small — reconnaissance vocale légère (~500 MB)",
    },
    "whisper_medium": {
        "name": "openai/whisper-medium",
        "type": "speech",
        "size_gb": 1.5,
        "requires_4bit": False,
        "languages": 99,
        "description": "Whisper Medium — bon équilibre précision/taille (~1.5 GB)",
    },
    "demucs_mdx": {
        "name": "facebook/demucs",
        "variant": "mdx_extra",
        "type": "separation",
        "size_gb": 0.8,
        "requires_4bit": False,
        "stems": ["drums", "bass", "other", "vocals"],
        "description": "Demucs MDX Extra — séparation légère, bonne qualité (~800 MB)",
    },
}

# Injecte dans le registre global
config.WORLD_CLASS_MODELS.update(LITE_MODELS)

# ── Redirection des modèles actifs vers les versions légères ──────────────
# Avec 2 Go de VRAM, on utilise les variantes légères pour éviter les OOM.
config.music_model = "musicgen_small"          # MusicGen Small via transformers
config.separation_model = "demucs_mdx"         # Demucs MDX Extra (800 MB)
config.speech_model = "whisper_small"          # Whisper Small (500 MB)
config.orchestrator_model = "mistral_7b"       # Mistral 7B 4-bit (fallback)
config.max_vram_usage_gb = 1.8                 # Garde 200 MB de marge sécurité
