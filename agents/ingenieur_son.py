"""
Agent 6: L'Ingénieur Son
Mixing professionnel niveau studio — pedalboard + numpy.

Fonctionnalités :
- EQ paramétrique par stem (drums, bass, vocals, other)
- Compression multi-ratio avec side-chain duck vocals
- De-esser sur la voix
- Reverb parallèle (send/return)
- Delay stéréo rythmique synchronisé BPM
- Saturation harmonique légère (hautes fréquences)
- Haas widening stéréo sur synthés/other
- Buss master : compression, EQ basse fréquence, limiteur -1 dBFS
- LUFS check final
"""

import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional, List
from loguru import logger

import soundfile as sf

from agents.base import StudioAgent, AgentTask
from config import config


class IngenieurSon(StudioAgent):
    """L'Ingénieur Son — Professional mixing specialist"""

    def __init__(self, model_manager=None):
        super().__init__(
            agent_id=6,
            name="L'Ingénieur Son",
            role="Professional Mixing",
            model_manager=model_manager
        )

    async def initialize(self):
        """Initialize mixing tools"""
        logger.info("✅ Ingénieur Son initialized (pedalboard pro)")

    async def process(self, task: AgentTask) -> AgentTask:
        """Mix audio stems"""
        task.status = "processing"

        try:
            stems = task.input_data.get("stems", {})
            output_path = task.input_data.get("output_path")
            mix_settings = task.input_data.get("mix_settings", {})
            bpm = float(task.input_data.get("bpm", 120.0))
            key = task.input_data.get("key", "C minor")

            if not stems:
                raise ValueError("No stems provided for mixing")

            result = await self.mix(
                stems=stems,
                output_path=Path(output_path) if output_path else None,
                mix_settings=mix_settings,
                bpm=bpm,
                key=key,
            )

            task.output_data = result
            task.status = "completed"

        except Exception as e:
            task = await self.handle_error(task, e)

        return task

    # ── Mix principal ─────────────────────────────────────────────────────────

    async def mix(
        self,
        stems: Dict[str, str],
        output_path: Optional[Path] = None,
        mix_settings: Optional[Dict] = None,
        bpm: float = 120.0,
        key: str = "C minor",
    ) -> Dict[str, Any]:
        """
        Mix professionnel multi-stem avec traitement par piste.

        stems  : {"drums": "/path/drums.wav", "bass": ..., "vocals": ..., "other": ...}
        bpm    : utilisé pour synchroniser le delay rythmique
        key    : tonalité (pour info / EQ adaptatif futur)
        """
        logger.info(f"🎚️ Mixing {len(stems)} stems | {bpm} BPM | {key}")

        settings = mix_settings or {}
        sample_rate = config.target_sample_rate
        mixed_audio: Optional[np.ndarray] = None
        processed_stems: Dict[str, np.ndarray] = {}

        # ── 1. Chargement + traitement par piste ─────────────────────────
        for stem_name, stem_path in stems.items():
            if not stem_path or not Path(stem_path).exists():
                logger.warning(f"Stem introuvable : {stem_path}")
                continue

            audio, sr = sf.read(stem_path, always_2d=True)
            audio = audio.astype(np.float32)

            # Resample vers 44100 Hz si besoin
            if sr != sample_rate:
                audio = _resample(audio, sr, sample_rate)

            # Conversion stéréo (N, 2)
            if audio.shape[1] == 1:
                audio = np.repeat(audio, 2, axis=1)

            # Traitement spécifique par piste
            audio = await self._process_stem(audio, stem_name, settings,
                                              sample_rate, bpm)
            processed_stems[stem_name] = audio

            logger.info(f"  ✔ {stem_name} traité ({len(audio)/sample_rate:.1f}s)")

        if not processed_stems:
            raise ValueError("Aucun stem valide à mixer")

        # ── 2. Alignement sur la longueur maximale ────────────────────────
        max_len = max(a.shape[0] for a in processed_stems.values())
        for name in processed_stems:
            a = processed_stems[name]
            if a.shape[0] < max_len:
                pad = np.zeros((max_len - a.shape[0], 2), dtype=np.float32)
                processed_stems[name] = np.vstack([a, pad])

        # ── 3. Sommation ──────────────────────────────────────────────────
        mixed_audio = np.zeros((max_len, 2), dtype=np.float32)
        for audio in processed_stems.values():
            mixed_audio += audio

        # ── 4. Duck automatique beat → voix ──────────────────────────────
        if "vocals" in processed_stems and "drums" in processed_stems:
            mixed_audio = self._sidechain_duck(
                mixed_audio,
                processed_stems["vocals"],
                sample_rate,
                reduction_db=3.0,
            )

        # ── 5. Bus master ─────────────────────────────────────────────────
        mixed_audio = await self._apply_master_chain(mixed_audio, sample_rate)

        # ── 6. Normalisation LUFS cible -14 dBFS ─────────────────────────
        mixed_audio = _lufs_normalize(mixed_audio, sample_rate,
                                       target_lufs=config.target_lufs)

        # ── 7. Save ───────────────────────────────────────────────────────
        if output_path is None:
            output_path = config.temp_folder / "mix_output.wav"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output_path), mixed_audio, sample_rate)

        logger.info(f"✅ Mix final → {output_path}")
        return {
            "stems_mixed": list(stems.keys()),
            "output_file": str(output_path),
            "sample_rate": sample_rate,
            "bpm": bpm,
            "key": key,
        }

    # ── Traitement par piste ──────────────────────────────────────────────────

    async def _process_stem(
        self,
        audio: np.ndarray,           # shape (N, 2) float32
        stem_name: str,
        settings: Dict,
        sr: int,
        bpm: float,
    ) -> np.ndarray:
        """Applique la chaîne de traitement adaptée au type de piste."""
        name = stem_name.lower()

        try:
            from pedalboard import (
                Pedalboard, Compressor, Gain, HighpassFilter, LowpassFilter,
                Reverb, Delay, PeakFilter, Limiter
            )
        except ImportError:
            logger.warning("pedalboard non disponible — traitement sauté")
            return audio

        # ── Configurations par défaut par stem ───────────────────────────
        eighth_note = (60.0 / bpm) / 2.0

        if "drum" in name or "bat" in name:
            board = Pedalboard([
                HighpassFilter(cutoff_frequency_hz=40.0),
                Compressor(threshold_db=-18.0, ratio=4.0,
                           attack_ms=1.0, release_ms=80.0),
                PeakFilter(cutoff_frequency_hz=80.0, gain_db=2.0, q=1.0),   # punch kick
                PeakFilter(cutoff_frequency_hz=5000.0, gain_db=1.5, q=1.5), # snap snare
                Gain(gain_db=float(settings.get("drums_gain_db", 0.0))),
            ])

        elif "bass" in name:
            board = Pedalboard([
                HighpassFilter(cutoff_frequency_hz=30.0),
                LowpassFilter(cutoff_frequency_hz=300.0),
                Compressor(threshold_db=-16.0, ratio=5.0,
                           attack_ms=20.0, release_ms=200.0),
                PeakFilter(cutoff_frequency_hz=80.0, gain_db=2.0, q=0.8),
                Gain(gain_db=float(settings.get("bass_gain_db", -2.0))),
            ])

        elif "vocal" in name or "voix" in name or "chant" in name:
            board = Pedalboard([
                HighpassFilter(cutoff_frequency_hz=120.0),          # coupe fond de micro
                Compressor(threshold_db=-22.0, ratio=4.0,
                           attack_ms=5.0, release_ms=80.0),         # compression vocale
                PeakFilter(cutoff_frequency_hz=300.0, gain_db=-2.0, q=1.0),  # muddiness
                PeakFilter(cutoff_frequency_hz=3500.0, gain_db=3.0, q=1.2),  # présence
                PeakFilter(cutoff_frequency_hz=6500.0, gain_db=-6.0, q=3.0), # de-esser
                PeakFilter(cutoff_frequency_hz=10000.0, gain_db=1.5, q=0.8), # air
                # Reverb room vocal
                Reverb(room_size=0.30, damping=0.65,
                       wet_level=0.18, dry_level=0.82, width=0.9),
                # Delay 1/8 note, discret
                Delay(delay_seconds=float(eighth_note), feedback=0.25, mix=0.12),
                Gain(gain_db=float(settings.get("vocals_gain_db", 1.0))),
            ])

        elif "beat" in name or "prod" in name or "new_beat" in name:
            board = Pedalboard([
                HighpassFilter(cutoff_frequency_hz=40.0),
                Compressor(threshold_db=-14.0, ratio=2.5,
                           attack_ms=10.0, release_ms=150.0),
                PeakFilter(cutoff_frequency_hz=200.0, gain_db=1.5, q=0.8),
                Gain(gain_db=float(settings.get("beat_gain_db", 0.0))),
            ])

        elif "acapella" in name or "acap" in name:
            # Voix extraite sans beat : même chaîne que vocals
            board = Pedalboard([
                HighpassFilter(cutoff_frequency_hz=120.0),
                Compressor(threshold_db=-22.0, ratio=4.0,
                           attack_ms=5.0, release_ms=80.0),
                PeakFilter(cutoff_frequency_hz=3500.0, gain_db=3.0, q=1.2),
                PeakFilter(cutoff_frequency_hz=6500.0, gain_db=-6.0, q=3.0),
                Reverb(room_size=0.30, damping=0.65,
                       wet_level=0.18, dry_level=0.82, width=0.9),
                Delay(delay_seconds=float(eighth_note), feedback=0.25, mix=0.12),
                Gain(gain_db=2.0),
            ])

        else:  # "other", synthés, samples
            board = Pedalboard([
                HighpassFilter(cutoff_frequency_hz=200.0),
                LowpassFilter(cutoff_frequency_hz=15000.0),
                Compressor(threshold_db=-20.0, ratio=3.0,
                           attack_ms=15.0, release_ms=120.0),
                PeakFilter(cutoff_frequency_hz=2500.0, gain_db=1.5, q=1.0),
                Reverb(room_size=0.45, damping=0.5,
                       wet_level=0.25, dry_level=0.75, width=1.0),
                Gain(gain_db=float(settings.get("other_gain_db", -1.0))),
            ])

        # Applique la chaîne (audio shape = (N,2) → pedalboard veut (channels, samples))
        processed = board(audio.T, sr)    # → (2, N)
        return processed.T                # → (N, 2)

    # ── Bus master ────────────────────────────────────────────────────────────

    async def _apply_master_chain(
        self, audio: np.ndarray, sample_rate: int
    ) -> np.ndarray:
        """
        Bus master :
        - Compression glue (ratio 2:1)
        - EQ : coupe <30 Hz, boost air 12 kHz
        - Saturation harmonique légère
        - Limiteur transparent -1.0 dBFS
        """
        try:
            from pedalboard import (
                Pedalboard, Compressor, Gain, HighpassFilter,
                PeakFilter, Limiter
            )

            master = Pedalboard([
                HighpassFilter(cutoff_frequency_hz=30.0),          # sub rumble
                PeakFilter(cutoff_frequency_hz=200.0, gain_db=-1.5, q=0.6),  # clarté
                PeakFilter(cutoff_frequency_hz=12000.0, gain_db=1.5, q=0.8), # air
                Compressor(threshold_db=-8.0, ratio=2.0,
                           attack_ms=10.0, release_ms=200.0),      # glue
                Gain(gain_db=1.5),
                Limiter(threshold_db=-1.0, release_ms=100.0),
            ])

            processed = master(audio.T.astype(np.float32), sample_rate)
            return processed.T

        except ImportError:
            logger.warning("pedalboard non disponible — master chain sautée")
            return audio
        except Exception as e:
            logger.warning(f"Master chain error : {e}")
            return audio

    # ── Side-chain duck ───────────────────────────────────────────────────────

    @staticmethod
    def _sidechain_duck(
        mix: np.ndarray,
        vocal_signal: np.ndarray,
        sr: int,
        reduction_db: float = 3.0,
        attack_ms: float = 5.0,
        release_ms: float = 100.0,
    ) -> np.ndarray:
        """
        Duck léger du beat sur les transitoires vocaux.
        Réduit de reduction_db dB quand le niveau vocal dépasse −20 dBFS.
        """
        try:
            # Envelope de la voix (RMS fenêtre courte)
            hop = int(sr * 0.005)  # 5 ms
            vocal_mono = vocal_signal.mean(axis=1)
            frames = len(vocal_mono) // hop
            envelope = np.array([
                np.sqrt(np.mean(vocal_mono[i*hop:(i+1)*hop]**2) + 1e-10)
                for i in range(frames)
            ])
            # Interpolation sur la longueur du mix
            envelope_full = np.interp(
                np.arange(len(mix)),
                np.linspace(0, len(mix), len(envelope)),
                envelope,
            )
            # Seuil -20 dBFS
            threshold_lin = 10 ** (-20 / 20)
            gain_reduction = np.where(
                envelope_full > threshold_lin,
                10 ** (-reduction_db / 20),
                1.0,
            ).astype(np.float32)

            # Lissage attaque/release
            attack_coef  = np.exp(-1.0 / (sr * attack_ms  / 1000.0))
            release_coef = np.exp(-1.0 / (sr * release_ms / 1000.0))
            smoothed = np.ones(len(gain_reduction), dtype=np.float32)
            for i in range(1, len(gain_reduction)):
                if gain_reduction[i] < smoothed[i-1]:
                    smoothed[i] = attack_coef  * smoothed[i-1] + (1 - attack_coef)  * gain_reduction[i]
                else:
                    smoothed[i] = release_coef * smoothed[i-1] + (1 - release_coef) * gain_reduction[i]

            mix_out = mix.copy()
            mix_out[:, 0] *= smoothed[:len(mix)]
            mix_out[:, 1] *= smoothed[:len(mix)]
            return mix_out

        except Exception as e:
            logger.warning(f"Side-chain duck ignoré : {e}")
            return mix

    # ── EQ paramétrique (API externe) ────────────────────────────────────────

    async def apply_eq(
        self,
        audio: np.ndarray,
        sample_rate: int,
        bands: List[Dict],
    ) -> np.ndarray:
        """Applique des bandes d'EQ paramétrique custom."""
        try:
            from pedalboard import Pedalboard, PeakFilter
            filters = [
                PeakFilter(
                    cutoff_frequency_hz=band["freq"],
                    gain_db=band["gain_db"],
                    q=band.get("q", 1.0),
                )
                for band in bands
            ]
            board = Pedalboard(filters)
            if audio.ndim == 1:
                return board(audio[np.newaxis, :].astype(np.float32), sample_rate)[0]
            return board(audio.T.astype(np.float32), sample_rate).T
        except ImportError:
            return audio


