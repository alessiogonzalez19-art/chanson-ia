"""
Agent 11: Le Gardien
Surveillance, auto-correction et maintenance du système.
"""

import asyncio
from typing import Dict, Any, Optional
from loguru import logger

from agents.base import StudioAgent, AgentTask

class Gardien(StudioAgent):
    """
    Agent autonome qui surveille les logs et corrige les erreurs en temps réel.
    """

    def __init__(self, model_manager=None):
        super().__init__(
            agent_id=11,
            name="Le Gardien",
            role="Surveillance et Auto-correction",
            model_manager=model_manager
        )
        self.llm = None

    async def initialize(self):
        if self.model_manager:
            self.llm = await self.model_manager.load_orchestrator()
            logger.info("🛡️ Gardien LLM loaded (DeepSeek class)")

    async def process(self, task: AgentTask) -> AgentTask:
        task.status = "processing"
        logger.info(f"🛡️ Gardien en action: {task.task_id}")

        try:
            error_log = task.input_data.get("error_log", "")
            file_path = task.input_data.get("file_path", "")

            if error_log:
                fix_plan = await self._analyze_error(error_log, file_path)
                applied = await self._apply_fix(fix_plan, file_path)
                task.output_data = {
                    "action": "analyzed_error",
                    "fix_plan": fix_plan,
                    "applied": applied
                }
            else:
                task.output_data = {"message": "Aucune erreur fournie."}

            task.status = "completed"
        except Exception as e:
            task = await self.handle_error(task, e)

        return task

    async def _analyze_error(self, error_log: str, file_path: str) -> str:
        prompt = f"""
        Tu es le Gardien d'un Studio d'IA. Une erreur est survenue :
        Fichier : {file_path}
        Log :
        {error_log}

        Propose le code Python complet et corrigé pour ce fichier.
        """
        if self.llm:
            response = await self.llm.generate(
                prompt,
                system_prompt="Tu es l'agent de maintenance. Retourne uniquement le code corrigé sans explication (dans un bloc de code)."
            )
            return response
        return "Analyse impossible sans LLM."

    async def _apply_fix(self, fix_plan: str, file_path: str) -> bool:
        import re
        import shutil
        from pathlib import Path
        import sys

        # Extract code from LLM response
        code_blocks = re.findall(r"```(?:python)?(.*?)```", fix_plan, re.DOTALL)
        if not code_blocks:
            logger.warning("Aucun bloc de code trouvé pour la correction.")
            return False

        new_code = code_blocks[0].strip()
        target_file = Path(file_path)

        if target_file.exists() and new_code:
            try:
                # 1. Backup
                backup_path = target_file.with_suffix(target_file.suffix + ".bak")
                shutil.copy2(target_file, backup_path)
                logger.info(f"🛡️ Backup créé : {backup_path}")

                # 2. Overwrite
                with open(target_file, "w", encoding="utf-8") as f:
                    f.write(new_code)
                logger.info(f"🛡️ Fichier corrigé : {target_file}")

                # 3. Restart Services (Simulation for security but ready for prod)
                logger.warning("🔄 Le Gardien initie un redémarrage des services (Simulation)")
                # os.execl(sys.executable, sys.executable, *sys.argv)
                return True
            except Exception as e:
                logger.error(f"Échec de l'application de la correction: {e}")
                return False
        return False
