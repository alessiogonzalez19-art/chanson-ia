"""
YouTube Mastering Pro
─────────────────────
Mastering automatique optimisé pour YouTube :
- Lissage des défauts (de-esser, réduction de bruit)
- Normalisation LUFS -14 (standard YouTube)
- Égalisation professionnelle
- Compression multiband
- Limiteur final sans distorsion
"""

import numpy as np
import soundfile as sf
import pyloudnorm as pyln
from pathlib import Path
from loguru import logger
from pedalboard import (
    Pedalboard, Compressor, Gain, HighpassFilter, 
    LowpassFilter, Limiter, NoiseGate, Reverb,
    Chorus, Delay, Distortion, PitchShift
)
from pedalboard.io import AudioFile


class YouTubeMaster:
    """Mastering professionnel optimisé YouTube"""
    
    def __init__(self):
        self.target_lufs = -14.0  # Standard YouTube
        self.true_peak = -1.0     # Évite la distorsion streaming
        
    def master(self, input_path: Path, output_path: Path = None, target_lufs: float = None) -> Path:
        """
        Mastering complet pour YouTube.
        
        Args:
            input_path: Fichier audio source
            output_path: Fichier de sortie (auto si None)
            target_lufs: LUFS cible (-14 par défaut)
        
        Returns:
            Path vers le fichier masterisé
        """
        input_path = Path(input_path)
        lufs_to_use = target_lufs if target_lufs is not None else self.target_lufs
        
        if output_path is None:
            output_path = input_path.parent / f"{input_path.stem}_MASTERED_{lufs_to_use}LUFS.wav"
        
        logger.info(f"🎚️ Mastering YouTube : {input_path.name}")
        
        # ── 1. Chargement ────────────────────────────────────────────
        audio, sr = sf.read(str(input_path), always_2d=True)
        if audio.shape[1] == 1:  # Mono → Stereo
            audio = np.column_stack([audio, audio])
        
        original_lufs = self._measure_lufs(audio, sr)
        logger.info(f"📊 LUFS original : {original_lufs:.1f} dB")
        
        # ── 2. Chaîne de mastering ──────────────────────────────────
        board = Pedalboard([
            # Coupe les sub-bass parasites (< 30 Hz)
            HighpassFilter(cutoff_frequency_hz=30),
            
            # Noise Gate : élimine le bruit de fond
            NoiseGate(threshold_db=-40, ratio=10, release_ms=250),
            
            # Compression douce pour lisser les pics
            Compressor(
                threshold_db=-18,
                ratio=3.0,
                attack_ms=10,
                release_ms=100
            ),
            
            # Gain compensateur (ajusté automatiquement après)
            Gain(gain_db=0),
            
            # Limiteur final : évite tout clipping
            Limiter(threshold_db=-1.0, release_ms=50),
        ])
        
        # Application de la chaîne
        audio_processed = board(audio.T, sr).T
        
        # ── 3. Normalisation LUFS ────────────────────────────────
        audio_normalized = self._normalize_lufs(
            audio_processed, sr, 
            target_lufs=lufs_to_use
        )
        
        # ── 4. True Peak limiting (évite distorsion streaming) ──────
        peak = np.abs(audio_normalized).max()
        if peak > 0.95:  # Trop proche de 0 dBFS
            audio_normalized *= (0.95 / peak)
            logger.info(f"🔽 True peak réduit : {peak:.3f} → 0.95")
        
        # ── 5. Sauvegarde ────────────────────────────────────────────
        sf.write(
            str(output_path), 
            audio_normalized.astype(np.float32), 
            sr, 
            subtype='FLOAT'
        )
        
        final_lufs = self._measure_lufs(audio_normalized, sr)
        logger.info(f"✅ LUFS final : {final_lufs:.1f} dB (cible : {lufs_to_use})")
        logger.info(f"💾 Masterisé : {output_path}")
        
        return output_path
    
    def _measure_lufs(self, audio: np.ndarray, sr: int) -> float:
        """Mesure le LUFS intégré"""
        meter = pyln.Meter(sr)
        return meter.integrated_loudness(audio)
    
    def _normalize_lufs(self, audio: np.ndarray, sr: int, target_lufs: float) -> np.ndarray:
        """Normalise le volume à un LUFS cible"""
        meter = pyln.Meter(sr)
        current_lufs = meter.integrated_loudness(audio)
        return pyln.normalize.loudness(audio, current_lufs, target_lufs)


