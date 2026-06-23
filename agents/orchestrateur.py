"""
Agent 1: L'Orchestrateur
Master coordinator using the local agent team.
"""

import json
from typing import Dict, List, Optional, Type
from loguru import logger

from agents.base import StudioAgent, AgentTask


class Orchestrateur(StudioAgent):
    """Master workflow coordinator."""

    def __init__(self, model_manager=None):
        super().__init__(
            agent_id=1,
            name="L'Orchestrateur",
            role="Workflow Coordination & Task Distribution",
            model_manager=model_manager,
        )
        self.agents: Dict[int, StudioAgent] = {}
        self.workflows = {}
        self.agent_classes = self._build_agent_registry()
        self.llm = None

    async def initialize(self):
        """Load orchestrator LLM when a model manager is available."""
        if self.model_manager:
            self.llm = await self.model_manager.load_orchestrator()
            logger.info("Orchestrateur LLM loaded")

    async def process(self, task: AgentTask) -> AgentTask:
        """Coordinate an end-to-end production workflow."""
        task.status = "processing"
        logger.info(f"Orchestrateur processing: {task.task_id}")

        try:
            project_data = task.input_data
            plan = await self._create_production_plan(project_data)
            results = await self._execute_workflow(plan, project_data)
            task.output_data = await self._collect_results(results)
            task.status = "completed"
        except Exception as e:
            task = await self.handle_error(task, e)

        return task

    async def _create_production_plan(self, project_data: Dict) -> Dict:
        """Create a production plan with the LLM, falling back to a deterministic plan."""
        prompt = f"""
Create a detailed music production plan for:

Project: {project_data.get('name', 'Untitled')}
Description: {project_data.get('description', 'No description')}
Genre: {project_data.get('genre', 'Electronic')}
Reference Tracks: {project_data.get('references', [])}

Return JSON with workflow and parameters.
"""

        if self.llm is not None:
            response = await self.llm.generate(
                prompt,
                system_prompt="You are a world-class music producer planning a studio session.",
            )
            try:
                import re

                json_match = re.search(r"\{.*\}", response, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
            except Exception as e:
                logger.warning(f"Production plan JSON parse failed: {e}")

        workflow = ["generation", "arrangement", "mixing", "mastering", "quality_control"]
        if project_data.get("audio_files"):
            workflow = ["analysis", "separation", "mixing", "mastering", "quality_control"]

        return {
            "workflow": workflow,
            "parameters": {
                "bpm": project_data.get("bpm") or 128,
                "key": project_data.get("key") or "C minor",
                "duration": project_data.get("duration") or 180,
            },
        }

    async def _execute_workflow(self, plan: Dict, project_data: Dict) -> List[Dict]:
        """Execute production workflow across real local agents."""
        workflow_steps = plan.get("workflow", [])
        results: List[Dict] = []

        for step in workflow_steps:
            logger.info(f"Executing step: {step}")
            step_task = AgentTask(
                task_type=step,
                input_data={
                    **project_data,
                    "plan": plan,
                    "previous_results": results,
                },
            )
            result = await self._dispatch_to_agent(step, step_task)
            results.append(result)

        return results

    async def _dispatch_to_agent(self, step: str, task: AgentTask) -> Dict:
        """Dispatch a task to the corresponding local agent."""
        agent_mapping = {
            "analysis": 2,
            "separation": 3,
            "generation": 4,
            "arrangement": 5,
            "mixing": 6,
            "mastering": 7,
            "dj_transitions": 8,
            "vocals": 9,
            "quality_control": 10,
        }

        agent_id = agent_mapping.get(step)
        if agent_id is None:
            return {
                "step": step,
                "agent_id": None,
                "status": "failed",
                "output": None,
                "error": f"Etape inconnue: {step}",
            }

        logger.info(f"Dispatching {step} to Agent {agent_id}")
        agent = await self._get_agent(agent_id)
        if agent is None:
            return {
                "step": step,
                "agent_id": agent_id,
                "status": "failed",
                "output": None,
                "error": f"Aucun agent executable branche pour l'etape '{step}'.",
            }

        self._hydrate_step_input(step, task)
        processed = await agent.process(task)
        output_files = self._extract_output_files(processed.output_data)

        return {
            "step": step,
            "agent_id": agent_id,
            "status": processed.status,
            "output": processed.output_data,
            "error": processed.error,
            "output_files": output_files,
            "quality_score": self._extract_quality_score(processed.output_data),
        }

    def _hydrate_step_input(self, step: str, task: AgentTask) -> None:
        if "audio_files" in task.input_data and "audio_path" not in task.input_data:
            audio_files = task.input_data.get("audio_files") or []
            if audio_files:
                task.input_data["audio_path"] = audio_files[0]

        if step == "generation":
            task.input_data.setdefault(
                "prompt",
                task.input_data.get("description")
                or task.input_data.get("genre")
                or "Electronic music",
            )
        elif step in {"mastering", "mixing"}:
            output_files = self._collect_previous_output_files(task.input_data.get("previous_results", []))
            if output_files:
                task.input_data.setdefault("audio_path", output_files[-1])
        elif step == "quality_control":
            output_files = self._collect_previous_output_files(task.input_data.get("previous_results", []))
            if output_files:
                task.input_data.setdefault("audio_files", output_files)

    def _build_agent_registry(self) -> Dict[int, Type[StudioAgent]]:
        from agents.analyste import Analyste
        from agents.chirurgien import Chirurgien
        from agents.compositeur import Compositeur
        from agents.arrangeur import Arrangeur
        from agents.ingenieur_son import IngenieurSon
        from agents.mastering import MasteringEngineer
        from agents.dj_pro import DJPro
        from agents.expert_vocal import ExpertVocal
        from agents.superviseur import Superviseur

        return {
            2: Analyste,
            3: Chirurgien,
            4: Compositeur,
            5: Arrangeur,
            6: IngenieurSon,
            7: MasteringEngineer,
            8: DJPro,
            9: ExpertVocal,
            10: Superviseur,
        }

    async def _get_agent(self, agent_id: int) -> Optional[StudioAgent]:
        if agent_id in self.agents:
            return self.agents[agent_id]

        agent_cls = self.agent_classes.get(agent_id)
        if agent_cls is None:
            return None

        agent = agent_cls(model_manager=self.model_manager)
        await agent.initialize()
        self.agents[agent_id] = agent
        return agent

    async def _collect_results(self, results: List[Dict]) -> Dict:
        """Collect and validate all agent results."""
        output_files: List[str] = []
        for result in results:
            output_files.extend(result.get("output_files", []) or [])

        quality_scores = [
            r.get("quality_score", 0.0)
            for r in results
            if isinstance(r.get("quality_score"), (int, float)) and r.get("quality_score", 0.0) > 0
        ]

        return {
            "project_completed": all(r.get("status") == "completed" for r in results),
            "steps_completed": len([r for r in results if r.get("status") == "completed"]),
            "steps_total": len(results),
            "output_files": output_files,
            "quality_score": sum(quality_scores) / len(quality_scores) if quality_scores else 0.0,
            "pending_steps": [r["step"] for r in results if r.get("status") != "completed"],
            "results": results,
        }

    def _collect_previous_output_files(self, results: List[Dict]) -> List[str]:
        files: List[str] = []
        for result in results:
            files.extend(self._extract_output_files(result.get("output", result)))
            files.extend(result.get("output_files", []) or [])
        return list(dict.fromkeys(files))

    def _extract_output_files(self, payload) -> List[str]:
        if not isinstance(payload, dict):
            return []

        files: List[str] = []
        for key in ("output_file", "final_mix", "remix_path", "generated_audio"):
            value = payload.get(key)
            if isinstance(value, str):
                files.append(value)

        output_files = payload.get("output_files")
        if isinstance(output_files, dict):
            files.extend(str(path) for path in output_files.values())
        elif isinstance(output_files, list):
            files.extend(str(path) for path in output_files)

        return list(dict.fromkeys(files))

    def _extract_quality_score(self, payload) -> float:
        if not isinstance(payload, dict):
            return 0.0
        value = payload.get("quality_score") or payload.get("overall_score") or 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
