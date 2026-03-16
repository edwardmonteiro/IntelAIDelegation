"""Protocol for adaptive coordination.

The coordinator consumes monitoring events and makes dynamic decisions:
  - Continue: Task is on track, no action needed.
  - Intervene: Send guidance or adjust parameters.
  - Pause: Temporarily halt execution.
  - Re-delegate: Terminate the current assignment and find a backup agent.
  - Cancel: Abandon the task entirely.

This replaces static plans with adaptive, event-driven orchestration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from intel_ai_delegation.monitoring.protocol import MonitoringEvent


class ActionType(Enum):
    """Types of coordination actions."""

    CONTINUE = "continue"
    INTERVENE = "intervene"
    PAUSE = "pause"
    RESUME = "resume"
    RE_DELEGATE = "re_delegate"
    CANCEL = "cancel"


@dataclass
class CoordinationAction:
    """A decision made by the coordinator in response to monitoring events.

    Attributes:
        action_type: What kind of action to take.
        task_id: The affected task.
        reason: Why this action was chosen.
        target_agent_id: For RE_DELEGATE, the backup agent to assign to.
        parameters: Additional action-specific data.
    """

    action_type: ActionType
    task_id: str
    reason: str = ""
    target_agent_id: str | None = None
    parameters: dict = None

    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}


class Coordinator(ABC):
    """Abstract base for adaptive coordination logic.

    The coordinator is the decision-making layer that reacts to
    monitoring signals and maintains overall task execution health.
    """

    @abstractmethod
    async def evaluate(self, events: list[MonitoringEvent]) -> CoordinationAction:
        """Evaluate a batch of monitoring events and decide on an action.

        Args:
            events: Recent monitoring events to evaluate.

        Returns:
            The coordination action to take.
        """
        ...

    @abstractmethod
    async def execute_action(self, action: CoordinationAction) -> None:
        """Execute a coordination action.

        This may involve pausing a task, terminating a contract,
        re-advertising on the market hub, etc.

        Args:
            action: The action to execute.
        """
        ...

    @abstractmethod
    async def get_backup_agents(self, task_id: str) -> list[str]:
        """Identify backup agents for potential re-delegation.

        Args:
            task_id: The task that may need a new agent.

        Returns:
            List of agent IDs suitable for re-delegation, ranked by fit.
        """
        ...
