"""
Agent 16: L'Ingénieur VST
Contrôle des plugins externes (VST3/AU) via Pedalboard.
"""

from pathlib import Path
from loguru import logger
import soundfile as sf

try:
    from pedalboard import Pedalboard, load_plugin
    PEDALBOARD_AVAILABLE = True
except ImportError:
    PEDALBOARD_AVAILABLE = False

from agents.base import StudioAgent, AgentTask
from config import config

class IngenieurVST(StudioAgent):
    """
    Agent qui charge des plugins VST externes et y fait passer l'audio.
    """

    def __init__(self, model_manager=None):
        super().__init__(
            agent_id=16,
            name="L'Ingénieur VST",
            role="Manipulation de Plugins Externes",
            model_manager=model_manager
        )
        self.output_dir = config.workspace_root / "vst_renders"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def process(self, task: AgentTask) -> AgentTask:
        task.status = "processing"
        logger.info(f"🎛️ L'Ingénieur VST charge les plugins: {task.task_id}")

        try:
            audio_path = task.input_data.get("audio_path")
            vst_path = task.input_data.get("vst_path") # Chemin absolu vers le .vst3 ou .dll
            
            if not audio_path or not Path(audio_path).exists():
                raise ValueError("Fichier audio introuvable.")
                
            if not vst_path or not Path(vst_path).exists():
                raise ValueError(f"Fichier VST introuvable à {vst_path}.")

            if not PEDALBOARD_AVAILABLE:
                raise ImportError("La librairie 'pedalboard' n'est pas installée.")

            # Chargement de l'audio
            audio_data, sample_rate = sf.read(audio_path)
            
            # Chargement du plugin VST
            logger.info(f"Chargement du plugin VST: {vst_path}")
            plugin = load_plugin(vst_path)
            
            # On pourrait exposer les paramètres du VST ici
            # ex: plugin.mix = 0.5
            
            board = Pedalboard([plugin])
            
            # Processing
            logger.info("Rendu audio via le VST...")
            effected_audio = board(audio_data, sample_rate)
            
            out_filename = Path(audio_path).stem + f"_{Path(vst_path).stem}.wav"
            out_path = self.output_dir / out_filename
            
            sf.write(str(out_path), effected_audio, sample_rate)
            
            logger.info(f"🎛️ Rendu VST terminé: {out_path}")
            
            task.output_data = {
                "message": "Processing VST terminé.",
                "output_path": str(out_path)
            }
            
            task.status = "completed"
        except Exception as e:
            task = await self.handle_error(task, e)

        return task
