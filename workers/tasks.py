"""
Celery Tasks for Audio Processing Pipeline
"""

import asyncio
import os
from pathlib import Path
from typing import Dict
from loguru import logger

from workers.celery_app import celery_app
from config import config
from models.manager import WorldClassModelManager

# ── Chargement automatique du profil lite ──────────────────────
# Si STUDIO_PROFILE=lite est défini, on injecte les modèles légers
# dans la config globale avant que les tâches ne démarrent.
if os.getenv("STUDIO_PROFILE") == "lite":
    try:
        import config_lite  # noqa: F401 — importer suffit pour injecter
        logger.info("⚡ Profil Lite chargé : modèles légers actifs")
    except Exception as _e:
        logger.warning(f"Impossible de charger config_lite : {_e}")

# Global model manager (shared across tasks)
model_manager = WorldClassModelManager()


@celery_app.task(bind=True, name="process_audio_project", autoretry_for=(Exception,), max_retries=3, default_retry_delay=5)
def process_audio_project(self, project_data: Dict) -> Dict:
    """Complete audio project processing pipeline"""

    logger.info(f"🎬 Starting project: {project_data.get('name')}")

    try:
        result = asyncio.run(_process_pipeline(project_data))

        return {
            "status": "completed",
            "task_id": self.request.id,
            "result": result
        }

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        return {
            "status": "failed",
            "task_id": self.request.id,
            "error": str(e)
        }


@celery_app.task(bind=True, name="analyze_audio", autoretry_for=(Exception,), max_retries=3, default_retry_delay=5)
def analyze_audio(self, audio_path: str) -> Dict:
    """Analyze audio file (Agent 2)"""

    from agents.analyste import Analyste

    agent = Analyste()
    result = asyncio.run(agent.analyze(Path(audio_path)))

    return result


@celery_app.task(bind=True, name="separate_stems", autoretry_for=(Exception,), max_retries=3, default_retry_delay=5)
def separate_stems(self, audio_path: str) -> Dict:
    """Separate audio into stems (Agent 3)"""

    async def _run():
        separator = await model_manager.load_separator()
        stems = await separator.separate(Path(audio_path))
        output_dir = config.temp_folder / f"stems_{self.request.id}"
        saved = await separator.save_stems(stems, output_dir)
        
        # ── Auto-export vers le bureau et lancement FL Studio ──
        try:
            from utils.fl_studio_bridge import FLStudioBridge
            bridge = FLStudioBridge()
            final_dir = await bridge.auto_export_stems(saved, "Stems")
            logger.info(f"📁 Projet prêt dans : {final_dir}")
        except Exception as e:
            logger.error(f"Erreur d'export FL Studio: {e}")
            final_dir = None

        await model_manager.unload_model("separator")

        return {"stems": saved, "fl_studio_dir": final_dir}

    return asyncio.run(_run())


@celery_app.task(bind=True, name="generate_music", autoretry_for=(Exception,), max_retries=3, default_retry_delay=5)
def generate_music(self, prompt: str, duration: int = 30) -> Dict:
    """Generate music (Agent 4)"""

    async def _run():
        generator = await model_manager.load_music_generator()
        audio = await generator.generate(prompt, duration)
        output_path = config.temp_folder / f"generated_{self.request.id}.wav"
        await generator.save_audio(audio, output_path)
        
        await model_manager.unload_model("music_gen")
        
        return {"generated_audio": str(output_path)}

    return asyncio.run(_run())


@celery_app.task(bind=True, name="transcribe_audio", autoretry_for=(Exception,), max_retries=3, default_retry_delay=5)
def transcribe_audio(self, audio_path: str) -> Dict:
    """Transcribe audio (Agent 9)"""

    async def _run():
        speech = await model_manager.load_speech_processor()
        result = await speech.transcribe(Path(audio_path))
        
        await model_manager.unload_model("speech")
        
        return result

    return asyncio.run(_run())


async def _process_pipeline(project_data: Dict) -> Dict:
    """Complete async processing pipeline"""

    results = {}

    # Step 1: Analysis (dispatch as Celery tasks - non-blocking)
    if "audio_files" in project_data:
        for audio_file in project_data["audio_files"]:
            # Use .delay() correctly — returns AsyncResult, not awaitable
            task_result = analyze_audio.delay(audio_file)
            results["analysis_task_id"] = task_result.id

    # Step 2: Stem Separation
    if project_data.get("separate_stems"):
        for audio_file in project_data.get("audio_files", []):
            task_result = separate_stems.delay(audio_file)
            results["separation_task_id"] = task_result.id

    # Step 3: Music Generation
    if project_data.get("generate_music"):
        prompt = project_data.get("music_prompt", "Electronic music")
        task_result = generate_music.delay(prompt)
        results["generation_task_id"] = task_result.id

    # Step 4: Vocal Processing
    if project_data.get("process_vocals"):
        for vocal_file in project_data.get("vocal_files", []):
            task_result = transcribe_audio.delay(vocal_file)
            results["transcription_task_id"] = task_result.id

    return results

