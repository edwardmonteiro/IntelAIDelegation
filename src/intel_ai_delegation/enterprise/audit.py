"""Immutable Audit Trail for enterprise compliance.

Every significant action in the delegation framework is recorded as an
immutable audit entry. The trail supports:
  - Filtering by actor, action, resource, time range, and severity.
  - Tamper detection via chained hashes (each entry includes the hash
    of the previous entry).
  - Export for external SIEM / compliance tooling.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AuditLevel(Enum):
    """Severity / importance of an audit event."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AuditCategory(Enum):
    """High-level category for audit events."""

    TASK = "task"
    CONTRACT = "contract"
    DELEGATION = "delegation"
    PERMISSION = "permission"
    RBAC = "rbac"
    AGENT = "agent"
    MARKET = "market"
    VERIFICATION = "verification"
    ORG = "organization"
    SYSTEM = "system"


@dataclass
class AuditEntry:
    """An immutable record of an action in the system.

    Audit entries form a hash chain: each entry's integrity_hash
    incorporates the previous entry's hash, making tampering detectable.

    Attributes:
        entry_id: Globally unique identifier.
        timestamp: When the action occurred (UTC).
        actor_id: DID of the user or agent who performed the action.
        action: What was done (e.g., "task.created", "contract.breached").
        category: High-level event category.
        level: Severity of the event.
        resource_type: The type of resource affected.
        resource_id: The specific resource instance.
        org_id: Organization context.
        details: Structured data about the action.
        previous_hash: Hash of the preceding audit entry (chain link).
        integrity_hash: Hash of this entry including previous_hash.
        ip_address: Source IP (if applicable).
        user_agent: Client identifier (if applicable).
    """

    actor_id: str
    action: str
    category: AuditCategory
    resource_type: str = ""
    resource_id: str = ""
    level: AuditLevel = AuditLevel.INFO
    org_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    previous_hash: str = ""
    integrity_hash: str = ""
    ip_address: str = ""
    user_agent: str = ""
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def compute_hash(self) -> str:
        """Compute the integrity hash for this entry.

        Includes the previous hash to form a chain.
        """
        payload = json.dumps(
            {
                "entry_id": self.entry_id,
                "timestamp": self.timestamp.isoformat(),
                "actor_id": self.actor_id,
                "action": self.action,
                "category": self.category.value,
                "resource_type": self.resource_type,
                "resource_id": self.resource_id,
                "details": self.details,
                "previous_hash": self.previous_hash,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def seal(self, previous_hash: str = "") -> None:
        """Seal the entry by computing and setting the integrity hash.

        Args:
            previous_hash: The hash of the previous audit entry.
        """
        self.previous_hash = previous_hash
        self.integrity_hash = self.compute_hash()


@dataclass
class AuditQuery:
    """Filter criteria for querying the audit trail.

    All fields are optional; unset fields match everything.

    Attributes:
        actor_id: Filter by acting agent/user.
        action: Filter by action name (supports prefix matching with '*').
        category: Filter by event category.
        level: Minimum severity level.
        resource_type: Filter by resource type.
        resource_id: Filter by specific resource.
        org_id: Filter by organization.
        start_time: Entries after this time.
        end_time: Entries before this time.
        limit: Maximum entries to return.
        offset: Pagination offset.
    """

    actor_id: str | None = None
    action: str | None = None
    category: AuditCategory | None = None
    level: AuditLevel | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    org_id: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    limit: int = 100
    offset: int = 0


class AuditTrail(ABC):
    """Abstract base for the immutable audit trail.

    Implementations must guarantee:
      - Append-only: entries cannot be modified or deleted.
      - Hash-chained: each entry links to the previous entry's hash.
      - Queryable: efficient filtering by actor, action, time, etc.
    """

    @abstractmethod
    async def record(self, entry: AuditEntry) -> AuditEntry:
        """Record an audit entry.

        The implementation must:
          1. Retrieve the latest entry's integrity_hash.
          2. Set it as this entry's previous_hash.
          3. Compute and set the integrity_hash.
          4. Persist the sealed entry.

        Args:
            entry: The audit entry to record.

        Returns:
            The sealed and persisted entry.
        """
        ...

    @abstractmethod
    async def query(self, query: AuditQuery) -> list[AuditEntry]:
        """Query audit entries matching the given filters.

        Args:
            query: The filter criteria.

        Returns:
            List of matching entries, ordered by timestamp descending.
        """
        ...

    @abstractmethod
    async def get_entry(self, entry_id: str) -> AuditEntry:
        """Retrieve a specific audit entry.

        Args:
            entry_id: The entry to retrieve.

        Returns:
            The audit entry.

        Raises:
            AuditError: If not found.
        """
        ...

    @abstractmethod
    async def verify_chain(
        self, start_id: str | None = None, end_id: str | None = None
    ) -> bool:
        """Verify the integrity of the audit hash chain.

        Walks the chain from end to start, recomputing each entry's
        hash and checking it against the stored integrity_hash.

        Args:
            start_id: First entry to verify (None = beginning).
            end_id: Last entry to verify (None = latest).

        Returns:
            True if the chain is intact, False if tampering detected.
        """
        ...

    @abstractmethod
    async def export(
        self, query: AuditQuery, format: str = "json"
    ) -> bytes:
        """Export audit entries for external compliance tools.

        Args:
            query: Filter criteria for which entries to export.
            format: Output format ("json", "csv", "syslog").

        Returns:
            Serialized audit data.
        """
        ...

    @abstractmethod
    async def count(self, query: AuditQuery) -> int:
        """Count entries matching a query without returning them.

        Args:
            query: The filter criteria.

        Returns:
            Number of matching entries.
        """
        ...


class AuditError(Exception):
    """Raised when an audit operation fails."""
