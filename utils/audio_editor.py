"""
Backend pour l'éditeur audio manuel (cut, fade, normalize, export).
"""

import os
from pathlib import Path
from pydub import AudioSegment
from typing import Dict, Any

def process_audio_edit(file_path: Path, operations: Dict[str, Any], output_format: str = "wav") -> Path:
    """
    Applique une série d'opérations d'édition sur un fichier audio.
    operations = {
        "cut": {"start_ms": 1000, "end_ms": 5000},
        "fade_in": {"duration_ms": 1000},
        "fade_out": {"duration_ms": 1000},
        "normalize": True,
        "pitch_shift": 0 # (non supporté basiquement par pydub, utiliser autre chose si nécessaire)
    }
    """
    audio = AudioSegment.from_file(file_path)

    # 1. Cut
    if "cut" in operations:
        start = operations["cut"].get("start_ms", 0)
        end = operations["cut"].get("end_ms", len(audio))
        audio = audio[start:end]

    # 2. Fade in
    if "fade_in" in operations:
        duration = operations["fade_in"].get("duration_ms", 1000)
        audio = audio.fade_in(duration)

    # 3. Fade out
    if "fade_out" in operations:
        duration = operations["fade_out"].get("duration_ms", 1000)
        audio = audio.fade_out(duration)

    # 4. Normalize
    if operations.get("normalize"):
        audio = audio.apply_gain(-audio.max_dBFS)

    # Export
    output_filename = f"edited_{file_path.stem}.{output_format}"
    output_path = file_path.parent / output_filename
    
    # Configure export params based on format
    export_params = {"format": output_format}
    if output_format == "mp3":
        export_params["bitrate"] = "320k"

    audio.export(output_path, **export_params)
    return output_path
