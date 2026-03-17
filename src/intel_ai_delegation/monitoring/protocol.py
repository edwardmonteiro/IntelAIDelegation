"""Protocol for dynamic monitoring of delegated tasks.

Monitoring operates at two levels:
  - Outcome-level: Check the final result against verification criteria.
  - Process-level: Continuously track intermediate steps for high-stakes tasks.

The monitor emits events that the adaptive coordination layer consumes
to decide whether to continue, pause, or re-delegate.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class EventSeverity(Enum):
    """Severity of a monitoring event."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class MonitoringEvent:
    """A discrete monitoring observation.

    Attributes:
        event_id: Unique identifier.
        task_id: The task being monitored.
        contract_id: The associated contract.
        severity: How concerning this event is.
        event_type: Category (e.g., "progress", "quality_check", "timeout_warning").
        message: Human-readable description.
        data: Structured data payload.
        timestamp: When the event occurred.
    """

    task_id: str
    event_type: str
    message: str
    contract_id: str = ""
    severity: EventSeverity = EventSeverity.INFO
    data: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)


class Monitor(ABC):
    """Abstract base for task monitoring.

    Implementations can range from simple polling to real-time
    stream-based observation systems.
    """

    @abstractmethod
    async def start_monitoring(self, task_id: str, contract_id: str) -> None:
        """Begin monitoring a task under a given contract.

        Args:
            task_id: The task to monitor.
            contract_id: The governing contract (contains SLA thresholds).
        """
        ...

    @abstractmethod
    async def stop_monitoring(self, task_id: str) -> None:
        """Stop monitoring a task.

        Args:
            task_id: The task to stop monitoring.
        """
        ...

    @abstractmethod
    async def report_progress(
        self, task_id: str, progress: float, message: str = ""
    ) -> MonitoringEvent:
        """Report progress on a task (called by the delegatee).

        Args:
            task_id: The task being worked on.
            progress: Completion ratio in [0, 1].
            message: Optional status message.

        Returns:
            The generated monitoring event.
        """
        ...

    @abstractmethod
    async def check_health(self, task_id: str) -> MonitoringEvent:
        """Perform a health check on a monitored task.

        This is used for process-level monitoring of high-stakes tasks.

        Args:
            task_id: The task to check.

        Returns:
            A monitoring event describing the current health.
        """
        ...

    @abstractmethod
    async def get_events(
        self, task_id: str, since: datetime | None = None
    ) -> list[MonitoringEvent]:
        """Retrieve monitoring events for a task.

        Args:
            task_id: The task to query.
            since: Only return events after this timestamp.

        Returns:
            List of events, ordered chronologically.
        """
        ...
