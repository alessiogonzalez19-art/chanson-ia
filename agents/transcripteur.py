"""
Agent 15: Le Transcripteur
Extraction MIDI depuis l'audio (Audio-to-MIDI).
"""

import os
from pathlib import Path
from loguru import logger
import librosa
import numpy as np

try:
    import mido
    from mido import Message, MidiFile, MidiTrack
    MIDO_AVAILABLE = True
except ImportError:
    MIDO_AVAILABLE = False

from agents.base import StudioAgent, AgentTask
from config import config

class Transcripteur(StudioAgent):
    """
    Agent qui écoute une piste audio et transcrit la mélodie principale en MIDI.
    """

    def __init__(self, model_manager=None):
        super().__init__(
            agent_id=15,
            name="Le Transcripteur",
            role="Extraction Audio-to-MIDI",
            model_manager=model_manager
        )
        self.output_dir = config.workspace_root / "midi_exports"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def process(self, task: AgentTask) -> AgentTask:
        task.status = "processing"
        logger.info(f"🎹 Le Transcripteur analyse l'audio: {task.task_id}")

        try:
            audio_path = task.input_data.get("audio_path")
            
            if not audio_path or not Path(audio_path).exists():
                raise ValueError("Fichier audio introuvable pour la transcription.")

            if not MIDO_AVAILABLE:
                raise ImportError("La librairie 'mido' n'est pas installée.")

            # Extraction du pitch via librosa.pyin
            logger.info("Analyse des fréquences (pYIN)...")
            y, sr = librosa.load(audio_path, sr=22050)
            f0, voiced_flag, voiced_probs = librosa.pyin(
                y, fmin=librosa.note_to_hz('C2'), fmax=librosa.note_to_hz('C7')
            )
            
            # Conversion basique en MIDI
            mid = MidiFile()
            track = MidiTrack()
            mid.tracks.append(track)
            
            # Ajout du tempo par défaut (120 BPM)
            track.append(mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(120), time=0))
            
            # Logique très basique de création de notes
            # En production, on utiliserait un algorithme de tracking plus avancé
            current_note = None
            time_accumulated = 0
            
            # fps de pYIN
            hop_length = 512
            frame_duration_ms = (hop_length / sr) * 1000
            ticks_per_frame = int(frame_duration_ms * mid.ticks_per_beat / 500) # approximation à 120bpm
            
            for freq, is_voiced in zip(f0, voiced_flag):
                if is_voiced and not np.isnan(freq):
                    note = int(round(librosa.hz_to_midi(freq)))
                    if current_note != note:
                        if current_note is not None:
                            # Note off
                            track.append(Message('note_off', note=current_note, velocity=64, time=time_accumulated))
                            time_accumulated = 0
                        # Note on
                        track.append(Message('note_on', note=note, velocity=100, time=time_accumulated))
                        current_note = note
                        time_accumulated = 0
                    else:
                        time_accumulated += ticks_per_frame
                else:
                    if current_note is not None:
                        track.append(Message('note_off', note=current_note, velocity=64, time=time_accumulated))
                        current_note = None
                        time_accumulated = 0
                    else:
                        time_accumulated += ticks_per_frame
            
            if current_note is not None:
                track.append(Message('note_off', note=current_note, velocity=64, time=time_accumulated))
                
            out_filename = Path(audio_path).stem + "_transcribed.mid"
            out_path = self.output_dir / out_filename
            mid.save(str(out_path))
            
            logger.info(f"🎹 Fichier MIDI généré: {out_path}")
            
            task.output_data = {
                "message": "Transcription MIDI terminée.",
                "midi_path": str(out_path)
            }
            
            task.status = "completed"
        except Exception as e:
            task = await self.handle_error(task, e)

        return task