@celery_app.task(bind=True, name="auto_remix_task", autoretry_for=(Exception,), max_retries=3, default_retry_delay=5)
def auto_remix_task(self, prompt: str, audio_path: str) -> Dict:
    """
    Auto-Remix Pro :
    1. Analyse BPM + key + beat-grid
    2. Séparation voix / instru
    3. Traitement vocal studio (autotune + compresseur + reverb + delay sync BPM)
    4. Génération beat MusicGen au BPM détecté
    5. Time-stretch du beat pour coller exactement au BPM vocal
    6. Optionnel : clean sample YouTube
    7. Mixage pro IngenieurSon (EQ + side-chain + master bus)
    8. Export FL Studio
    """
    async def _run():
        import re, gc
        import torch
        import numpy as np
        import soundfile as sf
        import librosa

        logger.info(f"🎧 Auto-Remix Pro Start | prompt='{prompt}'")

        # ── 1. Analyse ───────────────────────────────────────────────────
        from agents.analyste import Analyste
        analyste = Analyste()
        analysis = await analyste.analyze(Path(audio_path))
        bpm  = analysis.get("vocal_bpm") or analysis.get("bpm") or 120.0
        key  = analysis.get("key", "C minor")
        root = key.split()[0] if " " in key else "C"
        scale = key.split()[1].lower() if " " in key else "minor"
        logger.info(f"🎵 Analyse: BPM={bpm} | Key={key}")

        # ── 2. Détection sample YouTube ──────────────────────────────────
        yt_match = re.search(
            r'(?:ajoute|avec|sample de|et un|met un|met une)\s+(.*)',
            prompt, re.IGNORECASE,
        )
        youtube_sample_path = None
        if yt_match:
            query = yt_match.group(1).strip()
            logger.info(f"🧠 Sample détecté : '{query}'")
            try:
                from utils.youtube import YouTubeDownloader
                youtube_sample_path = YouTubeDownloader().auto_search_and_download(query)
            except Exception as e:
                logger.warning(f"YouTube sample : {e}")

        # ── 3. Séparation voix ───────────────────────────────────────────
        separator = await model_manager.load_separator()
        stems_arr  = await separator.separate(Path(audio_path))
        stems_dir  = config.temp_folder / f"stems_orig_{self.request.id}"
        saved_orig = await separator.save_stems(stems_arr, stems_dir)
        vocal_path = saved_orig.get("vocals")
        if not vocal_path or not Path(vocal_path).exists():
            raise Exception("Séparation vocale impossible.")

        # ── 4. Sample YouTube (optionnel) ────────────────────────────────
        clean_sample_path = None
        if youtube_sample_path:
            yt_stems_arr = await separator.separate(Path(youtube_sample_path))
            yt_dir = config.temp_folder / f"stems_yt_{self.request.id}"
            saved_yt = await separator.save_stems(yt_stems_arr, yt_dir)
            clean_sample_path = saved_yt.get("other")

        # Libérer VRAM Demucs avant MusicGen
        await model_manager.unload_model("separator")

        # ── 5. Traitement vocal studio (autotune + reverb + delay) ───────
        logger.info("🎤 Traitement vocal studio...")
        from agents.expert_vocal import ExpertVocal
        expert = ExpertVocal()
        vocal_studio_dir  = config.temp_folder / f"vocal_studio_{self.request.id}"
        vocal_studio_dir.mkdir(parents=True, exist_ok=True)
        studio_out = vocal_studio_dir / "vocals_studio.wav"
        studio_result = await expert.studio_vocal_chain(
            Path(vocal_path),
            key=root,
            scale=scale,
            bpm=bpm,
            autotune_strength=0.7,
            output_path=studio_out,
        )
        vocal_final_path = studio_result.get("output_file", vocal_path)
        logger.info(f"✅ Voix studio : {vocal_final_path}")

        # ── 6. Génération beat MusicGen ──────────────────────────────────
        logger.info(f"🎹 Génération beat | BPM={bpm} | key={key}")
        generator = await model_manager.load_music_generator()
        beat_audio = await generator.generate(prompt, duration_seconds=30,
                                              bpm=bpm, key=key)
        beat_raw_path = config.temp_folder / f"beat_raw_{self.request.id}.wav"
        await generator.save_audio(beat_audio, beat_raw_path)

        # Libérer MusicGen avant le mixage
        await model_manager.unload_model("music_gen")

        # ── 7. Time-stretch du beat au BPM vocal ─────────────────────────
        beat_synced_path = config.temp_folder / f"beat_synced_{self.request.id}.wav"
        try:
            beat_y, beat_sr = librosa.load(str(beat_raw_path), sr=None, mono=True)
            beat_tempo, _ = librosa.beat.beat_track(y=beat_y, sr=beat_sr)
            if hasattr(beat_tempo, "__len__"):
                beat_tempo = float(beat_tempo[0])
            if beat_tempo > 0 and abs(beat_tempo - bpm) > 1.0:
                stretch_ratio = float(bpm) / float(beat_tempo)
                logger.info(f"⏱ Time-stretch beat {beat_tempo:.1f}→{bpm:.1f} BPM (x{stretch_ratio:.3f})")
                beat_stretched = librosa.effects.time_stretch(beat_y, rate=stretch_ratio)
            else:
                beat_stretched = beat_y
            sf.write(str(beat_synced_path), beat_stretched.astype(np.float32), beat_sr)
        except Exception as e:
            logger.warning(f"Time-stretch ignoré : {e}")
            import shutil; shutil.copy2(str(beat_raw_path), str(beat_synced_path))

        # ── 8. Mixage pro IngenieurSon ────────────────────────────────────
        logger.info("🎚️ Mixage professionnel...")
        from agents.ingenieur_son import IngenieurSon
        ingenieur = IngenieurSon()

        stems_to_mix = {
            "beat":    str(beat_synced_path),
            "vocals":  str(vocal_final_path),
        }
        if clean_sample_path and Path(clean_sample_path).exists():
            stems_to_mix["other"] = str(clean_sample_path)

        mix_path = config.temp_folder / f"final_remix_{self.request.id}.wav"
        mix_result = await ingenieur.mix(
            stems=stems_to_mix,
            output_path=mix_path,
            bpm=bpm,
            key=key,
        )
        final_mix_path = mix_result.get("output_file", str(mix_path))

        # ── 9. Export FL Studio ───────────────────────────────────────────
        logger.info("📤 Export FL Studio...")
        stems_export = {
            "01_Final_Remix":  final_mix_path,
            "02_Beat_Synced":  str(beat_synced_path),
            "03_Vocals_Studio": vocal_final_path,
            "04_Vocals_Raw":   vocal_path,
        }
        if clean_sample_path and Path(clean_sample_path).exists():
            stems_export["05_Sample_YT"] = clean_sample_path

        from utils.fl_studio_bridge import FLStudioBridge
        bridge = FLStudioBridge()
        final_dir = await bridge.auto_export_stems(stems_export, "Remix_Pro")

        return {
            "remix_path":    final_mix_path,
            "fl_studio_dir": final_dir,
            "bpm":           bpm,
            "key":           key,
            "steps": [
                "analyse BPM+key",
                "séparation Demucs",
                "autotune + reverb + delay",
                "MusicGen beat",
                "time-stretch BPM sync",
                "IngenieurSon mix pro",
                "export FL Studio",
            ],
        }

        return asyncio.run(_run())


