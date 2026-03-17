"""Protocol for just-in-time permission management.

Agents are not given unchecked access. In high-stakes domains, access
to sensitive APIs and resources is granted on a just-in-time basis,
strictly scoped to the task and revoked upon completion or termination.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


@dataclass
class PermissionGrant:
    """A scoped, time-limited permission granted to an agent.

    Attributes:
        grant_id: Unique identifier.
        agent_id: The agent receiving the permission.
        task_id: The task this permission is scoped to.
        contract_id: The governing contract.
        scope: Permission scope identifier (e.g., "api:read:users").
        resource: The specific resource being accessed.
        granted_at: When the permission was granted.
        expires_at: When the permission automatically expires.
        revoked: Whether the permission has been explicitly revoked.
        metadata: Extensible data.
    """

    agent_id: str
    task_id: str
    scope: str
    resource: str = "*"
    contract_id: str = ""
    grant_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    granted_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None
    revoked: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        """Check if the grant is currently active."""
        if self.revoked:
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return True


class PermissionManager(ABC):
    """Abstract base for just-in-time permission management."""

    @abstractmethod
    async def grant(
        self,
        agent_id: str,
        task_id: str,
        scope: str,
        resource: str = "*",
        duration: timedelta | None = None,
    ) -> PermissionGrant:
        """Grant a scoped, time-limited permission to an agent.

        Args:
            agent_id: The agent to grant access to.
            task_id: The task the permission is scoped to.
            scope: Permission scope identifier.
            resource: Specific resource (default: all within scope).
            duration: How long the permission lasts. None = until revoked.

        Returns:
            The permission grant.
        """
        ...

    @abstractmethod
    async def revoke(self, grant_id: str) -> None:
        """Revoke a previously granted permission.

        Args:
            grant_id: The grant to revoke.
        """
        ...

    @abstractmethod
    async def revoke_all_for_task(self, task_id: str) -> int:
        """Revoke all permissions associated with a task.

        Called when a task completes, fails, or is re-delegated.

        Args:
            task_id: The task whose permissions should be revoked.

        Returns:
            Number of grants revoked.
        """
        ...

    @abstractmethod
    async def check(self, agent_id: str, scope: str, resource: str = "*") -> bool:
        """Check if an agent currently has a specific permission.

        Args:
            agent_id: The agent to check.
            scope: Required permission scope.
            resource: Required resource.

        Returns:
            True if the agent has a valid, non-expired grant.
        """
        ...

    @abstractmethod
    async def list_grants(self, agent_id: str) -> list[PermissionGrant]:
        """List all active permission grants for an agent.

        Args:
            agent_id: The agent to query.

        Returns:
            List of active (non-revoked, non-expired) grants.
        """
        ...
