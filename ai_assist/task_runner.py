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
            # Detect and execute MCP prompts vs natural language
            if self.task_def.is_mcp_prompt:
                server_name, prompt_name = self.task_def.parse_mcp_prompt()
                output = await self.agent.execute_mcp_prompt(
                    server_name, prompt_name, self.task_def.prompt_arguments, max_turns=self.task_def.max_turns
                )
            else:
                # Existing natural language path
                output = await self.agent.query(self.task_def.prompt, max_turns=self.task_def.max_turns)

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

            result = TaskResult(
                task_name=self.task_def.name, success=True, output=output, timestamp=timestamp, metadata=metadata
            )

            # Dispatch notification if configured
            if self.task_def.notify:
                await self._send_notification(result)

            return result

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

            result = TaskResult(
                task_name=self.task_def.name, success=False, output=error_msg, timestamp=timestamp, metadata={}
            )

            # Dispatch notification if configured
            if self.task_def.notify:
                await self._send_notification(result)

            return result

    def get_last_run(self) -> datetime | None:
        """Get timestamp of last successful run"""
        state = self.state_manager.get_monitor_state(self.state_key)
        return state.last_check

    def get_history(self, limit: int = 10) -> list[dict]:
        """Get historical execution results"""
        return self.state_manager.get_history(self.state_key, limit=limit)

    async def _send_notification(self, result: TaskResult):
        """Send notification for task completion"""
        from ai_assist.notification_dispatcher import Notification, NotificationDispatcher

        # Determine notification level
        level = "success" if result.success else "error"

        # Truncate output for notification (max 500 chars)
        message = result.output[:500] if result.output else "No output"

        # Create notification
        notification = Notification(
            id=f"task-{self.task_def.name}-{int(result.timestamp.timestamp() * 1000)}",
            action_id=self.task_def.name,
            title=f"Task: {self.task_def.name}",
            message=message,
            level=level,
            timestamp=result.timestamp,
            channels=self.task_def.notification_channels,
            delivered={},
        )

        # Dispatch
        dispatcher = NotificationDispatcher()
        await dispatcher.dispatch(notification)
