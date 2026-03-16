"""Protocol for contract lifecycle management.

Smart contracts formalize the delegation agreement between a delegator
and delegatee. They encode SLAs, penalties, verification methods, and
permission grants. The contract manager handles creation, activation,
breach detection, and completion.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from intel_ai_delegation.market.protocol import Bid
from intel_ai_delegation.models.contract import Contract, ContractStatus
from intel_ai_delegation.models.task import Task


class ContractManager(ABC):
    """Abstract base for contract lifecycle operations."""

    @abstractmethod
    async def create_contract(self, task: Task, bid: Bid) -> Contract:
        """Create a new contract from an accepted bid.

        The contract encodes the task's verification criteria, the bid's
        proposed cost and duration as SLA terms, and default penalties.

        Args:
            task: The task being contracted.
            bid: The accepted bid.

        Returns:
            A new contract in PROPOSED status.
        """
        ...

    @abstractmethod
    async def activate_contract(self, contract_id: str) -> Contract:
        """Transition a contract from PROPOSED/ACCEPTED to ACTIVE.

        This signals that work may begin. Permissions specified in the
        contract should be granted at this point.

        Args:
            contract_id: The contract to activate.

        Returns:
            The updated contract.

        Raises:
            ContractError: If the contract cannot be activated.
        """
        ...

    @abstractmethod
    async def report_breach(self, contract_id: str, reason: str) -> Contract:
        """Record a contract breach and apply penalties.

        Args:
            contract_id: The breached contract.
            reason: Human-readable description of the breach.

        Returns:
            The updated contract in BREACHED status.
        """
        ...

    @abstractmethod
    async def complete_contract(self, contract_id: str) -> Contract:
        """Mark a contract as successfully completed.

        This should only be called after the task's verification criteria
        have been satisfied.

        Args:
            contract_id: The contract to complete.

        Returns:
            The updated contract in COMPLETED status.
        """
        ...

    @abstractmethod
    async def terminate_contract(self, contract_id: str, reason: str) -> Contract:
        """Terminate a contract early (e.g., due to re-delegation).

        Args:
            contract_id: The contract to terminate.
            reason: Why the contract is being terminated.

        Returns:
            The updated contract in TERMINATED status.
        """
        ...

    @abstractmethod
    async def get_contract(self, contract_id: str) -> Contract:
        """Retrieve a contract by ID.

        Args:
            contract_id: The contract to retrieve.

        Returns:
            The contract.

        Raises:
            ContractError: If not found.
        """
        ...


class ContractError(Exception):
    """Raised when a contract operation fails."""
