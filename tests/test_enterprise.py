"""Tests for enterprise feature models and data structures."""

from datetime import datetime, timedelta

from intel_ai_delegation.enterprise.rbac import (
    BUILTIN_ADMIN,
    BUILTIN_OPERATOR,
    BUILTIN_VIEWER,
    AccessDecision,
    AccessRequest,
    Permission,
    PermissionEffect,
    Policy,
    Role,
    RoleBinding,
)
from intel_ai_delegation.enterprise.audit import (
    AuditCategory,
    AuditEntry,
    AuditLevel,
    AuditQuery,
)
from intel_ai_delegation.enterprise.org import (
    MemberRole,
    Membership,
    Organization,
    OrgStatus,
    Team,
)
from intel_ai_delegation.enterprise.metering import (
    MeterDimension,
    Quota,
    QuotaCheckResult,
    QuotaExceededError,
    QuotaPeriod,
    UsageRecord,
)
from intel_ai_delegation.enterprise.analytics import (
    AgentComparison,
    AlertSeverity,
    AnomalyAlert,
    RiskAssessment,
    RiskLevel,
    TrendDirection,
    TrustTrend,
)


# ── RBAC Tests ──────────────────────────────────────────────────────────


class TestPermission:
    def test_permission_key(self):
        p = Permission("tasks", "create")
        assert p.key == "tasks:create"

    def test_permission_equality(self):
        p1 = Permission("tasks", "create")
        p2 = Permission("tasks", "create", "Different description")
        assert p1 == p2

    def test_permission_hash(self):
        p1 = Permission("tasks", "create")
        p2 = Permission("tasks", "create")
        assert hash(p1) == hash(p2)
        assert len({p1, p2}) == 1

    def test_different_permissions_not_equal(self):
        p1 = Permission("tasks", "create")
        p2 = Permission("tasks", "delete")
        assert p1 != p2


class TestRole:
    def test_create_role(self):
        role = Role(name="custom")
        assert role.role_id
        assert role.permissions == []
        assert role.built_in is False

    def test_has_permission(self):
        role = Role(
            name="test",
            permissions=[Permission("tasks", "read"), Permission("tasks", "create")],
        )
        assert role.has_permission("tasks", "read") is True
        assert role.has_permission("tasks", "delete") is False

    def test_grant_permission(self):
        role = Role(name="test")
        perm = Permission("tasks", "create")
        role.grant(perm)
        assert role.has_permission("tasks", "create") is True
        # Granting same permission again should not duplicate
        role.grant(perm)
        assert len(role.permissions) == 1

    def test_revoke_permission(self):
        perm = Permission("tasks", "create")
        role = Role(name="test", permissions=[perm])
        role.revoke(perm)
        assert role.has_permission("tasks", "create") is False
        assert len(role.permissions) == 0


class TestRoleBinding:
    def test_create_binding(self):
        binding = RoleBinding(
            agent_id="did:web:alice",
            role_id="role-123",
            org_id="org-1",
        )
        assert binding.is_valid is True
        assert binding.binding_id

    def test_expired_binding(self):
        binding = RoleBinding(
            agent_id="did:web:alice",
            role_id="role-123",
            expires_at=datetime(2020, 1, 1),
        )
        assert binding.is_valid is False

    def test_deactivated_binding(self):
        binding = RoleBinding(
            agent_id="did:web:alice",
            role_id="role-123",
            active=False,
        )
        assert binding.is_valid is False


class TestPolicy:
    def test_policy_matches_exact(self):
        policy = Policy(
            name="test",
            effect=PermissionEffect.DENY,
            resource="tasks",
            action="delete",
        )
        assert policy.matches("tasks", "delete") is True
        assert policy.matches("tasks", "create") is False

    def test_policy_wildcard_resource(self):
        policy = Policy(
            name="deny-all",
            effect=PermissionEffect.DENY,
            resource="*",
            action="delete",
        )
        assert policy.matches("tasks", "delete") is True
        assert policy.matches("contracts", "delete") is True
        assert policy.matches("tasks", "create") is False

    def test_policy_wildcard_action(self):
        policy = Policy(
            name="full-tasks",
            effect=PermissionEffect.ALLOW,
            resource="tasks",
            action="*",
        )
        assert policy.matches("tasks", "create") is True
        assert policy.matches("tasks", "delete") is True
        assert policy.matches("contracts", "create") is False

    def test_policy_double_wildcard(self):
        policy = Policy(
            name="superadmin",
            effect=PermissionEffect.ALLOW,
            resource="*",
            action="*",
        )
        assert policy.matches("anything", "everything") is True


