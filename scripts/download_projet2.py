#!/usr/bin/env python3
"""
Téléchargement des modèles légers — Projet 2 (PC Standard)
Compatible GTX 960 / GTX 1060 / 2–8 GB VRAM / 16 GB RAM

Modèles téléchargés :
  - Mistral 7B Instruct (4-bit quantized)  ~4 GB
  - MusicGen Small                          ~0.3 GB
  - Whisper Small                           ~0.5 GB
  - Demucs MDX Extra                        ~0.8 GB
Total estimé : ~6 GB
"""

import os
import sys
import argparse
from pathlib import Path
from loguru import logger

# Ajoute la racine au PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

# Charge le profil lite (injecte les modèles légers dans la config)
from config import config

# Répertoire de cache — préférer D: si disponible
CACHE_DIR = Path(os.getenv("MODELS_CACHE", str(Path.home() / "studio_ia_models")))


def download_llm_lite():
    """Télécharge Mistral 7B Instruct en 4-bit"""
    logger.info("🧠 Téléchargement du LLM léger : Mistral 7B Instruct (4-bit)")

    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        import torch

        model_id = "mistralai/Mistral-7B-Instruct-v0.3"

        logger.info(f"  📥 {model_id}  (~4 GB en 4-bit)")
        logger.info("  ⏳ Téléchargement du tokenizer...")

        tokenizer = AutoTokenizer.from_pretrained(
            model_id,
            cache_dir=CACHE_DIR,
            trust_remote_code=True,
        )
        logger.info("  ✅ Tokenizer téléchargé")

        # Téléchargement sans charger en mémoire GPU (juste le cache)
        logger.info("  ⏳ Téléchargement du modèle (4-bit)...")

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
        )

        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            quantization_config=bnb_config,
            device_map="cpu",  # Download to CPU first
            cache_dir=CACHE_DIR,
            trust_remote_code=True,
        )
        logger.info("  ✅ Mistral 7B Instruct (4-bit) téléchargé")
        del model, tokenizer

    except ImportError as e:
        logger.warning(f"  bitsandbytes non disponible, téléchargement en FP16 : {e}")
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer

            model_id = "mistralai/Mistral-7B-Instruct-v0.3"
            tokenizer = AutoTokenizer.from_pretrained(model_id, cache_dir=CACHE_DIR)
            model = AutoModelForCausalLM.from_pretrained(
                model_id,
                cache_dir=CACHE_DIR,
                low_cpu_mem_usage=True,
            )
            logger.info("  ✅ Mistral 7B téléchargé (FP16)")
            del model, tokenizer
        except Exception as e2:
            logger.error(f"  ❌ Échec Mistral 7B : {e2}")

    except Exception as e:
        logger.error(f"  ❌ Échec téléchargement LLM : {e}")


def download_musicgen_small():
    """Télécharge MusicGen Small de Meta"""
    logger.info("🎵 Téléchargement de MusicGen Small (~300 MB)")
    try:
        from audiocraft.models import MusicGen

        model = MusicGen.get_pretrained("facebook/musicgen-small")
        logger.info("  ✅ MusicGen Small téléchargé")
        del model
    except ImportError:
        logger.warning("  audiocraft non installé, essai via transformers...")
        try:
            from transformers import AutoProcessor, MusicgenForConditionalGeneration

            processor = AutoProcessor.from_pretrained(
                "facebook/musicgen-small",
                cache_dir=CACHE_DIR,
            )
            model = MusicgenForConditionalGeneration.from_pretrained(
                "facebook/musicgen-small",
                cache_dir=CACHE_DIR,
            )
            logger.info("  ✅ MusicGen Small téléchargé via transformers")
            del processor, model
        except Exception as e:
            logger.error(f"  ❌ Échec MusicGen Small : {e}")
    except Exception as e:
        logger.error(f"  ❌ Échec MusicGen Small : {e}")


def download_whisper_small():
    """Télécharge Whisper Small d'OpenAI"""
    logger.info("🎤 Téléchargement de Whisper Small (~500 MB)")
    try:
        import whisper

        model = whisper.load_model("small", download_root=str(CACHE_DIR))
        logger.info("  ✅ Whisper Small téléchargé")
        del model
    except ImportError:
        logger.warning("  openai-whisper non installé, essai via transformers...")
        try:
            from transformers import WhisperProcessor, WhisperForConditionalGeneration

            processor = WhisperProcessor.from_pretrained(
                "openai/whisper-small",
                cache_dir=CACHE_DIR,
            )
            model = WhisperForConditionalGeneration.from_pretrained(
                "openai/whisper-small",
                cache_dir=CACHE_DIR,
            )
            logger.info("  ✅ Whisper Small téléchargé via transformers")
            del processor, model
        except Exception as e:
            logger.error(f"  ❌ Échec Whisper Small : {e}")
    except Exception as e:
        logger.error(f"  ❌ Échec Whisper Small : {e}")


def download_demucs_mdx():
    """Télécharge Demucs MDX Extra"""
    logger.info("🎚️ Téléchargement de Demucs MDX Extra (~800 MB)")
    try:
        from demucs import pretrained

        model = pretrained.get_model("mdx_extra")
        logger.info("  ✅ Demucs MDX Extra téléchargé")
        del model
    except ImportError:
        logger.error("  ❌ demucs non installé : pip install demucs")
    except Exception as e:
        logger.error(f"  ❌ Échec Demucs MDX : {e}")


def show_summary():
    """Affiche le résumé des modèles disponibles"""
    logger.info("=" * 60)
    logger.info("📦 Résumé des modèles Projet 2 :")
    logger.info(f"   📁 Cache : {CACHE_DIR}")
    logger.info("")
    logger.info("   🧠 LLM      : Mistral 7B Instruct v0.3 (4-bit, ~4 GB)")
    logger.info("   🎵 Musique  : MusicGen Small (~300 MB)")
    logger.info("   🎤 Speech   : Whisper Small (~500 MB)")
    logger.info("   🎚️ Séparation: Demucs MDX Extra (~800 MB)")
    logger.info("")
    logger.info("   Total : ~6 GB")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Télécharger les modèles légers pour Projet 2 (PC Standard)"
    )
    parser.add_argument("--all",        action="store_true", help="Tout télécharger")
    parser.add_argument("--llm",        action="store_true", help="Mistral 7B Instruct")
    parser.add_argument("--music",      action="store_true", help="MusicGen Small")
    parser.add_argument("--speech",     action="store_true", help="Whisper Small")
    parser.add_argument("--separation", action="store_true", help="Demucs MDX Extra")

    args = parser.parse_args()

    # Si aucun argument, afficher l'aide et demander --all
    if not any(vars(args).values()):
        parser.print_help()
        print("\n💡 Lancez avec --all pour tout télécharger")
        return

    # Créer le dossier de cache
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"🚀 Démarrage des téléchargements Projet 2")
    logger.info(f"📁 Répertoire : {CACHE_DIR}")
    logger.info("")

    if args.all or args.llm:
        download_llm_lite()

    if args.all or args.music:
        download_musicgen_small()

    if args.all or args.speech:
        download_whisper_small()

    if args.all or args.separation:
        download_demucs_mdx()

    show_summary()
    logger.info("✅ Téléchargements Projet 2 terminés !")


if __name__ == "__main__":
    main()
