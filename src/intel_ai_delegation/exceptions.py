"""Shared exception hierarchy for the delegation framework."""


class DelegationError(Exception):
    """Base exception for all delegation framework errors."""


class DecompositionError(DelegationError):
    """Raised when a task cannot be decomposed."""


class BidError(DelegationError):
    """Raised when a bid operation fails."""


class ContractError(DelegationError):
    """Raised when a contract operation fails."""


class PermissionError(DelegationError):
    """Raised when a permission operation fails."""


class VerificationError(DelegationError):
    """Raised when verification fails."""


class LedgerError(DelegationError):
    """Raised when a ledger operation fails."""


class CoordinationError(DelegationError):
    """Raised when coordination logic encounters an error."""
