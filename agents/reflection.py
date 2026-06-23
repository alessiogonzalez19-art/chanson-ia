"""
Système de Réflexion Collective.
Fait réfléchir plusieurs agents en parallèle pendant 60 secondes max.
"""

import asyncio
import json
from loguru import logger
from typing import List, Dict

from agents.base import AgentTask, StudioAgent

async def _agent_reflection(agent: StudioAgent, context: Dict) -> Dict:
    """Demande à un agent de réfléchir sur un contexte."""
    # Simulation du temps de réflexion ou appel réel à un LLM avec le contexte
    try:
        # Si l'agent a un LLM initialisé, on pourrait lui faire générer une réponse.
        # Pour le moment, on retourne un plan fictif de l'agent.
        logger.info(f"🧠 {agent.name} réfléchit...")
        
        # Simuler un délai asynchrone (l'agent "réfléchit")
        await asyncio.sleep(1)
        
        return {
            "agent_id": agent.agent_id,
            "agent_name": agent.name,
            "plan": f"Plan proposé par {agent.name} pour {context.get('project_name', 'ce projet')}",
            "observations": [f"Le projet semble être du genre {context.get('genre', 'inconnu')}."],
            "suggestions": ["Utiliser des samples de haute qualité."]
        }
    except Exception as e:
        logger.error(f"Erreur de réflexion pour {agent.name}: {e}")
        return {
            "agent_id": getattr(agent, 'agent_id', -1),
            "error": str(e)
        }

async def trigger_collective_reflection(agents: List[StudioAgent], context: Dict, timeout: int = 60) -> List[Dict]:
    """
    Lance la réflexion pour tous les agents en parallèle.
    Attend maximum `timeout` secondes.
    """
    logger.info(f"⏳ Début de la réflexion collective (Max {timeout}s) avec {len(agents)} agents...")
    
    tasks = []
    for agent in agents:
        tasks.append(_agent_reflection(agent, context))
        
    try:
        # On exécute toutes les tâches en parallèle avec un timeout global
        results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=timeout)
        
        # Filtrer les exceptions
        valid_results = []
        for res in results:
            if isinstance(res, Exception):
                logger.warning(f"Un agent a échoué pendant la réflexion: {res}")
            else:
                valid_results.append(res)
                
        logger.info("✅ Réflexion collective terminée.")
        return valid_results
        
    except asyncio.TimeoutError:
        logger.error(f"⏰ Timeout de la réflexion collective atteint ({timeout}s).")
        return []
