"""
utils/autotune.py
─────────────────
Autotune professionnel : détection de pitch (CREPE) + correction vers la gamme
la plus proche (pyrubberband) + formant preservation.

Dépendances : crepe, pyrubberband, numpy, scipy, soundfile
  pip install crepe tensorflow pyrubberband

Si crepe n'est pas installé, on tombe en fallback librosa pyin (moins précis
mais toujours fonctionnel).
"""

from __future__ import annotations

import numpy as np
from pathlib import Path
from typing import Optional
from loguru import logger
import soundfile as sf


# ── Gammes musicales ──────────────────────────────────────────────────────────
SCALES = {
    "major":       [0, 2, 4, 5, 7, 9, 11],
    "minor":       [0, 2, 3, 5, 7, 8, 10],
    "pentatonic":  [0, 2, 4, 7, 9],
    "blues":       [0, 3, 5, 6, 7, 10],
    "chromatic":   list(range(12)),
    "dorian":      [0, 2, 3, 5, 7, 9, 10],
    "mixolydian":  [0, 2, 4, 5, 7, 9, 10],
}

# Noms des classes de hauteur
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def hz_to_midi(freq: np.ndarray) -> np.ndarray:
    """Convertit Hz → numéro MIDI (A4 = 69 = 440 Hz)."""
    with np.errstate(divide="ignore", invalid="ignore"):
        midi = np.where(freq > 0, 69 + 12 * np.log2(freq / 440.0), 0.0)
    return midi.astype(np.float64)


