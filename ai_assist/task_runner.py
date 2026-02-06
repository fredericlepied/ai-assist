"""Execute user-defined tasks and track state"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .agent import AiAssistAgent
from .conditions import ActionExecutor, ConditionEvaluator
from .state import StateManager
from .tasks import TaskDefinition


@dataclass
class TaskResult:
    """Result from executing a task"""

    task_name: str
    success: bool
    output: str
    timestamp: datetime
    metadata: dict[str, Any]  # Extracted values for conditions


class TaskRunner:
    """Execute a user-defined task and track its state"""

    def __init__(self, task_def: TaskDefinition, agent: AiAssistAgent, state_manager: StateManager):
        self.task_def = task_def
        self.agent = agent
        self.state_manager = state_manager
        self.state_key = self._get_state_key()

    def _get_state_key(self) -> str:
        """Generate state key for this task"""
        # Sanitize task name for use in filenames
        sanitized = "".join(c if c.isalnum() or c in "-_" else "_" for c in self.task_def.name)
        return f"task_{sanitized}"

    async def run(self) -> TaskResult:
        """Execute the task and return results"""
        timestamp = datetime.now()

        try:
            output = await self.agent.query(self.task_def.prompt)

            evaluator = ConditionEvaluator()
            metadata = evaluator.extract_metadata(output)

            if self.task_def.conditions:
                executor = ActionExecutor(self.agent, self.state_manager)

                for condition in self.task_def.conditions:
                    if "if" in condition and "then" in condition:
                        if evaluator.evaluate(condition["if"], metadata):
                            context = {
                                "result": output,
                                "metadata": metadata,
                                "task_name": self.task_def.name,
                            }
                            await executor.execute(condition["then"], context)

            self.state_manager.update_monitor(
                self.state_key,
                {
                    "task_name": self.task_def.name,
                    "last_success": True,
                    "last_output_length": len(output),
                    "last_metadata": metadata,
                },
            )

            self.state_manager.append_history(
                self.state_key,
                {
                    "task_name": self.task_def.name,
                    "success": True,
                    "timestamp": timestamp.isoformat(),
                    "metadata": metadata,
                },
            )

            return TaskResult(
                task_name=self.task_def.name, success=True, output=output, timestamp=timestamp, metadata=metadata
            )

        except Exception as e:
            error_msg = str(e)
            self.state_manager.update_monitor(
                self.state_key,
                {
                    "task_name": self.task_def.name,
                    "last_success": False,
                    "last_error": error_msg,
                },
            )

            self.state_manager.append_history(
                self.state_key,
                {
                    "task_name": self.task_def.name,
                    "success": False,
                    "error": error_msg,
                    "timestamp": timestamp.isoformat(),
                },
            )

            return TaskResult(
                task_name=self.task_def.name, success=False, output=error_msg, timestamp=timestamp, metadata={}
            )

    def get_last_run(self) -> datetime | None:
        """Get timestamp of last successful run"""
        state = self.state_manager.get_monitor_state(self.state_key)
        return state.last_check

    def get_history(self, limit: int = 10) -> list[dict]:
        """Get historical execution results"""
        return self.state_manager.get_history(self.state_key, limit=limit)
