"""Agent model — represents any entity (AI or human) that can execute tasks.

Agents are identified by Decentralized Identifiers (DIDs) and authenticated
via public-key cryptography. Their reputation is a portfolio of domain-specific
Verifiable Credentials rather than a single generic score.

An algorithmic circuit breaker can deactivate agents when sudden reputation
drops or security flags are detected.
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
    reputation system as a portfolio of Verifiable Credentials.

    Attributes:
        agent_id: Decentralized Identifier (DID), e.g. "did:web:agent-name".
            Defaults to a UUID-based DID for convenience.
        name: Human-readable display name.
        agent_type: AI, human, or hybrid.
        public_key: Cryptographic public key for signing bids, attestations,
            and monitoring reports.
        capabilities: List of declared capabilities.
        base_reputation_score: Quick-reference aggregate score in [0, 1].
            The true reputation is derived from the credential portfolio.
        active_status: Whether the agent is active. Toggled by the circuit
            breaker on sudden reputation drops or security flags.
        max_concurrent_tasks: Upper bound on simultaneous task assignments.
        current_task_ids: IDs of tasks currently assigned.
        registered_at: When the agent joined the system.
        metadata: Extensible key-value metadata.
    """

    name: str
    agent_type: AgentType = AgentType.AI
    agent_id: str = field(
        default_factory=lambda: f"did:key:{uuid.uuid4()}"
    )
    public_key: str = ""
    capabilities: list[AgentCapability] = field(default_factory=list)
    base_reputation_score: float = 0.5
    active_status: bool = True
    max_concurrent_tasks: int = 1
    current_task_ids: list[str] = field(default_factory=list)
    registered_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_capacity(self) -> bool:
        """Whether the agent can accept another task."""
        return (
            self.active_status
            and len(self.current_task_ids) < self.max_concurrent_tasks
        )

    @property
    def is_available(self) -> bool:
        """Alias — agent is available if active and has capacity."""
        return self.has_capacity

    def has_capability(self, capability_name: str) -> bool:
        """Check if the agent declares a given capability."""
        return any(c.name == capability_name for c in self.capabilities)
