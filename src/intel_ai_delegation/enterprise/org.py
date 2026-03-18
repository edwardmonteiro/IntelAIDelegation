"""Multi-tenant Organization and Team management.

Enterprises operate with organizational hierarchies:
  - Organizations: Top-level tenants with isolated data and settings.
  - Teams: Groups within an org that share resources and permissions.
  - Memberships: Agent/user associations with teams and orgs.

All delegation operations are scoped to an organization, ensuring
data isolation between tenants.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class MemberRole(Enum):
    """Role of a member within an organization or team."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class OrgStatus(Enum):
    """Lifecycle status of an organization."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


@dataclass
class Organization:
    """A tenant in the multi-tenant delegation system.

    Organizations provide data isolation: tasks, contracts, agents,
    and ledger entries are scoped to an org. Cross-org delegation
    requires explicit federation agreements.

    Attributes:
        org_id: Globally unique identifier.
        name: Display name.
        slug: URL-safe unique identifier.
        status: Current lifecycle state.
        owner_id: DID of the organization owner.
        settings: Org-level configuration (e.g., default SLA terms,
            allowed verification methods, federation policies).
        max_agents: Maximum number of registered agents.
        max_teams: Maximum number of teams.
        max_tasks_per_month: Monthly task delegation limit.
        billing_email: Contact for billing/invoicing.
        created_at: When the org was created.
        metadata: Extensible key-value data.
    """

    name: str
    slug: str
    owner_id: str
    org_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: OrgStatus = OrgStatus.ACTIVE
    settings: dict[str, Any] = field(default_factory=dict)
    max_agents: int = 100
    max_teams: int = 20
    max_tasks_per_month: int = 10000
    billing_email: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.status == OrgStatus.ACTIVE


@dataclass
class Team:
    """A group within an organization that shares resources.

    Teams allow fine-grained scoping of permissions and resource
    access. Agents can belong to multiple teams.

    Attributes:
        team_id: Unique identifier.
        org_id: Parent organization.
        name: Display name.
        description: What this team does.
        lead_id: DID of the team lead.
        settings: Team-level overrides for org settings.
        created_at: When the team was created.
        metadata: Extensible data.
    """

    org_id: str
    name: str
    description: str = ""
    lead_id: str = ""
    team_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    settings: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Membership:
    """An agent/user's membership in an organization or team.

    Attributes:
        membership_id: Unique identifier.
        agent_id: The member (DID).
        org_id: Organization.
        team_id: Team within the org (None = org-level only).
        role: Member's role within this scope.
        joined_at: When the membership started.
        invited_by: Who invited this member (DID).
        active: Whether the membership is active.
    """

    agent_id: str
    org_id: str
    role: MemberRole = MemberRole.MEMBER
    team_id: str | None = None
    invited_by: str = ""
    membership_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    joined_at: datetime = field(default_factory=datetime.utcnow)
    active: bool = True


class OrgManager(ABC):
    """Abstract base for organization and team management."""

    @abstractmethod
    async def create_org(self, org: Organization) -> Organization:
        """Create a new organization.

        Args:
            org: The organization to create.

        Returns:
            The created organization.
        """
        ...

    @abstractmethod
    async def get_org(self, org_id: str) -> Organization:
        """Retrieve an organization by ID.

        Args:
            org_id: The organization to retrieve.

        Returns:
            The organization.

        Raises:
            OrgError: If not found.
        """
        ...

    @abstractmethod
    async def update_org(self, org: Organization) -> Organization:
        """Update organization settings.

        Args:
            org: The organization with updated fields.

        Returns:
            The updated organization.
        """
        ...

    @abstractmethod
    async def suspend_org(self, org_id: str, reason: str = "") -> Organization:
        """Suspend an organization (disables all delegation activity).

        Args:
            org_id: The organization to suspend.
            reason: Why the org is being suspended.

        Returns:
            The updated organization.
        """
        ...

    @abstractmethod
    async def create_team(self, team: Team) -> Team:
        """Create a new team within an organization.

        Args:
            team: The team to create.

        Returns:
            The created team.
        """
        ...

    @abstractmethod
    async def get_teams(self, org_id: str) -> list[Team]:
        """List all teams in an organization.

        Args:
            org_id: The organization to query.

        Returns:
            List of teams.
        """
        ...

    @abstractmethod
    async def add_member(self, membership: Membership) -> Membership:
        """Add a member to an organization or team.

        Args:
            membership: The membership to create.

        Returns:
            The created membership.
        """
        ...

    @abstractmethod
    async def remove_member(self, membership_id: str) -> None:
        """Remove a member from an organization or team.

        Args:
            membership_id: The membership to deactivate.
        """
        ...

    @abstractmethod
    async def get_members(
        self, org_id: str, team_id: str | None = None
    ) -> list[Membership]:
        """List members of an organization or team.

        Args:
            org_id: The organization to query.
            team_id: Optional team filter.

        Returns:
            List of active memberships.
        """
        ...

    @abstractmethod
    async def get_agent_orgs(self, agent_id: str) -> list[Organization]:
        """List all organizations an agent belongs to.

        Args:
            agent_id: The agent to query (DID).

        Returns:
            List of organizations.
        """
        ...


class OrgError(Exception):
    """Raised when an organization operation fails."""
