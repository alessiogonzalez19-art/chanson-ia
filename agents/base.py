"""
Base Agent Class
Foundation for all 10 AI agents
"""

import asyncio
import uuid
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger


@dataclass
class AgentTask:
    """Task for an agent to process"""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_type: str = ""
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending, processing, completed, failed
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class StudioAgent:
    """Base class for all studio agents"""
    
    def __init__(self, agent_id: int, name: str, role: str, model_manager=None):
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.model_manager = model_manager
        self.current_task: Optional[AgentTask] = None
        self.processing_history: list = []
        
        logger.info(f"🤖 Agent {agent_id}: {name} - {role}")
    
    async def initialize(self):
        """Initialize agent resources"""
        pass
    
    async def process(self, task: AgentTask) -> AgentTask:
        """Process a task - override in subclasses"""
        raise NotImplementedError(f"Agent {self.name} must implement process()")
    
    async def validate_input(self, task: AgentTask) -> bool:
        """Validate task input data"""
        return True
    
    async def handle_error(self, task: AgentTask, error: Exception) -> AgentTask:
        """Handle processing errors"""
        task.status = "failed"
        task.error = str(error)
        logger.error(f"❌ Agent {self.name} failed: {error}")
        return task
    
    async def cleanup(self):
        """Cleanup resources"""
        pass
    
    def get_status(self) -> Dict:
        """Get agent status"""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "role": self.role,
            "current_task": self.current_task.task_id if self.current_task else None,
            "history_count": len(self.processing_history)
        }