"""Role-Based Access Control (RBAC) for enterprise delegation environments.

Provides fine-grained authorization with:
  - Permissions: Atomic actions on resources (e.g., "tasks:create", "contracts:read").
  - Roles: Named collections of permissions (e.g., "operator", "admin").
  - Policies: Conditional rules that allow or deny access based on context.
  - RoleBindings: Associations between agents/users and roles, scoped to orgs/teams.
  - RBACEnforcer: The policy decision point that evaluates access requests.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class PermissionEffect(Enum):
    """Whether a policy allows or denies the action."""

    ALLOW = "allow"
    DENY = "deny"


@dataclass
class Permission:
    """An atomic authorization unit.

    Permissions follow the pattern "resource:action" where resource is
    a framework concept (tasks, contracts, agents, ledger) and action
    is the operation (create, read, update, delete, delegate, verify).

    Attributes:
        resource: The resource type (e.g., "tasks", "contracts").
        action: The operation (e.g., "create", "read", "delegate").
        description: Human-readable explanation.
    """

    resource: str
    action: str
    description: str = ""

    @property
    def key(self) -> str:
        """Canonical permission key: 'resource:action'."""
        return f"{self.resource}:{self.action}"

    def __hash__(self) -> int:
        return hash(self.key)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Permission):
            return self.key == other.key
        return NotImplemented


@dataclass
class Role:
    """A named collection of permissions.

    Roles are the primary grouping mechanism. Built-in roles include:
      - viewer: Read-only access to tasks, contracts, and ledger.
      - operator: Can create/delegate tasks and manage contracts.
      - admin: Full access including RBAC management and org settings.

    Attributes:
        role_id: Unique identifier.
        name: Human-readable role name (must be unique within an org).
        permissions: Set of permissions granted by this role.
        description: What this role is for.
        built_in: Whether this is a system-defined role (cannot be deleted).
        org_id: The organization this role belongs to (None = global).
        created_at: When the role was created.
    """

    name: str
    permissions: list[Permission] = field(default_factory=list)
    description: str = ""
    built_in: bool = False
    org_id: str | None = None
    role_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)

    def has_permission(self, resource: str, action: str) -> bool:
        """Check if this role includes a specific permission."""
        key = f"{resource}:{action}"
        return any(p.key == key for p in self.permissions)

    def grant(self, permission: Permission) -> None:
        """Add a permission to this role."""
        if permission not in self.permissions:
            self.permissions.append(permission)

    def revoke(self, permission: Permission) -> None:
        """Remove a permission from this role."""
        self.permissions = [p for p in self.permissions if p.key != permission.key]


@dataclass
class RoleBinding:
    """Associates an agent or user with a role, optionally scoped to an org/team.

    Attributes:
        binding_id: Unique identifier.
        agent_id: The agent or user (DID) receiving this role.
        role_id: The role being granted.
        org_id: Organization scope (None = global).
        team_id: Team scope within the org (None = org-wide).
        granted_by: Who granted this binding (DID).
        granted_at: When the binding was created.
        expires_at: Optional expiration.
        active: Whether the binding is currently active.
    """

    agent_id: str
    role_id: str
    org_id: str | None = None
    team_id: str | None = None
    granted_by: str = ""
    binding_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    granted_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None
    active: bool = True

    @property
    def is_valid(self) -> bool:
        """Check if the binding is currently active and not expired."""
        if not self.active:
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return True


@dataclass
class Policy:
    """A conditional access rule evaluated by the RBAC enforcer.

    Policies allow fine-grained, context-aware authorization beyond
    simple role checks. For example: "deny delegation of HIGH criticality
    tasks to agents with trust score below 0.8".

    Attributes:
        policy_id: Unique identifier.
        name: Human-readable policy name.
        effect: Whether this policy allows or denies access.
        resource: Resource pattern (supports wildcards: "tasks:*").
        action: Action pattern (supports wildcards).
        conditions: Context conditions that must all be true for the
            policy to apply. Keys are condition types, values are
            thresholds or patterns.
        priority: Higher priority policies override lower ones.
            Deny policies should generally have higher priority.
        org_id: Organization scope.
        enabled: Whether the policy is active.
        description: Explanation of what this policy enforces.
    """

    name: str
    effect: PermissionEffect
    resource: str
    action: str
    conditions: dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    org_id: str | None = None
    enabled: bool = True
    description: str = ""
    policy_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)

    def matches(self, resource: str, action: str) -> bool:
        """Check if this policy applies to a given resource:action pair."""
        return (
            _pattern_matches(self.resource, resource)
            and _pattern_matches(self.action, action)
        )


def _pattern_matches(pattern: str, value: str) -> bool:
    """Simple wildcard matching: '*' matches anything."""
    if pattern == "*":
        return True
    return pattern == value


@dataclass
class AccessRequest:
    """A request to perform an action, evaluated by the enforcer.

    Attributes:
        agent_id: Who is requesting access (DID).
        resource: The resource type.
        action: The action to perform.
        resource_id: Specific resource instance (optional).
        context: Additional context for policy evaluation
            (e.g., task criticality, agent trust score).
    """

    agent_id: str
    resource: str
    action: str
    resource_id: str = ""
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class AccessDecision:
    """The result of an RBAC evaluation.

    Attributes:
        allowed: Whether access is granted.
        reason: Explanation of why access was granted or denied.
        matched_policies: Policy IDs that influenced the decision.
        matched_roles: Role IDs that contributed permissions.
    """

    allowed: bool
    reason: str = ""
    matched_policies: list[str] = field(default_factory=list)
    matched_roles: list[str] = field(default_factory=list)


class RBACEnforcer(ABC):
    """Abstract base for the RBAC policy decision point.

    The enforcer evaluates access requests against role bindings
    and policies, returning allow/deny decisions with explanations.
    """

    @abstractmethod
    async def evaluate(self, request: AccessRequest) -> AccessDecision:
        """Evaluate an access request against roles and policies.

        Evaluation order:
          1. Collect all valid role bindings for the agent.
          2. Aggregate permissions from all bound roles.
          3. Check if any permission matches the requested resource:action.
          4. Apply policies in priority order (deny overrides allow).
          5. Return the decision with matched policies and roles.

        Args:
            request: The access request to evaluate.

        Returns:
            The access decision.
        """
        ...

    @abstractmethod
    async def create_role(self, role: Role) -> Role:
        """Create a new role.

        Args:
            role: The role to create.

        Returns:
            The created role.
        """
        ...

    @abstractmethod
    async def bind_role(self, binding: RoleBinding) -> RoleBinding:
        """Bind a role to an agent/user.

        Args:
            binding: The role binding to create.

        Returns:
            The created binding.
        """
        ...

    @abstractmethod
    async def unbind_role(self, binding_id: str) -> None:
        """Deactivate a role binding.

        Args:
            binding_id: The binding to deactivate.
        """
        ...

    @abstractmethod
    async def add_policy(self, policy: Policy) -> Policy:
        """Add an access policy.

        Args:
            policy: The policy to add.

        Returns:
            The created policy.
        """
        ...

    @abstractmethod
    async def remove_policy(self, policy_id: str) -> None:
        """Remove an access policy.

        Args:
            policy_id: The policy to remove.
        """
        ...

    @abstractmethod
    async def get_agent_roles(self, agent_id: str) -> list[Role]:
        """Get all roles bound to an agent.

        Args:
            agent_id: The agent to query (DID).

        Returns:
            List of roles currently bound to the agent.
        """
        ...

    @abstractmethod
    async def get_agent_permissions(self, agent_id: str) -> list[Permission]:
        """Get the effective permission set for an agent.

        This aggregates permissions from all bound roles.

        Args:
            agent_id: The agent to query (DID).

        Returns:
            Deduplicated list of all effective permissions.
        """
        ...


# ----- Built-in role definitions -----

VIEWER_PERMISSIONS = [
    Permission("tasks", "read", "View task details and status"),
    Permission("contracts", "read", "View contract details"),
    Permission("ledger", "read", "View ledger transactions"),
    Permission("agents", "read", "View agent profiles"),
    Permission("analytics", "read", "View trust analytics"),
]

OPERATOR_PERMISSIONS = VIEWER_PERMISSIONS + [
    Permission("tasks", "create", "Create new tasks"),
    Permission("tasks", "delegate", "Delegate tasks to agents"),
    Permission("tasks", "cancel", "Cancel pending tasks"),
    Permission("contracts", "create", "Create contracts"),
    Permission("contracts", "activate", "Activate contracts"),
    Permission("market", "advertise", "Advertise tasks on market"),
    Permission("market", "select_bid", "Select winning bids"),
    Permission("monitoring", "read", "View monitoring events"),
]

ADMIN_PERMISSIONS = OPERATOR_PERMISSIONS + [
    Permission("tasks", "delete", "Delete tasks"),
    Permission("contracts", "terminate", "Terminate contracts"),
    Permission("agents", "create", "Register new agents"),
    Permission("agents", "deactivate", "Deactivate agents"),
    Permission("rbac", "manage", "Manage roles, bindings, and policies"),
    Permission("org", "manage", "Manage organization settings"),
    Permission("org", "members", "Manage organization membership"),
    Permission("quotas", "manage", "Manage usage quotas"),
    Permission("audit", "read", "View audit trail"),
    Permission("audit", "export", "Export audit data"),
]

BUILTIN_VIEWER = Role(
    name="viewer",
    permissions=list(VIEWER_PERMISSIONS),
    description="Read-only access to tasks, contracts, ledger, and analytics.",
    built_in=True,
)

BUILTIN_OPERATOR = Role(
    name="operator",
    permissions=list(OPERATOR_PERMISSIONS),
    description="Can create and delegate tasks, manage contracts, and use the market.",
    built_in=True,
)

BUILTIN_ADMIN = Role(
    name="admin",
    permissions=list(ADMIN_PERMISSIONS),
    description="Full access including RBAC, org management, quotas, and audit.",
    built_in=True,
)