@celery_app.task(bind=True, name="clean_vocal_macro", autoretry_for=(Exception,), max_retries=2, default_retry_delay=5)
def clean_vocal_macro(self, audio_path: str) -> Dict:
    """Macro: Clean and polish vocal (De-noise, De-esser, Compression, EQ)"""
    async def _run():
        from agents.expert_vocal import ExpertVocal
        expert = ExpertVocal()
        
        output_dir = config.temp_folder / "macros"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"cleaned_{Path(audio_path).name}"
        
        # Chain basique de nettoyage
        result = await expert.studio_vocal_chain(
            Path(audio_path),
            autotune_strength=0.0, # Pas d'autotune pour un simple nettoyage
            output_path=output_path
        )
        return {"status": "success", "output_path": str(output_path), "message": "Voix nettoyée avec succès"}

    return asyncio.run(_run())


@celery_app.task(bind=True, name="vocal_production_task", autoretry_for=(Exception,), max_retries=3, default_retry_delay=5)
def vocal_production_task(self, vocal_path: str, style_prompt: str = "") -> Dict:
    """
    Production complète sur une voix brute :
    - Analyse BPM / key / structure de la voix
    - Autotune (CREPE + pyrubberband)
    - De-esser + compression + EQ + reverb + delay rythmique
    - Génération d'un beat/prod complet adapté au BPM et à la tonalité
    - Mixage pro voix + beat
    - Export FL Studio

    Usage chat : "je chante / produis derrière moi" ou "ajoute une prod sur ma voix"
    """
    async def _run():
        import gc
        import torch
        import numpy as np
        import soundfile as sf
        import librosa

        logger.info(f"🎤 Vocal Production Start | {vocal_path}")

        # ── 1. Analyse de la voix ─────────────────────────────────────────
        from agents.analyste import Analyste
        analyste = Analyste()
        analysis = await analyste.analyze(Path(vocal_path))
        bpm   = analysis.get("vocal_bpm") or analysis.get("bpm") or 90.0
        key   = analysis.get("key", "C minor")
        root  = key.split()[0] if " " in key else "C"
        scale = key.split()[1].lower() if " " in key else "minor"
        duration = float(analysis.get("duration_seconds", 30.0))
        logger.info(f"🎵 Voix analysée: {bpm} BPM | {key} | {duration:.1f}s")

        # ── 2. Traitement vocal studio ────────────────────────────────────
        logger.info("🎤 Application de la chaîne studio vocale...")
        from agents.expert_vocal import ExpertVocal
        expert = ExpertVocal()
        studio_dir = config.temp_folder / f"prod_vocals_{self.request.id}"
        studio_dir.mkdir(parents=True, exist_ok=True)
        studio_out = studio_dir / "vocals_studio.wav"

        studio_result = await expert.studio_vocal_chain(
            Path(vocal_path),
            key=root,
            scale=scale,
            bpm=bpm,
            autotune_strength=0.7,
            output_path=studio_out,
        )
        treated_vocal = studio_result.get("output_file", vocal_path)

        # ── 3. Prompt de prod auto depuis style + analyse ─────────────────
        # Construit un prompt MusicGen cohérent avec le style et la tonalité
        style_hint = style_prompt.strip() if style_prompt else "modern pop production"
        music_prompt = (
            f"{style_hint}, key {key}, professional studio beat, "
            f"cinematic production, {int(bpm)} BPM, "
            "layered synths, punchy kick, smooth bass"
        )

        # ── 4. Génération de la prod (beat + instru) ─────────────────────
        logger.info(f"🎹 Génération de la prod : '{music_prompt}'")
        generator = await model_manager.load_music_generator()
        beat_audio = await generator.generate(
            prompt=music_prompt,
            duration_seconds=int(min(duration + 4, 30)),
            bpm=bpm,
            key=key,
        )
        beat_path = config.temp_folder / f"prod_beat_{self.request.id}.wav"
        await generator.save_audio(beat_audio, beat_path)

        # Libérer MusicGen
        await model_manager.unload_model("music_gen")

        # ── 5. Time-stretch beat au BPM vocal ────────────────────────────
        beat_synced = config.temp_folder / f"prod_beat_synced_{self.request.id}.wav"
        try:
            y_b, sr_b = librosa.load(str(beat_path), sr=None, mono=True)
            beat_detected, _ = librosa.beat.beat_track(y=y_b, sr=sr_b)
            if hasattr(beat_detected, "__len__"):
                beat_detected = float(beat_detected[0])
            if beat_detected > 0 and abs(beat_detected - bpm) > 1.0:
                rate = float(bpm) / float(beat_detected)
                logger.info(f"⏱ Sync BPM {beat_detected:.1f}→{bpm:.1f}")
                y_b = librosa.effects.time_stretch(y_b, rate=rate)
            sf.write(str(beat_synced), y_b.astype(np.float32), sr_b)
        except Exception as e:
            logger.warning(f"Time-stretch ignoré : {e}")
            import shutil; shutil.copy2(str(beat_path), str(beat_synced))

        # ── 6. Mixage IngenieurSon ────────────────────────────────────────
        logger.info("🎚️ Mixage pro voix + prod...")
        from agents.ingenieur_son import IngenieurSon
        ingenieur = IngenieurSon()
        mix_path = config.temp_folder / f"prod_final_{self.request.id}.wav"
        mix_result = await ingenieur.mix(
            stems={
                "beat":   str(beat_synced),
                "vocals": str(treated_vocal),
            },
            output_path=mix_path,
            bpm=bpm,
            key=key,
        )
        final_mix = mix_result.get("output_file", str(mix_path))

        # ── 7. Export FL Studio ───────────────────────────────────────────
        from utils.fl_studio_bridge import FLStudioBridge
        bridge = FLStudioBridge()
        exports = {
            "01_Production_Finale": final_mix,
            "02_Beat_Synced":       str(beat_synced),
            "03_Voix_Studio":       treated_vocal,
            "04_Voix_Brute":        vocal_path,
        }
        final_dir = await bridge.auto_export_stems(exports, "Vocal_Production")

        return {
            "final_mix":     final_mix,
            "fl_studio_dir": final_dir,
            "bpm":           bpm,
            "key":           key,
            "steps_vocal":   studio_result.get("steps_applied", []),
        }

    return asyncio.run(_run())