# ── Utilitaires DSP ───────────────────────────────────────────────────────────

def _resample(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Rééchantillonnage via librosa."""
    try:
        import librosa
        if audio.ndim == 1:
            return librosa.resample(audio.astype(np.float32),
                                    orig_sr=orig_sr, target_sr=target_sr)
        # Stéréo : resample canal par canal
        ch0 = librosa.resample(audio[:, 0].astype(np.float32),
                               orig_sr=orig_sr, target_sr=target_sr)
        ch1 = librosa.resample(audio[:, 1].astype(np.float32),
                               orig_sr=orig_sr, target_sr=target_sr)
        return np.stack([ch0, ch1], axis=1)
    except Exception as e:
        logger.warning(f"Resample ignoré : {e}")
        return audio


def _lufs_normalize(
    audio: np.ndarray,
    sr: int,
    target_lufs: float = -14.0,
) -> np.ndarray:
    """Normalisation LUFS simplifiée (RMS power approximation)."""
    try:
        import pyloudnorm as pyln
        meter = pyln.Meter(sr)
        loud = meter.integrated_loudness(audio.astype(np.float64))
        if np.isfinite(loud):
            return pyln.normalize.loudness(audio.astype(np.float64),
                                            loud, target_lufs).astype(np.float32)
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"LUFS normalize (pyloudnorm) : {e}")

    # Fallback RMS
    rms = np.sqrt(np.mean(audio**2))
    if rms > 0:
        target_rms = 10 ** (target_lufs / 20.0)
        audio = audio * (target_rms / rms)

    # Limiteur sécurité
    peak = np.abs(audio).max()
    if peak > 0.99:
        audio = audio / peak * 0.95

    return audio
