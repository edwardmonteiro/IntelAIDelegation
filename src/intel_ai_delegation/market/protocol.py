"""Protocol for the Market Hub.

The Market Hub is where delegators advertise sub-tasks and agents submit
bids. The hub supports decentralized discovery so that the best-fit agent
can be matched to each task based on capabilities, cost, and trust scores.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from intel_ai_delegation.models.agent import Agent
from intel_ai_delegation.models.task import Task


@dataclass
class Bid:
    """A bid submitted by an agent for a specific task.

    Attributes:
        bid_id: Unique identifier.
        task_id: The task being bid on.
        agent_id: The bidding agent (DID).
        proposed_cost: The economic or computational expense proposed.
        proposed_duration_seconds: Proposed time-frame for execution in seconds.
        confidence: Agent's self-assessed confidence in [0, 1].
        privacy_guarantee: Privacy mechanism offered, e.g. "tee_enclave_sgx",
            "zk_snark", "none".
        reputation_bond: Financial stake posted into escrow prior to execution
            to ensure crypto-economic security.
        message: Optional free-form message from the agent.
        submitted_at: Timestamp of submission.
        metadata: Extensible key-value data.
    """

    task_id: str
    agent_id: str
    proposed_cost: float = 0.0
    proposed_duration_seconds: float = 0.0
    confidence: float = 1.0
    privacy_guarantee: str = "none"
    reputation_bond: float = 0.0
    message: str = ""
    bid_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    submitted_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


class MarketHub(ABC):
    """Abstract base for the task marketplace.

    Implementations may be in-memory, backed by a message broker,
    or running on a decentralized ledger.
    """

    @abstractmethod
    async def advertise_task(self, task: Task) -> None:
        """Publish a task to the market for agents to discover.

        Args:
            task: The task to advertise. Its status should transition
                  to ADVERTISED.
        """
        ...

    @abstractmethod
    async def submit_bid(self, bid: Bid) -> None:
        """Submit a bid from an agent for an advertised task.

        Args:
            bid: The bid to submit.

        Raises:
            BidError: If the task is not accepting bids.
        """
        ...

    @abstractmethod
    async def get_bids(self, task_id: str) -> list[Bid]:
        """Retrieve all bids for a given task.

        Args:
            task_id: The task to query bids for.

        Returns:
            List of bids, ordered by submission time.
        """
        ...

    @abstractmethod
    async def select_bid(self, task_id: str, bid_id: str) -> Bid:
        """Accept a bid and assign the task to the winning agent.

        Args:
            task_id: The task being assigned.
            bid_id: The winning bid.

        Returns:
            The accepted bid.

        Raises:
            BidError: If the bid or task is invalid.
        """
        ...

    @abstractmethod
    async def register_agent(self, agent: Agent) -> None:
        """Register an agent in the marketplace.

        Args:
            agent: The agent to register.
        """
        ...

    @abstractmethod
    async def find_agents(
        self, capability: str, min_trust: float = 0.0
    ) -> list[Agent]:
        """Discover agents matching a capability and minimum trust threshold.

        Args:
            capability: Required capability identifier.
            min_trust: Minimum trust score filter.

        Returns:
            List of matching agents, ordered by trust score descending.
        """
        ...


class BidError(Exception):
    """Raised when a bid operation fails."""
