"""Protocol for the Trust and Reputation system.

Agent performance history is recorded as immutable LedgerTransactions.
Trust scores are dynamic and derived from the full portfolio of
multi-dimensional records (quality, transparency, safety). The ledger
is append-only and should be synced to a blockchain backend for
tamper-proof guarantees.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from intel_ai_delegation.models.credential import VerifiableCredential
from intel_ai_delegation.models.ledger import LedgerTransaction


@dataclass
class TrustScore:
    """Aggregated trust metrics for an agent.

    Derived from the agent's full history of LedgerTransactions
    and their portfolio of VerifiableCredentials.

    Attributes:
        agent_id: The agent (DID).
        overall: Composite trust score in [0, 1].
        reliability: Track record of completing tasks successfully.
        quality: Average quality of delivered work.
        transparency: Average clarity of reasoning traces.
        safety: Average compliance with safety protocols.
        timeliness: Track record of meeting deadlines.
        total_tasks: Number of tasks in the history.
        updated_at: When this score was last computed.
    """

    agent_id: str
    overall: float = 0.5
    reliability: float = 0.5
    quality: float = 0.5
    transparency: float = 0.5
    safety: float = 0.5
    timeliness: float = 0.5
    total_tasks: int = 0
    updated_at: datetime = field(default_factory=datetime.utcnow)


class TrustLedger(ABC):
    """Abstract base for the trust and reputation ledger.

    The ledger is append-only (immutable). Trust scores are computed
    from the full history of ledger transactions and verifiable credentials.
    """

    @abstractmethod
    async def record_transaction(self, transaction: LedgerTransaction) -> None:
        """Append a ledger transaction (immutable once written).

        Args:
            transaction: The performance record to store.
        """
        ...

    @abstractmethod
    async def get_trust_score(self, agent_id: str) -> TrustScore:
        """Compute the current trust score for an agent.

        The score is derived from the agent's full history of
        ledger transactions and verifiable credentials.

        Args:
            agent_id: The agent to evaluate (DID).

        Returns:
            The computed trust score.
        """
        ...

    @abstractmethod
    async def get_transaction_history(
        self, agent_id: str, limit: int = 100
    ) -> list[LedgerTransaction]:
        """Retrieve an agent's ledger transaction history.

        Args:
            agent_id: The agent to query (DID).
            limit: Maximum number of records to return.

        Returns:
            List of transactions, most recent first.
        """
        ...

    @abstractmethod
    async def get_transaction(self, transaction_id: str) -> LedgerTransaction:
        """Retrieve a specific ledger transaction.

        Args:
            transaction_id: The transaction to retrieve.

        Returns:
            The ledger transaction.

        Raises:
            LedgerError: If not found.
        """
        ...

    @abstractmethod
    async def issue_credential(
        self, credential: VerifiableCredential
    ) -> VerifiableCredential:
        """Issue a verifiable credential to an agent.

        Args:
            credential: The credential to issue.

        Returns:
            The credential with its hash populated.
        """
        ...

    @abstractmethod
    async def get_credentials(
        self, agent_id: str, skill_domain: str | None = None
    ) -> list[VerifiableCredential]:
        """Retrieve an agent's verifiable credentials.

        Args:
            agent_id: The agent to query (DID).
            skill_domain: Optional filter by skill domain.

        Returns:
            List of valid (non-revoked, non-expired) credentials.
        """
        ...

    @abstractmethod
    async def revoke_credential(self, credential_id: str) -> None:
        """Revoke a previously issued credential.

        Args:
            credential_id: The credential to revoke.
        """
        ...


class LedgerError(Exception):
    """Raised when a ledger operation fails."""
