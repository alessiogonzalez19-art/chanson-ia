"""
Agent 13: Le Chef Suprême
Orchestrateur global qui gère la réflexion collective et la distribution finale des tâches.
"""

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from loguru import logger
from typing import Dict, List, Optional

from agents.base import StudioAgent, AgentTask
from agents.reflection import trigger_collective_reflection
from config import config

class ChefSupreme(StudioAgent):
    """
    Le Chef Suprême qui lance la réflexion collective, fusionne les rapports, 
    et orchestre l'exécution finale.
    """

    def __init__(self, model_manager=None, agents_registry: Dict[int, StudioAgent] = None):
        super().__init__(
            agent_id=13,
            name="Le Chef Suprême",
            role="Orchestration Globale et Décision",
            model_manager=model_manager
        )
        self.llm = None
        self.agents_registry = agents_registry or {}
        self.plans_dir = config.workspace_root / "plans"
        self.plans_dir.mkdir(parents=True, exist_ok=True)

    async def initialize(self):
        if self.model_manager:
            self.llm = await self.model_manager.load_orchestrator()
            logger.info("👑 Chef Suprême LLM loaded (DeepSeek class)")

    async def process(self, task: AgentTask) -> AgentTask:
        task.status = "processing"
        logger.info(f"👑 Le Chef Suprême prend le contrôle: {task.task_id}")

        try:
            context = task.input_data.get("context", {})
            user_request = task.input_data.get("request", "")
            
            # 1. Lancer la réflexion collective (si la demande est complexe)
            agents_to_consult = [a for a in self.agents_registry.values() if a.agent_id not in (11, 13)]
            
            reflection_results = []
            if len(agents_to_consult) > 0:
                reflection_results = await trigger_collective_reflection(
                    agents_to_consult, 
                    context={"project_name": "Studio IA V0", "request": user_request}, 
                    timeout=60
                )

            # 2. Fusionner et créer le Plan Global
            global_plan = await self._create_global_plan(user_request, reflection_results)
            
            # Sauvegarder le plan
            plan_path = self._save_plan(global_plan)
            
            # 3. Distribuer les tâches
            logger.info("👑 Distribution des tâches aux agents...")
            
            # Analyse basique du plan pour trouver quelles tâches lancer
            # Dans un vrai scénario, le LLM renverrait un JSON strict avec les celery tasks à appeler
            tasks_launched = []
            plan_lower = global_plan.lower()
            
            # Import tardif pour éviter les boucles circulaires
            try:
                from workers.celery_app import celery_app
                
                # Exemple de parsing: si le plan parle de scraper
                if "scraper" in plan_lower or "agent 12" in plan_lower:
                    t = celery_app.send_task("scrape_library_track", args=["sample générique d'après le plan"])
                    tasks_launched.append({"agent": 12, "task_id": t.id})
                    
                # Si le plan parle de génération
                if "générer" in plan_lower or "compositeur" in plan_lower or "agent 4" in plan_lower:
                    t = celery_app.send_task("generate_library_track", args=[user_request, 30])
                    tasks_launched.append({"agent": 4, "task_id": t.id})
                    
                # Autre exemple: séparation
                if "isoler" in plan_lower or "chirurgien" in plan_lower or "agent 3" in plan_lower:
                    # Necessite un path audio. On utiliserait task.input_data.get("audio_path")
                    audio = task.input_data.get("audio_path")
                    if audio:
                        t = celery_app.send_task("separate_stems", args=[audio])
                        tasks_launched.append({"agent": 3, "task_id": t.id})
            except Exception as e:
                logger.error(f"Impossible de lancer les tâches Celery : {e}")
            
            task.output_data = {
                "message": "Plan global créé et distribué avec succès.",
                "global_plan": global_plan,
                "plan_path": str(plan_path),
                "reflection_count": len(reflection_results),
                "tasks_launched": tasks_launched
            }
            
            task.status = "completed"
        except Exception as e:
            task = await self.handle_error(task, e)

        return task

    async def _create_global_plan(self, user_request: str, reflection_results: List[Dict]) -> str:
        """Génère un plan global en fusionnant les idées des agents."""
        logger.info("👑 Synthèse des rapports des agents...")
        
        prompt = f"""
        Demande utilisateur : {user_request}
        
        Rapports des agents :
        {json.dumps(reflection_results, indent=2, ensure_ascii=False)}
        
        En tant que Chef Suprême, crée un plan d'action unifié, étape par étape.
        Assigne clairement chaque étape à un agent (Ex: 'Agent 4: Générer un beat').
        """
        
        if self.llm:
            response = await self.llm.generate(
                prompt,
                system_prompt="Tu es le Chef Suprême, le producteur exécutif qui prend les décisions finales."
            )
            return response
            
        # Fallback si pas de LLM
        return f"Plan de base (pas de LLM):\n1. Analyser la requête: {user_request}\n2. Exécuter la tâche par l'agent concerné."

    def _save_plan(self, plan_text: str) -> Path:
        """Sauvegarde le plan généré dans le dossier des plans."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"plan_{timestamp}.txt"
        file_path = self.plans_dir / filename
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(plan_text)
            
        logger.info(f"💾 Plan sauvegardé : {file_path}")
        return file_path
