"""
Agent 17: Le Directeur Artistique (A&R)
Analyse musicale experte et "Hit Potential" via librosa et LLM.
"""

from loguru import logger
import librosa
import numpy as np

from agents.base import StudioAgent, AgentTask

class DirecteurArtistique(StudioAgent):
    """
    Agent qui évalue le potentiel d'un morceau ("Hit Analyzer").
    Il extrait des features (RMS, BPM, Centroid) et demande au LLM une note.
    """

    def __init__(self, model_manager=None):
        super().__init__(
            agent_id=17,
            name="Le Directeur Artistique",
            role="Analyse Hit Potential",
            model_manager=model_manager
        )
        self.llm = None

    async def initialize(self):
        if self.model_manager:
            self.llm = await self.model_manager.load_orchestrator()

    async def process(self, task: AgentTask) -> AgentTask:
        task.status = "processing"
        logger.info(f"📈 Le Directeur Artistique écoute la track: {task.task_id}")

        try:
            audio_path = task.input_data.get("audio_path")
            
            if not audio_path:
                raise ValueError("Fichier audio introuvable.")

            # Extraction de features
            logger.info("Extraction des métriques audio...")
            y, sr = librosa.load(audio_path, duration=30) # Analyse sur les 30 premières secondes
            
            # Énergie (RMS)
            rms = librosa.feature.rms(y=y)[0]
            avg_rms = float(np.mean(rms))
            
            # Brillance (Spectral Centroid)
            cent = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
            avg_cent = float(np.mean(cent))
            
            # Tempo
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            tempo_val = float(tempo[0]) if isinstance(tempo, np.ndarray) else float(tempo)
            
            # Analyse LLM
            prompt = f"""
            Tu es le Directeur Artistique (A&R) d'un grand label.
            Voici les caractéristiques acoustiques d'une maquette :
            - Tempo : {tempo_val:.1f} BPM
            - Énergie (RMS) : {avg_rms:.4f}
            - Brillance (Spectral Centroid) : {avg_cent:.1f} Hz
            
            Donne ton avis professionnel sur le "Hit Potential" (Note sur 10) et ce qu'il faudrait améliorer pour que ce soit un tube grand public.
            """
            
            if self.llm:
                review = await self.llm.generate(
                    prompt,
                    system_prompt="Tu es un A&R strict mais visionnaire."
                )
            else:
                review = f"Analyse basique (LLM off): Morceau à {tempo_val:.1f} BPM avec une énergie de {avg_rms:.4f}."
                
            task.output_data = {
                "features": {
                    "tempo": tempo_val,
                    "rms_energy": avg_rms,
                    "brightness": avg_cent
                },
                "review": review
            }
            
            task.status = "completed"
        except Exception as e:
            task = await self.handle_error(task, e)

        return task