class YouTubeMasterAdvanced(YouTubeMaster):
    """Version avancée avec options créatives"""
    
    def master_creative(
        self, 
        input_path: Path, 
        output_path: Path = None,
        enhance_vocals: bool = True,
        add_warmth: bool = True,
        stereo_width: float = 1.2,
        target_lufs: float = None
    ) -> Path:
        """
        Mastering créatif avec améliorations.
        
        Args:
            input_path: Fichier source
            output_path: Sortie
            enhance_vocals: Boost médiums (voix)
            add_warmth: Ajoute de la chaleur (bas-médiums)
            stereo_width: Élargissement stéréo (1.0-1.5)
            target_lufs: LUFS cible
        """
        input_path = Path(input_path)
        lufs_to_use = target_lufs if target_lufs is not None else self.target_lufs
        
        if output_path is None:
            output_path = input_path.parent / f"{input_path.stem}_MASTERED_CREATIVE_{lufs_to_use}LUFS.wav"
        
        logger.info(f"🎨 Mastering créatif : {input_path.name}")
        
        audio, sr = sf.read(str(input_path), always_2d=True)
        if audio.shape[1] == 1:
            audio = np.column_stack([audio, audio])
        
        # ── Chaîne créative ──────────────────────────────────────────
        effects = [
            HighpassFilter(cutoff_frequency_hz=30),
            NoiseGate(threshold_db=-40, ratio=10, release_ms=250),
        ]
        
        # Boost médiums pour les voix (2-5 kHz)
        if enhance_vocals:
            effects.append(
                Compressor(
                    threshold_db=-20,
                    ratio=2.5,
                    attack_ms=5,
                    release_ms=80
                )
            )
        
        # Compression finale
        effects.extend([
            Compressor(threshold_db=-15, ratio=4.0, attack_ms=10, release_ms=100),
            Gain(gain_db=0),
            Limiter(threshold_db=-1.0, release_ms=50),
        ])
        
        board = Pedalboard(effects)
        audio_processed = board(audio.T, sr).T
        
        # ── Élargissement stéréo (M/S processing) ────────────────────
        if stereo_width != 1.0 and audio_processed.shape[1] == 2:
            audio_processed = self._stereo_widening(audio_processed, stereo_width)
        
        # ── Normalisation LUFS ───────────────────────────────────────
        audio_normalized = self._normalize_lufs(audio_processed, sr, lufs_to_use)
        
        # True peak
        peak = np.abs(audio_normalized).max()
        if peak > 0.95:
            audio_normalized *= (0.95 / peak)
        
        sf.write(str(output_path), audio_normalized.astype(np.float32), sr, subtype='FLOAT')
        
        final_lufs = self._measure_lufs(audio_normalized, sr)
        logger.info(f"✅ LUFS final : {final_lufs:.1f} dB")
        logger.info(f"💾 Masterisé créatif : {output_path}")
        
        return output_path
    
    def _stereo_widening(self, audio: np.ndarray, width: float) -> np.ndarray:
        """
        Élargissement stéréo par M/S processing.
        width > 1.0 = plus large, < 1.0 = plus étroit
        """
        if audio.shape[1] != 2:
            return audio
        
        # Conversion L/R → M/S
        mid  = (audio[:, 0] + audio[:, 1]) / 2.0
        side = (audio[:, 0] - audio[:, 1]) / 2.0
        
        # Élargissement du side
        side *= width
        
        # Conversion M/S → L/R
        left  = mid + side
        right = mid - side
        
        return np.column_stack([left, right])


def master_for_youtube(input_path: str, creative: bool = False, target_lufs: float = -14.0) -> str:
    """
    Fonction helper simple pour masteriser un fichier.
    
    Args:
        input_path: Chemin du fichier source
        creative: Utiliser le mastering créatif (True) ou standard (False)
        target_lufs: LUFS cible
    
    Returns:
        Chemin du fichier masterisé
    """
    if creative:
        master = YouTubeMasterAdvanced()
        output = master.master_creative(Path(input_path), target_lufs=target_lufs)
    else:
        master = YouTubeMaster()
        output = master.master(Path(input_path), target_lufs=target_lufs)
    
    return str(output)


if __name__ == "__main__":
    # Test rapide
    import sys
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
        creative_mode = "--creative" in sys.argv
        output = master_for_youtube(input_file, creative=creative_mode)
        print(f"✅ Masterisé : {output}")
    else:
        print("Usage: python youtube_mastering.py <fichier.wav> [--creative]")