class TestBuiltinRoles:
    def test_viewer_permissions(self):
        assert BUILTIN_VIEWER.built_in is True
        assert BUILTIN_VIEWER.has_permission("tasks", "read") is True
        assert BUILTIN_VIEWER.has_permission("tasks", "create") is False
        assert BUILTIN_VIEWER.has_permission("rbac", "manage") is False

    def test_operator_permissions(self):
        assert BUILTIN_OPERATOR.built_in is True
        assert BUILTIN_OPERATOR.has_permission("tasks", "read") is True
        assert BUILTIN_OPERATOR.has_permission("tasks", "create") is True
        assert BUILTIN_OPERATOR.has_permission("tasks", "delegate") is True
        assert BUILTIN_OPERATOR.has_permission("rbac", "manage") is False

    def test_admin_permissions(self):
        assert BUILTIN_ADMIN.built_in is True
        assert BUILTIN_ADMIN.has_permission("tasks", "read") is True
        assert BUILTIN_ADMIN.has_permission("rbac", "manage") is True
        assert BUILTIN_ADMIN.has_permission("org", "manage") is True
        assert BUILTIN_ADMIN.has_permission("audit", "read") is True

    def test_permission_hierarchy(self):
        """Admin has all operator perms, operator has all viewer perms."""
        viewer_keys = {p.key for p in BUILTIN_VIEWER.permissions}
        operator_keys = {p.key for p in BUILTIN_OPERATOR.permissions}
        admin_keys = {p.key for p in BUILTIN_ADMIN.permissions}
        assert viewer_keys.issubset(operator_keys)
        assert operator_keys.issubset(admin_keys)


class TestAccessDecision:
    def test_allowed(self):
        d = AccessDecision(allowed=True, reason="Role 'admin' grants access")
        assert d.allowed is True

    def test_denied(self):
        d = AccessDecision(
            allowed=False,
            reason="No matching permission",
            matched_policies=["policy-1"],
        )
        assert d.allowed is False
        assert len(d.matched_policies) == 1


# ── Audit Trail Tests ───────────────────────────────────────────────────


class TestAuditEntry:
    def test_create_entry(self):
        entry = AuditEntry(
            actor_id="did:web:alice",
            action="task.created",
            category=AuditCategory.TASK,
            resource_type="task",
            resource_id="task-123",
        )
        assert entry.entry_id
        assert entry.level == AuditLevel.INFO
        assert entry.integrity_hash == ""

    def test_seal_entry(self):
        entry = AuditEntry(
            actor_id="did:web:alice",
            action="task.created",
            category=AuditCategory.TASK,
        )
        entry.seal(previous_hash="abc123")
        assert entry.previous_hash == "abc123"
        assert entry.integrity_hash != ""
        assert len(entry.integrity_hash) == 64  # SHA-256 hex

    def test_hash_chain(self):
        entry1 = AuditEntry(
            actor_id="did:web:alice",
            action="task.created",
            category=AuditCategory.TASK,
        )
        entry1.seal()

        entry2 = AuditEntry(
            actor_id="did:web:bob",
            action="contract.activated",
            category=AuditCategory.CONTRACT,
        )
        entry2.seal(previous_hash=entry1.integrity_hash)

        assert entry2.previous_hash == entry1.integrity_hash
        assert entry2.integrity_hash != entry1.integrity_hash

    def test_hash_deterministic(self):
        entry = AuditEntry(
            actor_id="did:web:alice",
            action="task.created",
            category=AuditCategory.TASK,
            entry_id="fixed-id",
            timestamp=datetime(2024, 1, 1),
        )
        entry.seal(previous_hash="prev")
        hash1 = entry.integrity_hash

        entry2 = AuditEntry(
            actor_id="did:web:alice",
            action="task.created",
            category=AuditCategory.TASK,
            entry_id="fixed-id",
            timestamp=datetime(2024, 1, 1),
        )
        entry2.seal(previous_hash="prev")
        assert entry2.integrity_hash == hash1

    def test_tamper_detection(self):
        entry = AuditEntry(
            actor_id="did:web:alice",
            action="task.created",
            category=AuditCategory.TASK,
        )
        entry.seal()
        original_hash = entry.integrity_hash

        # Tamper with the entry
        entry.action = "task.deleted"
        recomputed = entry.compute_hash()
        assert recomputed != original_hash

    def test_audit_levels(self):
        for level in AuditLevel:
            entry = AuditEntry(
                actor_id="a",
                action="test",
                category=AuditCategory.SYSTEM,
                level=level,
            )
            assert entry.level == level

    def test_all_categories(self):
        for cat in AuditCategory:
            entry = AuditEntry(
                actor_id="a",
                action="test",
                category=cat,
            )
            assert entry.category == cat


