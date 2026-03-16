"""Protocol for the Trust and Reputation system.

Agent performance history is recorded on an immutable ledger. Trust scores
are dynamic and influence future task assignments. The system supports
both quantitative metrics and qualitative reviews.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ReputationRecord:
    """An immutable record of an agent's performance on a task.

    Attributes:
        record_id: Unique identifier.
        agent_id: The agent being evaluated.
        task_id: The task that was performed.
        contract_id: The governing contract.
        outcome: Whether the task succeeded, failed, or was breached.
        quality_score: Quality metric in [0, 1].
        timeliness_score: Whether deadlines were met, in [0, 1].
        cost_efficiency: Actual vs. proposed cost ratio.
        reviewer_id: Who submitted this record (delegator or third party).
        notes: Free-form review notes.
        recorded_at: When this record was created.
        metadata: Extensible data.
    """

    agent_id: str
    task_id: str
    outcome: str
    contract_id: str = ""
    quality_score: float = 1.0
    timeliness_score: float = 1.0
    cost_efficiency: float = 1.0
    reviewer_id: str = ""
    notes: str = ""
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    recorded_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TrustScore:
    """Aggregated trust metrics for an agent.

    Attributes:
        agent_id: The agent.
        overall: Composite trust score in [0, 1].
        reliability: Track record of completing tasks.
        quality: Average quality of delivered work.
        timeliness: Track record of meeting deadlines.
        total_tasks: Number of tasks in the history.
        updated_at: When this score was last computed.
    """

    agent_id: str
    overall: float = 0.5
    reliability: float = 0.5
    quality: float = 0.5
    timeliness: float = 0.5
    total_tasks: int = 0
    updated_at: datetime = field(default_factory=datetime.utcnow)


class TrustLedger(ABC):
    """Abstract base for the trust and reputation ledger.

    The ledger is append-only (immutable). Trust scores are computed
    from the full history of reputation records.
    """

    @abstractmethod
    async def record(self, record: ReputationRecord) -> None:
        """Append a reputation record to the ledger.

        Records are immutable once written.

        Args:
            record: The performance record to store.
        """
        ...

    @abstractmethod
    async def get_trust_score(self, agent_id: str) -> TrustScore:
        """Compute the current trust score for an agent.

        The score is derived from the agent's full history of
        reputation records on the ledger.

        Args:
            agent_id: The agent to evaluate.

        Returns:
            The computed trust score.
        """
        ...

    @abstractmethod
    async def get_history(
        self, agent_id: str, limit: int = 100
    ) -> list[ReputationRecord]:
        """Retrieve an agent's reputation history.

        Args:
            agent_id: The agent to query.
            limit: Maximum number of records to return.

        Returns:
            List of records, most recent first.
        """
        ...

    @abstractmethod
    async def get_record(self, record_id: str) -> ReputationRecord:
        """Retrieve a specific reputation record.

        Args:
            record_id: The record to retrieve.

        Returns:
            The reputation record.

        Raises:
            LedgerError: If not found.
        """
        ...


class LedgerError(Exception):
    """Raised when a ledger operation fails."""
