"""Usage Metering and Quota Enforcement.

Tracks resource consumption per organization, team, and agent.
Enforces configurable quotas to prevent runaway costs and ensure
fair resource allocation across tenants.

Metered dimensions:
  - Task delegations (count)
  - Contract creations (count)
  - Agent registrations (count)
  - Compute consumption (abstract cost units)
  - API calls (count)
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class QuotaPeriod(Enum):
    """Time period for quota enforcement."""

    HOURLY = "hourly"
    DAILY = "daily"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    LIFETIME = "lifetime"


class MeterDimension(Enum):
    """Dimensions that can be metered."""

    TASK_DELEGATIONS = "task_delegations"
    CONTRACT_CREATIONS = "contract_creations"
    AGENT_REGISTRATIONS = "agent_registrations"
    COMPUTE_COST = "compute_cost"
    API_CALLS = "api_calls"
    STORAGE_BYTES = "storage_bytes"
    VERIFICATION_RUNS = "verification_runs"


@dataclass
class UsageRecord:
    """A single usage event to be recorded.

    Attributes:
        record_id: Unique identifier.
        org_id: Organization that consumed the resource.
        agent_id: Agent that triggered the consumption.
        team_id: Team context (optional).
        dimension: What was consumed.
        quantity: How much was consumed.
        task_id: Associated task (optional).
        timestamp: When the consumption occurred.
        metadata: Additional context.
    """

    org_id: str
    agent_id: str
    dimension: MeterDimension
    quantity: float = 1.0
    team_id: str | None = None
    task_id: str | None = None
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Quota:
    """A usage limit for a specific dimension and scope.

    Attributes:
        quota_id: Unique identifier.
        org_id: Organization this quota applies to.
        team_id: Team scope (None = org-wide).
        dimension: What resource is limited.
        limit: Maximum allowed quantity per period.
        period: Time period for the limit.
        current_usage: Current consumption in the active period.
        alert_threshold: Percentage of limit that triggers a warning (0-1).
        hard_limit: If True, operations are blocked when limit is reached.
            If False, a warning is issued but operations continue.
        enabled: Whether this quota is actively enforced.
        created_at: When the quota was created.
    """

    org_id: str
    dimension: MeterDimension
    limit: float
    period: QuotaPeriod = QuotaPeriod.MONTHLY
    team_id: str | None = None
    current_usage: float = 0.0
    alert_threshold: float = 0.8
    hard_limit: bool = True
    enabled: bool = True
    quota_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def utilization(self) -> float:
        """Current usage as a fraction of the limit."""
        if self.limit <= 0:
            return 1.0
        return self.current_usage / self.limit

    @property
    def remaining(self) -> float:
        """How much quota remains."""
        return max(0.0, self.limit - self.current_usage)

    @property
    def is_exceeded(self) -> bool:
        """Whether the quota has been exceeded."""
        return self.current_usage >= self.limit

    @property
    def is_warning(self) -> bool:
        """Whether usage has crossed the alert threshold."""
        return self.utilization >= self.alert_threshold


@dataclass
class QuotaCheckResult:
    """Result of checking whether an operation is within quota.

    Attributes:
        allowed: Whether the operation can proceed.
        dimension: The metered dimension.
        current_usage: Current consumption.
        limit: The quota limit.
        remaining: How much quota remains.
        warning: Whether usage is above the alert threshold.
        message: Human-readable status message.
    """

    allowed: bool
    dimension: MeterDimension
    current_usage: float = 0.0
    limit: float = 0.0
    remaining: float = 0.0
    warning: bool = False
    message: str = ""


class UsageMeter(ABC):
    """Abstract base for usage metering and quota enforcement."""

    @abstractmethod
    async def record_usage(self, record: UsageRecord) -> UsageRecord:
        """Record a usage event.

        This also updates the current_usage on any applicable quotas.

        Args:
            record: The usage event.

        Returns:
            The persisted usage record.
        """
        ...

    @abstractmethod
    async def check_quota(
        self, org_id: str, dimension: MeterDimension, quantity: float = 1.0
    ) -> QuotaCheckResult:
        """Check if an operation is within quota before executing.

        Args:
            org_id: The organization.
            dimension: The resource dimension.
            quantity: How much will be consumed.

        Returns:
            Whether the operation is allowed.
        """
        ...

    @abstractmethod
    async def set_quota(self, quota: Quota) -> Quota:
        """Create or update a quota.

        Args:
            quota: The quota to set.

        Returns:
            The persisted quota.
        """
        ...

    @abstractmethod
    async def get_quotas(self, org_id: str) -> list[Quota]:
        """List all quotas for an organization.

        Args:
            org_id: The organization to query.

        Returns:
            List of quotas.
        """
        ...

    @abstractmethod
    async def get_usage_summary(
        self,
        org_id: str,
        dimension: MeterDimension | None = None,
        period: QuotaPeriod = QuotaPeriod.MONTHLY,
    ) -> dict[str, float]:
        """Get aggregated usage for an organization.

        Args:
            org_id: The organization to query.
            dimension: Optional filter by dimension.
            period: Time period to aggregate over.

        Returns:
            Dict mapping dimension names to total consumption.
        """
        ...

    @abstractmethod
    async def reset_period(
        self, org_id: str, dimension: MeterDimension
    ) -> None:
        """Reset usage counters for a new period.

        Called automatically when a quota period rolls over.

        Args:
            org_id: The organization.
            dimension: The dimension to reset.
        """
        ...


class QuotaExceededError(Exception):
    """Raised when an operation would exceed a hard quota limit."""

    def __init__(self, dimension: MeterDimension, current: float, limit: float):
        self.dimension = dimension
        self.current = current
        self.limit = limit
        super().__init__(
            f"Quota exceeded for {dimension.value}: "
            f"{current}/{limit} (limit reached)"
        )