def midi_to_hz(midi: np.ndarray) -> np.ndarray:
    """Convertit numéro MIDI → Hz."""
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def snap_to_scale(midi_note: float, root_midi: int, scale: list[int]) -> float:
    """Snaps un pitch MIDI vers la note la plus proche dans la gamme."""
    if midi_note <= 0:
        return midi_note

    # Classe de hauteur modulo 12
    pitch_class = midi_note % 12
    # Distance par rapport à la gamme
    scale_notes = [(root_midi % 12 + s) % 12 for s in scale]
    distances = [(pitch_class - s) % 12 for s in scale_notes]
    neg_distances = [(s - pitch_class) % 12 for s in scale_notes]
    min_dist = min(min(distances), min(neg_distances))

    # Trouver la note cible
    best = midi_note
    best_dist = 999.0
    for s in scale_notes:
        # Cherche toutes les octaves proches
        for octave in range(-1, 2):
            candidate = s + 12 * (int(midi_note) // 12 + octave)
            d = abs(candidate - midi_note)
            if d < best_dist:
                best_dist = d
                best = candidate

    return float(best)


class AutotuneProcessor:
    """
    Applique une correction de pitch (autotune) sur un signal vocal mono.

    Modes :
    - "subtle"  : correction douce, conserve le vibrato naturel (strength=0.5)
    - "hard"    : correction totale à la T-Pain (strength=1.0)
    - "natural" : intermédiaire (strength=0.7)
    """

    def __init__(
        self,
        key: str = "C",
        scale: str = "minor",
        strength: float = 0.7,
        formant_preserve: bool = True,
    ):
        """
        key            : tonique ex. "C", "A#"
        scale          : "major", "minor", "pentatonic", "blues", "chromatic"
        strength       : 0.0 = aucune correction, 1.0 = snap parfait
        formant_preserve : True = tente de conserver le timbre vocal
        """
        self.key = key
        self.scale_name = scale
        self.scale = SCALES.get(scale, SCALES["minor"])
        self.root_midi = NOTE_NAMES.index(key) if key in NOTE_NAMES else 0
        self.strength = np.clip(float(strength), 0.0, 1.0)
        self.formant_preserve = formant_preserve
        logger.info(
            f"🎵 AutotuneProcessor — key={key} {scale} | strength={strength} | formants={'on' if formant_preserve else 'off'}"
        )

    def process(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """
        Corrige le pitch du signal vocal.

        audio : array 1D float32/float64, normalisé −1…+1
        sr    : sample rate
        Retourne un array 1D de même longueur.
        """
        # --- 1. Détection de pitch ---
        times, freqs, confidence = self._detect_pitch(audio, sr)

        if times is None or len(times) == 0:
            logger.warning("Autotune : aucun pitch détecté, signal renvoyé intact")
            return audio

        # --- 2. Calcul des ratios de shift frame par frame ---
        #   On décompose en blocs et on applique pyrubberband par chunk.
        #   Taille de chunk ≈ hop de CREPE (10 ms)
        hop_samples = int(sr * 0.010)  # 10 ms
        if hop_samples < 1:
            hop_samples = 512

        audio_out = self._apply_pitch_correction(audio, sr, times, freqs, confidence, hop_samples)
        return audio_out

    # ──────────────────────────────────────────────────────────────────────────

    def _detect_pitch(self, audio: np.ndarray, sr: int):
        """Détection de pitch — CREPE en priorité, sinon librosa pyin."""
        try:
            import crepe
            # CREPE attend float32, sr quelconque
            a32 = audio.astype(np.float32)
            t, f, conf, _ = crepe.predict(a32, sr, viterbi=True, step_size=10, verbose=0)
            logger.info("🎤 Pitch détecté par CREPE")
            return t, f, conf
        except ImportError:
            pass

        try:
            import librosa
            f0, voiced, prob = librosa.pyin(
                audio.astype(np.float32),
                fmin=librosa.note_to_hz("C2"),
                fmax=librosa.note_to_hz("C7"),
                sr=sr,
                hop_length=512,
            )
            times = librosa.frames_to_time(np.arange(len(f0)), sr=sr, hop_length=512)
            confidence = prob.astype(np.float64)
            freq = np.where(voiced, f0, 0.0)
            logger.info("🎤 Pitch détecté par librosa pyin (fallback)")
            return times, freq, confidence
        except Exception as e:
            logger.error(f"Détection de pitch impossible : {e}")
            return None, None, None

    def _apply_pitch_correction(
        self,
        audio: np.ndarray,
        sr: int,
        times: np.ndarray,
        freqs: np.ndarray,
        confidence: np.ndarray,
        hop_samples: int,
    ) -> np.ndarray:
        """
        Applique le pitch-shift note-par-note en utilisant pyrubberband
        (online mode) ou un shift global approximatif si pyrubberband manque.
        """
        midi_detected = hz_to_midi(np.where(freqs > 0, freqs, 0.0))

        # Calcul du semitone shift pour chaque frame
        shifts = np.zeros(len(freqs))
        for i, (midi, conf) in enumerate(zip(midi_detected, confidence)):
            if midi <= 0 or conf < 0.5:
                shifts[i] = 0.0
                continue
            target = snap_to_scale(midi, self.root_midi, self.scale)
            raw_shift = target - midi
            # Application du facteur de force
            shifts[i] = raw_shift * self.strength

        # Essaie pyrubberband (frame-level pitch shift)
        try:
            import pyrubberband as pyrb
            # pyrubberband n'a pas de mode frame-by-frame natif,
            # on calcule le shift médian pondéré par confiance et on l'applique.
            # Pour une correction plus fine on sépare en segments par shift similaire.
            audio_out = self._pyrubberband_segmented(audio, sr, times, shifts, confidence)
            return audio_out
        except ImportError:
            logger.warning("pyrubberband non installé — shift global approximatif utilisé")

        # Fallback : shift global (médiane sur frames confiantes)
        confident_mask = confidence > 0.6
        if confident_mask.any():
            global_shift = float(np.median(shifts[confident_mask]))
        else:
            global_shift = 0.0

        if abs(global_shift) < 0.01:
            return audio

        try:
            import pyrubberband as pyrb
            return pyrb.pitch_shift(audio.astype(np.float64), sr, global_shift)
        except Exception:
            pass

        try:
            import librosa
            rate = 2.0 ** (global_shift / 12.0)
            return librosa.effects.pitch_shift(audio.astype(np.float32), sr=sr, n_steps=global_shift)
        except Exception as e:
            logger.error(f"Pitch shift impossible : {e}")
            return audio

    def _pyrubberband_segmented(
        self,
        audio: np.ndarray,
        sr: int,
        times: np.ndarray,
        shifts: np.ndarray,
        confidence: np.ndarray,
        min_segment_duration: float = 0.2,
    ) -> np.ndarray:
        """
        Regroupe les frames en segments de shift similaire
        et applique pyrubberband à chaque segment.
        """
        import pyrubberband as pyrb

        n = len(audio)
        output = np.zeros(n, dtype=np.float64)
        audio_d = audio.astype(np.float64)

        # Conversion times → sample indices
        frame_starts = (times * sr).astype(int)
        frame_starts = np.clip(frame_starts, 0, n - 1)

        # Groupement des frames par shift arrondi à 0.5 semitone
        rounded_shifts = np.round(shifts * 2) / 2.0  # précision 0.5 st
        segments = []
        seg_start = 0
        seg_shift = rounded_shifts[0] if len(rounded_shifts) > 0 else 0.0

        for i in range(1, len(rounded_shifts)):
            if rounded_shifts[i] != seg_shift or i == len(rounded_shifts) - 1:
                seg_end = frame_starts[i] if i < len(frame_starts) else n
                segments.append((seg_start, seg_end, seg_shift))
                seg_start = seg_end
                seg_shift = rounded_shifts[i]

        if not segments:
            segments = [(0, n, 0.0)]

        # Applique le shift segment par segment
        write_pos = 0
        for seg_s, seg_e, shift in segments:
            seg_s = max(0, min(seg_s, n))
            seg_e = max(seg_s, min(seg_e, n))
            chunk = audio_d[seg_s:seg_e]
            if len(chunk) < 256:
                output[seg_s:seg_e] = chunk
                continue
            try:
                if abs(shift) > 0.05:
                    processed = pyrb.pitch_shift(chunk, sr, shift,
                                                  rbargs={"--formant": ""} if self.formant_preserve else {})
                else:
                    processed = chunk

                # Écriture avec crossfade 32 samples pour éviter les clics
                fade = 32
                if write_pos > 0 and write_pos < n:
                    xf_len = min(fade, len(processed), n - write_pos)
                    ramp = np.linspace(0, 1, xf_len)
                    output[write_pos: write_pos + xf_len] = (
                        output[write_pos: write_pos + xf_len] * (1 - ramp)
                        + processed[:xf_len] * ramp
                    )
                    copy_len = min(len(processed) - xf_len, n - write_pos - xf_len)
                    if copy_len > 0:
                        output[write_pos + xf_len: write_pos + xf_len + copy_len] = processed[xf_len: xf_len + copy_len]
                    write_pos += len(processed)
                else:
                    copy_len = min(len(processed), n - write_pos)
                    output[write_pos: write_pos + copy_len] = processed[:copy_len]
                    write_pos += copy_len

            except Exception as e:
                logger.warning(f"Segment pitch-shift failed: {e} — copie brute")
                copy_len = min(len(chunk), n - write_pos)
                output[write_pos: write_pos + copy_len] = chunk[:copy_len]
                write_pos += copy_len

        return output.astype(np.float32)


# ── API haut niveau ───────────────────────────────────────────────────────────

def autotune_file(
    input_path: Path,
    output_path: Optional[Path] = None,
    key: str = "C",
    scale: str = "minor",
    strength: float = 0.7,
    formant_preserve: bool = True,
) -> Path:
    """
    Charge un fichier WAV vocal, applique l'autotune, sauvegarde le résultat.

    Retourne le chemin du fichier corrigé.
    """
    audio, sr = sf.read(str(input_path), always_2d=False)

    # Mono
    if audio.ndim == 2:
        audio_mono = audio.mean(axis=1)
    else:
        audio_mono = audio.copy()

    # Normalise
    peak = np.abs(audio_mono).max()
    if peak > 0:
        audio_mono = audio_mono / peak * 0.95

    processor = AutotuneProcessor(key=key, scale=scale, strength=strength,
                                   formant_preserve=formant_preserve)
    corrected = processor.process(audio_mono.astype(np.float32), sr)

    # Normalise output
    peak_out = np.abs(corrected).max()
    if peak_out > 0:
        corrected = corrected / peak_out * 0.95

    if output_path is None:
        output_path = input_path.parent / f"{input_path.stem}_autotuned{input_path.suffix}"

    sf.write(str(output_path), corrected.astype(np.float32), sr)
    logger.info(f"✅ Autotune sauvegardé : {output_path}")
    return output_path