class TestAuditQuery:
    def test_default_query(self):
        q = AuditQuery()
        assert q.limit == 100
        assert q.offset == 0
        assert q.actor_id is None

    def test_filtered_query(self):
        q = AuditQuery(
            actor_id="did:web:alice",
            category=AuditCategory.TASK,
            level=AuditLevel.WARNING,
            limit=50,
        )
        assert q.actor_id == "did:web:alice"
        assert q.category == AuditCategory.TASK


# ── Organization Tests ──────────────────────────────────────────────────


class TestOrganization:
    def test_create_org(self):
        org = Organization(
            name="Acme Corp",
            slug="acme-corp",
            owner_id="did:web:alice",
        )
        assert org.is_active is True
        assert org.org_id
        assert org.max_agents == 100
        assert org.max_tasks_per_month == 10000

    def test_suspended_org(self):
        org = Organization(
            name="Bad Corp",
            slug="bad-corp",
            owner_id="did:web:eve",
            status=OrgStatus.SUSPENDED,
        )
        assert org.is_active is False

    def test_org_settings(self):
        org = Organization(
            name="Custom Corp",
            slug="custom",
            owner_id="did:web:alice",
            settings={
                "default_verification": "automated_test",
                "federation_enabled": True,
            },
        )
        assert org.settings["federation_enabled"] is True


class TestTeam:
    def test_create_team(self):
        team = Team(
            org_id="org-1",
            name="ML Agents",
            description="Machine learning agent team",
        )
        assert team.team_id
        assert team.org_id == "org-1"


class TestMembership:
    def test_create_membership(self):
        m = Membership(
            agent_id="did:web:alice",
            org_id="org-1",
            role=MemberRole.ADMIN,
        )
        assert m.active is True
        assert m.membership_id
        assert m.role == MemberRole.ADMIN

    def test_team_membership(self):
        m = Membership(
            agent_id="did:web:bob",
            org_id="org-1",
            team_id="team-1",
            role=MemberRole.MEMBER,
        )
        assert m.team_id == "team-1"

    def test_all_member_roles(self):
        for role in MemberRole:
            m = Membership(
                agent_id="did:web:test",
                org_id="org-1",
                role=role,
            )
            assert m.role == role


# ── Metering & Quotas Tests ────────────────────────────────────────────


class TestUsageRecord:
    def test_create_record(self):
        record = UsageRecord(
            org_id="org-1",
            agent_id="did:web:bot-1",
            dimension=MeterDimension.TASK_DELEGATIONS,
        )
        assert record.quantity == 1.0
        assert record.record_id

    def test_record_with_cost(self):
        record = UsageRecord(
            org_id="org-1",
            agent_id="did:web:bot-1",
            dimension=MeterDimension.COMPUTE_COST,
            quantity=42.5,
            task_id="task-1",
        )
        assert record.quantity == 42.5
        assert record.task_id == "task-1"


class TestQuota:
    def test_create_quota(self):
        q = Quota(
            org_id="org-1",
            dimension=MeterDimension.TASK_DELEGATIONS,
            limit=1000,
        )
        assert q.utilization == 0.0
        assert q.remaining == 1000
        assert q.is_exceeded is False
        assert q.is_warning is False
        assert q.period == QuotaPeriod.MONTHLY

    def test_quota_utilization(self):
        q = Quota(
            org_id="org-1",
            dimension=MeterDimension.TASK_DELEGATIONS,
            limit=100,
            current_usage=85,
        )
        assert q.utilization == 0.85
        assert q.remaining == 15
        assert q.is_warning is True
        assert q.is_exceeded is False

    def test_quota_exceeded(self):
        q = Quota(
            org_id="org-1",
            dimension=MeterDimension.TASK_DELEGATIONS,
            limit=100,
            current_usage=100,
        )
        assert q.is_exceeded is True
        assert q.remaining == 0

    def test_quota_zero_limit(self):
        q = Quota(
            org_id="org-1",
            dimension=MeterDimension.API_CALLS,
            limit=0,
        )
        assert q.utilization == 1.0

    def test_all_periods(self):
        for period in QuotaPeriod:
            q = Quota(
                org_id="org-1",
                dimension=MeterDimension.API_CALLS,
                limit=100,
                period=period,
            )
            assert q.period == period

    def test_all_dimensions(self):
        for dim in MeterDimension:
            q = Quota(org_id="org-1", dimension=dim, limit=100)
            assert q.dimension == dim


