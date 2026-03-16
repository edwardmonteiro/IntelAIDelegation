"""Agent model — represents any entity (AI or human) that can execute tasks.

Agents register their capabilities, bid on tasks in the market hub, and
accumulate trust/reputation scores over time on an immutable ledger.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AgentType(Enum):
    """Whether the agent is an AI system or a human operator."""

    AI = "ai"
    HUMAN = "human"
    HYBRID = "hybrid"


@dataclass
class AgentCapability:
    """A declared capability that an agent can perform.

    Attributes:
        name: Machine-readable capability identifier (e.g., "code_review").
        description: Human-readable explanation.
        proficiency: Self-reported proficiency score in [0, 1].
        verified: Whether this capability has been independently verified.
    """

    name: str
    description: str = ""
    proficiency: float = 1.0
    verified: bool = False


@dataclass
class Agent:
    """An entity capable of executing delegated tasks.

    Agents participate in the market hub by advertising capabilities and
    submitting bids. Their performance history feeds into the trust and
    reputation system.

    Attributes:
        agent_id: Globally unique identifier.
        name: Human-readable display name.
        agent_type: AI, human, or hybrid.
        capabilities: List of declared capabilities.
        trust_score: Current aggregate trust score in [0, 1].
        reputation_score: Current aggregate reputation score in [0, 1].
        is_available: Whether the agent is currently accepting new tasks.
        max_concurrent_tasks: Upper bound on simultaneous task assignments.
        current_task_ids: IDs of tasks currently assigned.
        registered_at: When the agent joined the system.
        metadata: Extensible key-value metadata.
    """

    name: str
    agent_type: AgentType = AgentType.AI
    agent_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    capabilities: list[AgentCapability] = field(default_factory=list)
    trust_score: float = 0.5
    reputation_score: float = 0.5
    is_available: bool = True
    max_concurrent_tasks: int = 1
    current_task_ids: list[str] = field(default_factory=list)
    registered_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_capacity(self) -> bool:
        """Whether the agent can accept another task."""
        return (
            self.is_available
            and len(self.current_task_ids) < self.max_concurrent_tasks
        )

    def has_capability(self, capability_name: str) -> bool:
        """Check if the agent declares a given capability."""
        return any(c.name == capability_name for c in self.capabilities)
