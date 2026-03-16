"""Task model — the fundamental unit of work in the delegation framework.

A Task represents a discrete unit of work that can be delegated, decomposed
into sub-tasks, monitored, and verified upon completion. Tasks are recursively
decomposable until their outcomes can be strictly and precisely verified.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any


class TaskStatus(Enum):
    """Lifecycle states of a task.

    Aligned with the paper's execution flow: Pending -> Bidding ->
    In_Progress -> Under_Verification -> Completed/Failed/Disputed.
    """

    PENDING = "pending"
    BIDDING = "bidding"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    UNDER_VERIFICATION = "under_verification"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DISPUTED = "disputed"
    RE_DELEGATED = "re_delegated"


class TaskCriticality(Enum):
    """Criticality level — determines permission gating and oversight depth.

    High-criticality tasks receive process-level monitoring and require
    human escalation on failure. Low-criticality tasks use outcome-level
    checks and support automatic re-delegation.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskPriority(Enum):
    """Priority levels that influence scheduling and market bidding."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class VerificationCriteria:
    """Defines how a task's outcome should be verified.

    Attributes:
        method: The verification approach — "direct_inspection",
                "third_party_audit", "cryptographic_zk_proof",
                "consensus_game", or "automated_test".
        specification: A formal or semi-formal description of the expected outcome.
        acceptance_threshold: Numeric threshold for acceptance (e.g., accuracy >= 0.95).
        timeout: Maximum time allowed for verification.
    """

    method: str
    specification: str
    acceptance_threshold: float = 1.0
    timeout: timedelta | None = None


@dataclass
class ResourceRequirements:
    """Resources an agent needs to execute a task.

    Attributes:
        capabilities: List of required capability identifiers.
        max_cost: Maximum budget in abstract cost units.
        max_duration: Maximum wall-clock time for execution.
        required_permissions: Permission scopes the agent will need.
    """

    capabilities: list[str] = field(default_factory=list)
    max_cost: float | None = None
    max_duration: timedelta | None = None
    required_permissions: list[str] = field(default_factory=list)


@dataclass
class Task:
    """A unit of work that can be delegated within the framework.

    Tasks follow a contract-first approach: they must declare their
    verification criteria upfront so that outcomes are objectively assessable.

    Attributes:
        task_id: Globally unique identifier.
        name: Human-readable short name.
        description: Detailed description of what the task accomplishes.
        status: Current lifecycle state.
        criticality: Determines oversight level and failure-handling policy.
        reversible: If True, failures trigger automatic re-delegation.
            If False, failures escalate to a human immediately.
        priority: Scheduling priority.
        parent_id: ID of the parent task if this is a sub-task
            (supports recursive sub-delegation chains).
        sub_task_ids: IDs of child tasks produced by decomposition.
        verification: How to verify successful completion.
        resources: Resource requirements for execution.
        input_data: Arbitrary input payload for the task.
        output_data: Arbitrary output payload upon completion.
        delegator_id: DID of the agent or human who created/delegated the task.
        assignee_id: DID of the agent currently assigned.
        created_at: Timestamp of creation.
        updated_at: Timestamp of last status change.
        deadline: Hard deadline for completion.
        metadata: Extensible key-value metadata.
    """

    name: str
    description: str
    verification: VerificationCriteria
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: TaskStatus = TaskStatus.PENDING
    criticality: TaskCriticality = TaskCriticality.MEDIUM
    reversible: bool = True
    priority: TaskPriority = TaskPriority.MEDIUM
    parent_id: str | None = None
    sub_task_ids: list[str] = field(default_factory=list)
    resources: ResourceRequirements = field(default_factory=ResourceRequirements)
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    delegator_id: str | None = None
    assignee_id: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    deadline: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_leaf(self) -> bool:
        """A leaf task has no sub-tasks and is directly executable."""
        return len(self.sub_task_ids) == 0

    @property
    def is_terminal(self) -> bool:
        """A terminal task is in a final state."""
        return self.status in {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
