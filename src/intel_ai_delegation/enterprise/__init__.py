"""Enterprise features for Intelligent AI Delegation.

This package provides enterprise-grade capabilities:
  - RBAC: Role-based access control with fine-grained policies
  - Audit: Immutable, queryable audit trail for compliance
  - Org: Multi-tenant organization and team management
  - Metering: Usage tracking with enforced quotas
  - Analytics: Advanced trust analytics with trend and anomaly detection
"""

from intel_ai_delegation.enterprise.rbac import (
    Permission,
    Policy,
    Role,
    RBACEnforcer,
    RoleBinding,
)
from intel_ai_delegation.enterprise.audit import (
    AuditEntry,
    AuditLevel,
    AuditTrail,
)
from intel_ai_delegation.enterprise.org import (
    Organization,
    Team,
    Membership,
    MemberRole,
    OrgManager,
)
from intel_ai_delegation.enterprise.metering import (
    UsageRecord,
    Quota,
    QuotaPeriod,
    UsageMeter,
)
from intel_ai_delegation.enterprise.analytics import (
    TrustTrend,
    AnomalyAlert,
    AgentComparison,
    TrustAnalytics,
)

__all__ = [
    "Permission",
    "Policy",
    "Role",
    "RBACEnforcer",
    "RoleBinding",
    "AuditEntry",
    "AuditLevel",
    "AuditTrail",
    "Organization",
    "Team",
    "Membership",
    "MemberRole",
    "OrgManager",
    "UsageRecord",
    "Quota",
    "QuotaPeriod",
    "UsageMeter",
    "TrustTrend",
    "AnomalyAlert",
    "AgentComparison",
    "TrustAnalytics",
]
