#!/usr/bin/env python3
"""
Download all world-class models for offline use
"""

import os
import sys
from pathlib import Path
import argparse
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import config


def download_llm_models():
    """Download orchestrator LLMs"""
    logger.info("📥 Downloading LLM models...")
    
    models = [
        "deepseek-ai/DeepSeek-V3",
        "Qwen/Qwen2.5-72B-Instruct",
        "mistralai/Mixtral-8x22B-Instruct-v0.1"
    ]
    
    for model_name in models:
        try:
            logger.info(f"Downloading {model_name}...")
            
            from transformers import AutoModelForCausalLM, AutoTokenizer
            
            # Download with 4-bit quantization for storage efficiency
            from transformers import BitsAndBytesConfig
            
            quantization_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4"
            )
            
            model = AutoModelForCausalLM.from_pretrained(
                model_name,
                quantization_config=quantization_config,
                device_map="cpu",
                trust_remote_code=True,
                cache_dir=config.models_cache
            )
            
            tokenizer = AutoTokenizer.from_pretrained(
                model_name,
                trust_remote_code=True,
                cache_dir=config.models_cache
            )
            
            logger.info(f"✅ Downloaded {model_name}")
            del model
            del tokenizer
            
        except Exception as e:
            logger.error(f"Failed to download {model_name}: {e}")


def download_music_models():
    """Download music generation models"""
    logger.info("🎵 Downloading music models...")
    
    try:
        import stable_audio_tools
        model = stable_audio_tools.get_pretrained("stabilityai/stable-audio-open-1.0")
        logger.info("✅ Stable Audio 2.0 downloaded")
        del model
    except Exception as e:
        logger.error(f"Failed to download Stable Audio: {e}")
    
    try:
        from audiocraft.models import MusicGen
        model = MusicGen.get_pretrained("facebook/musicgen-large")
        logger.info("✅ MusicGen Large downloaded")
        del model
    except Exception as e:
        logger.error(f"Failed to download MusicGen: {e}")


def download_speech_models():
    """Download speech recognition models"""
    logger.info("🎤 Downloading speech models...")
    
    try:
        import whisper
        model = whisper.load_model("large-v3", download_root=config.models_cache)
        logger.info("✅ Whisper Large V3 downloaded")
        del model
    except Exception as e:
        logger.error(f"Failed to download Whisper: {e}")


def download_separation_models():
    """Download stem separation models"""
    logger.info("🎚️ Downloading separation models...")
    
    try:
        from demucs import pretrained
        model = pretrained.get_model('htdemucs')
        logger.info("✅ Demucs HT downloaded")
        del model
    except Exception as e:
        logger.error(f"Failed to download Demucs: {e}")


def main():
    parser = argparse.ArgumentParser(description="Download world-class AI models")
    parser.add_argument("--all", action="store_true", help="Download all models")
    parser.add_argument("--llm", action="store_true", help="Download LLM models")
    parser.add_argument("--music", action="store_true", help="Download music models")
    parser.add_argument("--speech", action="store_true", help="Download speech models")
    parser.add_argument("--separation", action="store_true", help="Download separation models")
    
    args = parser.parse_args()
    
    config.setup_directories()
    
    logger.info("🚀 Starting model downloads...")
    logger.info(f"Cache directory: {config.models_cache}")
    
    if args.all or args.llm:
        download_llm_models()
    
    if args.all or args.music:
        download_music_models()
    
    if args.all or args.speech:
        download_speech_models()
    
    if args.all or args.separation:
        download_separation_models()
    
    logger.info("✅ All downloads complete!")


if __name__ == "__main__":
    main()