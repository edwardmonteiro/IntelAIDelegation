"""Ledger Transaction model — immutable performance history records.

Every completed (or failed) task results in a permanent record on the
ledger. This is the core of the reputation system — an append-only,
tamper-proof log that can be synced to a blockchain backend.

Each record captures multi-dimensional scores (quality, transparency,
safety) along with verifiable resource consumption metrics and a
cryptographic proof hash for zero-knowledge verification.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class CompletionStatus(Enum):
    """Outcome of a task execution."""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


@dataclass
class LedgerTransaction:
    """An immutable record of task execution on the reputation ledger.

    Once written, ledger transactions cannot be modified or deleted.
    They serve as the ground truth for computing agent trust and
    reputation scores.

    Attributes:
        transaction_id: Globally unique identifier.
        task_id: The task that was executed.
        delegatee_id: DID of the agent who performed the work.
        completion_status: Whether the task succeeded, failed, or was partial.
        quality_score: Quality metric graded by the delegator or verifier, in [0, 1].
        transparency_score: Derived from the clarity of reasoning traces
            during process monitoring, in [0, 1].
        safety_score: Derived from compliance to predefined safety protocols, in [0, 1].
        resource_consumed: Verifiable resource consumption metrics
            (e.g., {"gpu_hours": 2.5, "api_tokens": 15000}).
        verification_proof_hash: Cryptographic receipt (e.g., zk-SNARK trace)
            proving the work was done correctly.
        delegator_id: DID of the delegator who recorded this transaction.
        contract_id: The governing contract.
        recorded_at: When this record was created (immutable timestamp).
        metadata: Extensible key-value data.
    """

    task_id: str
    delegatee_id: str
    completion_status: CompletionStatus
    quality_score: float = 1.0
    transparency_score: float = 1.0
    safety_score: float = 1.0
    resource_consumed: dict[str, Any] = field(default_factory=dict)
    verification_proof_hash: str = ""
    delegator_id: str = ""
    contract_id: str = ""
    transaction_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    recorded_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def composite_score(self) -> float:
        """Weighted composite score across all dimensions.

        Default weighting: quality 50%, transparency 25%, safety 25%.
        Override via metadata["score_weights"] for custom weighting.
        """
        weights = self.metadata.get(
            "score_weights",
            {"quality": 0.5, "transparency": 0.25, "safety": 0.25},
        )
        return (
            self.quality_score * weights.get("quality", 0.5)
            + self.transparency_score * weights.get("transparency", 0.25)
            + self.safety_score * weights.get("safety", 0.25)
        )
