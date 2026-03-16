"""Protocol for verifiable task completion.

A task is not considered done until its outcome is verified. Verification
methods include:
  - Direct inspection: The delegator reviews the output.
  - Third-party audit: An independent agent verifies the result.
  - Cryptographic proof: zk-SNARKs or similar proofs guarantee correctness
    without exposing sensitive data.
  - Automated testing: Programmatic checks against a specification.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from intel_ai_delegation.models.task import Task


class VerificationStatus(Enum):
    """Outcome of a verification attempt."""

    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"
    ERROR = "error"


@dataclass
class VerificationResult:
    """The result of verifying a task's output.

    Attributes:
        task_id: The verified task.
        status: Whether verification passed or failed.
        method: The method used (matches VerificationCriteria.method).
        score: Quantitative score in [0, 1] if applicable.
        details: Structured details about the verification.
        proof: Cryptographic proof data, if applicable.
        verifier_id: Who performed the verification.
        verified_at: Timestamp of verification.
    """

    task_id: str
    status: VerificationStatus
    method: str
    score: float = 1.0
    details: dict[str, Any] = field(default_factory=dict)
    proof: bytes | None = None
    verifier_id: str = ""
    verified_at: datetime = field(default_factory=datetime.utcnow)


class Verifier(ABC):
    """Abstract base for task verification.

    Implementations can range from simple assertion checks to
    full zk-SNARK proof generation and validation.
    """

    @abstractmethod
    async def verify(self, task: Task) -> VerificationResult:
        """Verify that a task's output meets its specification.

        The verification method is determined by task.verification.method.

        Args:
            task: The task to verify. Must have output_data populated.

        Returns:
            The verification result.
        """
        ...

    @abstractmethod
    async def validate_proof(self, proof: bytes, task: Task) -> bool:
        """Validate a cryptographic proof of task completion.

        Args:
            proof: The proof data to validate.
            task: The task the proof relates to.

        Returns:
            True if the proof is valid.
        """
        ...