class TestQuotaExceededError:
    def test_error_message(self):
        err = QuotaExceededError(
            MeterDimension.TASK_DELEGATIONS, current=100, limit=100
        )
        assert "task_delegations" in str(err)
        assert "100" in str(err)
        assert err.dimension == MeterDimension.TASK_DELEGATIONS

    def test_error_attributes(self):
        err = QuotaExceededError(
            MeterDimension.API_CALLS, current=5000, limit=1000
        )
        assert err.current == 5000
        assert err.limit == 1000


class TestQuotaCheckResult:
    def test_allowed(self):
        r = QuotaCheckResult(
            allowed=True,
            dimension=MeterDimension.TASK_DELEGATIONS,
            current_usage=50,
            limit=100,
            remaining=50,
        )
        assert r.allowed is True

    def test_denied_with_warning(self):
        r = QuotaCheckResult(
            allowed=False,
            dimension=MeterDimension.TASK_DELEGATIONS,
            warning=True,
            message="Quota exceeded",
        )
        assert r.allowed is False
        assert r.warning is True


# ── Trust Analytics Tests ───────────────────────────────────────────────


class TestTrustTrend:
    def test_improving_trend(self):
        trend = TrustTrend(
            agent_id="did:web:bot-1",
            dimension="quality",
            direction=TrendDirection.IMPROVING,
            current_score=0.9,
            period_start_score=0.7,
            change_rate=0.01,
        )
        assert trend.absolute_change == pytest.approx(0.2)
        assert trend.percentage_change == pytest.approx(28.57, rel=0.01)

    def test_declining_trend(self):
        trend = TrustTrend(
            agent_id="did:web:bot-1",
            dimension="reliability",
            direction=TrendDirection.DECLINING,
            current_score=0.5,
            period_start_score=0.8,
        )
        assert trend.absolute_change == pytest.approx(-0.3)
        assert trend.percentage_change < 0

    def test_zero_start_score(self):
        trend = TrustTrend(
            agent_id="did:web:bot-1",
            dimension="overall",
            direction=TrendDirection.IMPROVING,
            current_score=0.5,
            period_start_score=0.0,
        )
        assert trend.percentage_change == 0.0

    def test_all_directions(self):
        for d in TrendDirection:
            trend = TrustTrend(
                agent_id="a",
                dimension="overall",
                direction=d,
                current_score=0.5,
                period_start_score=0.5,
            )
            assert trend.direction == d


class TestAnomalyAlert:
    def test_create_alert(self):
        alert = AnomalyAlert(
            agent_id="did:web:bot-1",
            severity=AlertSeverity.HIGH,
            anomaly_type="sudden_drop",
            dimension="quality",
            expected_value=0.85,
            actual_value=0.3,
            deviation=3.2,
            description="Quality score dropped 55 points in 24 hours",
            recommended_action="Pause delegations and investigate",
        )
        assert alert.alert_id
        assert alert.acknowledged is False
        assert alert.deviation == 3.2

    def test_all_severities(self):
        for s in AlertSeverity:
            alert = AnomalyAlert(
                agent_id="a",
                severity=s,
                anomaly_type="test",
                dimension="overall",
                expected_value=0.5,
                actual_value=0.5,
            )
            assert alert.severity == s


class TestAgentComparison:
    def test_create_comparison(self):
        comp = AgentComparison(
            domain="code_review",
            rankings=[
                {"agent_id": "did:web:bot-1", "score": 0.95, "rank": 1},
                {"agent_id": "did:web:bot-2", "score": 0.88, "rank": 2},
            ],
            total_agents=50,
            top_percentile=0.92,
            median_score=0.75,
        )
        assert comp.total_agents == 50
        assert len(comp.rankings) == 2
        assert comp.rankings[0]["rank"] == 1


class TestRiskAssessment:
    def test_create_assessment(self):
        risk = RiskAssessment(
            task_id="task-1",
            agent_id="did:web:bot-1",
            risk_level=RiskLevel.MODERATE,
            success_probability=0.72,
            risk_factors=[
                {"factor": "low_experience", "weight": 0.3},
                {"factor": "high_criticality", "weight": 0.5},
            ],
            mitigations=["Assign a human reviewer", "Reduce task scope"],
            confidence=0.8,
        )
        assert risk.risk_level == RiskLevel.MODERATE
        assert risk.success_probability == 0.72
        assert len(risk.risk_factors) == 2
        assert len(risk.mitigations) == 2

    def test_all_risk_levels(self):
        for level in RiskLevel:
            risk = RiskAssessment(
                task_id="t",
                agent_id="a",
                risk_level=level,
                success_probability=0.5,
            )
            assert risk.risk_level == level


# Need pytest import for approx
import pytest
