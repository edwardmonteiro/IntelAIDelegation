"""Contract model — formalizes the agreement between delegator and delegatee.

Smart contracts pair performance requirements with verification mechanisms
and automated penalties for breaches, ensuring accountability at every step.
The contract terms are hashed and stored immutably to prevent retroactive
tampering.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any


class ContractStatus(Enum):
    """Lifecycle states of a delegation contract."""

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    ACTIVE = "active"
    COMPLETED = "completed"
    BREACHED = "breached"
    TERMINATED = "terminated"
    EXPIRED = "expired"


class VerificationMethod(Enum):
    """Supported verification methods for contract fulfillment."""

    DIRECT_INSPECTION = "direct_inspection"
    THIRD_PARTY_AUDIT = "third_party_audit"
    CRYPTOGRAPHIC_ZK_PROOF = "cryptographic_zk_proof"
    CONSENSUS_GAME = "consensus_game"
    AUTOMATED_TEST = "automated_test"


@dataclass
class Penalty:
    """An automated penalty applied when contract terms are violated.

    Attributes:
        condition: Description of the breach condition that triggers this penalty.
        severity: A severity label ("low", "medium", "high", "critical").
        reputation_impact: How much the agent's reputation score decreases.
        description: Human-readable description of the penalty.
    """

    condition: str
    severity: str = "medium"
    reputation_impact: float = 0.0
    description: str = ""


@dataclass
class ServiceLevelAgreement:
    """Quantitative performance requirements within a contract.

    Attributes:
        max_duration: Maximum time to complete the task.
        min_quality_score: Minimum acceptable quality metric.
        max_cost: Budget cap.
        availability_requirement: Required uptime ratio for long-running tasks.
        checkpoints: List of intermediate milestones with deadlines.
    """

    max_duration: timedelta | None = None
    min_quality_score: float = 0.0
    max_cost: float | None = None
    availability_requirement: float | None = None
    checkpoints: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Contract:
    """A formal agreement governing the delegation of a task.

    The contract binds a delegator and a delegatee to a set of terms
    including SLAs, penalties, verification criteria, and permission grants.
    An immutable hash of the agreed terms is stored for tamper detection.

    Attributes:
        contract_id: Globally unique identifier.
        task_id: The task this contract governs.
        bid_id: The accepted bid that created this contract.
        delegator_id: DID of the delegating entity.
        delegatee_id: DID of the entity accepting the work.
        status: Current lifecycle state.
        verification_method: How task completion is verified.
        monitoring_cadence: Frequency of progress reports negotiated
            prior to execution (e.g., "every_5m", "on_checkpoint", "on_completion").
        contract_terms_hash: Immutable hash of the exact terms agreed upon,
            used to detect any retroactive tampering.
        sla: Service-level agreement terms.
        penalties: Penalties that apply upon breach.
        permissions_granted: Scoped permissions the delegatee receives.
        created_at: When the contract was created.
        activated_at: When the contract became active.
        completed_at: When the contract reached a terminal state.
        metadata: Extensible key-value metadata.
    """

    task_id: str
    delegator_id: str
    delegatee_id: str
    bid_id: str = ""
    contract_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: ContractStatus = ContractStatus.PROPOSED
    verification_method: VerificationMethod = VerificationMethod.DIRECT_INSPECTION
    monitoring_cadence: str = "on_completion"
    contract_terms_hash: str = ""
    sla: ServiceLevelAgreement = field(default_factory=ServiceLevelAgreement)
    penalties: list[Penalty] = field(default_factory=list)
    permissions_granted: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    activated_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.status == ContractStatus.ACTIVE

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            ContractStatus.COMPLETED,
            ContractStatus.BREACHED,
            ContractStatus.TERMINATED,
            ContractStatus.EXPIRED,
        }
