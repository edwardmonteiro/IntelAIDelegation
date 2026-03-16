"""Tests for core data models."""

from datetime import datetime, timedelta

from intel_ai_delegation.models.agent import Agent, AgentCapability, AgentType
from intel_ai_delegation.models.contract import (
    Contract,
    ContractStatus,
    Penalty,
    ServiceLevelAgreement,
    VerificationMethod,
)
from intel_ai_delegation.models.credential import VerifiableCredential
from intel_ai_delegation.models.ledger import CompletionStatus, LedgerTransaction
from intel_ai_delegation.models.task import (
    ResourceRequirements,
    Task,
    TaskCriticality,
    TaskPriority,
    TaskStatus,
    VerificationCriteria,
)
from intel_ai_delegation.market.protocol import Bid


class TestTask:
    def test_create_task(self):
        task = Task(
            name="Test task",
            description="A test",
            verification=VerificationCriteria(
                method="automated_test",
                specification="assert result == 42",
            ),
        )
        assert task.status == TaskStatus.PENDING
        assert task.priority == TaskPriority.MEDIUM
        assert task.criticality == TaskCriticality.MEDIUM
        assert task.reversible is True
        assert task.is_leaf is True
        assert task.is_terminal is False
        assert task.task_id

    def test_task_with_sub_tasks(self):
        task = Task(
            name="Parent",
            description="Parent task",
            verification=VerificationCriteria(
                method="direct_inspection", specification="all sub-tasks pass"
            ),
            sub_task_ids=["child-1", "child-2"],
        )
        assert task.is_leaf is False

    def test_terminal_states(self):
        for status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            task = Task(
                name="t",
                description="d",
                verification=VerificationCriteria(
                    method="direct_inspection", specification="ok"
                ),
                status=status,
            )
            assert task.is_terminal is True

    def test_non_terminal_states(self):
        """DISPUTED and RE_DELEGATED are not terminal — they may be resolved."""
        for status in [TaskStatus.DISPUTED, TaskStatus.RE_DELEGATED]:
            task = Task(
                name="t",
                description="d",
                verification=VerificationCriteria(
                    method="direct_inspection", specification="ok"
                ),
                status=status,
            )
            assert task.is_terminal is False

    def test_criticality_and_reversibility(self):
        task = Task(
            name="High-stakes",
            description="Irreversible high-criticality task",
            verification=VerificationCriteria(
                method="cryptographic_zk_proof", specification="proof valid"
            ),
            criticality=TaskCriticality.HIGH,
            reversible=False,
        )
        assert task.criticality == TaskCriticality.HIGH
        assert task.reversible is False

    def test_resource_requirements(self):
        req = ResourceRequirements(
            capabilities=["code_review"],
            max_cost=100.0,
            max_duration=timedelta(hours=1),
            required_permissions=["api:read"],
        )
        assert req.capabilities == ["code_review"]
        assert req.max_cost == 100.0


class TestAgent:
    def test_create_agent(self):
        agent = Agent(name="TestBot", agent_type=AgentType.AI)
        assert agent.base_reputation_score == 0.5
        assert agent.active_status is True
        assert agent.has_capacity is True
        assert agent.agent_id.startswith("did:key:")

    def test_did_identity(self):
        agent = Agent(name="Custom", agent_id="did:web:example.com:agent-1")
        assert agent.agent_id == "did:web:example.com:agent-1"

    def test_public_key(self):
        agent = Agent(name="Signer", public_key="ed25519:abc123")
        assert agent.public_key == "ed25519:abc123"

    def test_capability_check(self):
        agent = Agent(
            name="Coder",
            capabilities=[
                AgentCapability(name="python", description="Python programming"),
                AgentCapability(name="review", description="Code review"),
            ],
        )
        assert agent.has_capability("python") is True
        assert agent.has_capability("java") is False

    def test_capacity_limit(self):
        agent = Agent(
            name="Busy",
            max_concurrent_tasks=2,
            current_task_ids=["t1", "t2"],
        )
        assert agent.has_capacity is False

    def test_circuit_breaker_deactivation(self):
        """When active_status is False (circuit breaker triggered),
        agent should not have capacity even with no tasks."""
        agent = Agent(name="Flagged", active_status=False)
        assert agent.has_capacity is False
        assert agent.is_available is False


class TestContract:
    def test_create_contract(self):
        contract = Contract(
            task_id="task-1",
            delegator_id="did:web:alice",
            delegatee_id="did:web:bot-1",
        )
        assert contract.status == ContractStatus.PROPOSED
        assert contract.is_active is False
        assert contract.is_terminal is False
        assert contract.verification_method == VerificationMethod.DIRECT_INSPECTION

    def test_contract_with_bid_and_terms_hash(self):
        contract = Contract(
            task_id="task-1",
            delegator_id="did:web:alice",
            delegatee_id="did:web:bot-1",
            bid_id="bid-123",
            monitoring_cadence="every_5m",
            contract_terms_hash="sha256:abcdef1234567890",
        )
        assert contract.bid_id == "bid-123"
        assert contract.monitoring_cadence == "every_5m"
        assert contract.contract_terms_hash == "sha256:abcdef1234567890"

    def test_verification_methods(self):
        for method in VerificationMethod:
            contract = Contract(
                task_id="t",
                delegator_id="a",
                delegatee_id="b",
                verification_method=method,
            )
            assert contract.verification_method == method

    def test_active_contract(self):
        contract = Contract(
            task_id="task-1",
            delegator_id="did:web:alice",
            delegatee_id="did:web:bot-1",
            status=ContractStatus.ACTIVE,
        )
        assert contract.is_active is True

    def test_terminal_states(self):
        for status in [
            ContractStatus.COMPLETED,
            ContractStatus.BREACHED,
            ContractStatus.TERMINATED,
            ContractStatus.EXPIRED,
        ]:
            contract = Contract(
                task_id="t",
                delegator_id="a",
                delegatee_id="b",
                status=status,
            )
            assert contract.is_terminal is True

    def test_sla_and_penalties(self):
        sla = ServiceLevelAgreement(
            max_duration=timedelta(hours=2),
            min_quality_score=0.9,
            max_cost=500.0,
        )
        penalty = Penalty(
            condition="deadline_exceeded",
            severity="high",
            reputation_impact=0.1,
        )
        contract = Contract(
            task_id="t",
            delegator_id="a",
            delegatee_id="b",
            sla=sla,
            penalties=[penalty],
        )
        assert contract.sla.min_quality_score == 0.9
        assert len(contract.penalties) == 1
        assert contract.penalties[0].severity == "high"


class TestVerifiableCredential:
    def test_create_credential(self):
        cred = VerifiableCredential(
            agent_id="did:web:bot-1",
            issuer_id="did:web:certifier",
            skill_domain="formal_code_verification",
            credential_hash="sha256:abc123",
        )
        assert cred.is_valid is True
        assert cred.skill_domain == "formal_code_verification"
        assert cred.credential_id  # auto-generated

    def test_revoked_credential(self):
        cred = VerifiableCredential(
            agent_id="did:web:bot-1",
            issuer_id="did:web:certifier",
            skill_domain="translation",
            revoked=True,
        )
        assert cred.is_valid is False

    def test_expired_credential(self):
        cred = VerifiableCredential(
            agent_id="did:web:bot-1",
            issuer_id="did:web:certifier",
            skill_domain="translation",
            expires_at=datetime(2020, 1, 1),
        )
        assert cred.is_valid is False


class TestLedgerTransaction:
    def test_create_transaction(self):
        tx = LedgerTransaction(
            task_id="task-1",
            delegatee_id="did:web:bot-1",
            completion_status=CompletionStatus.SUCCESS,
            quality_score=0.95,
            transparency_score=0.8,
            safety_score=1.0,
        )
        assert tx.transaction_id  # auto-generated
        assert tx.completion_status == CompletionStatus.SUCCESS

    def test_composite_score_default_weights(self):
        tx = LedgerTransaction(
            task_id="task-1",
            delegatee_id="did:web:bot-1",
            completion_status=CompletionStatus.SUCCESS,
            quality_score=0.8,
            transparency_score=0.6,
            safety_score=1.0,
        )
        # Default: quality 50%, transparency 25%, safety 25%
        expected = 0.8 * 0.5 + 0.6 * 0.25 + 1.0 * 0.25
        assert abs(tx.composite_score - expected) < 1e-9

    def test_composite_score_custom_weights(self):
        tx = LedgerTransaction(
            task_id="task-1",
            delegatee_id="did:web:bot-1",
            completion_status=CompletionStatus.PARTIAL,
            quality_score=0.5,
            transparency_score=0.5,
            safety_score=0.5,
            metadata={
                "score_weights": {
                    "quality": 0.34,
                    "transparency": 0.33,
                    "safety": 0.33,
                }
            },
        )
        expected = 0.5 * 0.34 + 0.5 * 0.33 + 0.5 * 0.33
        assert abs(tx.composite_score - expected) < 1e-9

    def test_resource_consumed(self):
        tx = LedgerTransaction(
            task_id="task-1",
            delegatee_id="did:web:bot-1",
            completion_status=CompletionStatus.SUCCESS,
            resource_consumed={"gpu_hours": 2.5, "api_tokens": 15000},
            verification_proof_hash="zk:proof:abc123",
        )
        assert tx.resource_consumed["gpu_hours"] == 2.5
        assert tx.verification_proof_hash == "zk:proof:abc123"

    def test_failure_status(self):
        tx = LedgerTransaction(
            task_id="task-1",
            delegatee_id="did:web:bot-1",
            completion_status=CompletionStatus.FAILURE,
            quality_score=0.0,
        )
        assert tx.completion_status == CompletionStatus.FAILURE


class TestBid:
    def test_create_bid(self):
        bid = Bid(
            task_id="task-1",
            agent_id="did:web:bot-1",
            proposed_cost=50.0,
            proposed_duration_seconds=3600,
        )
        assert bid.privacy_guarantee == "none"
        assert bid.reputation_bond == 0.0
        assert bid.bid_id  # auto-generated

    def test_bid_with_privacy_and_bond(self):
        bid = Bid(
            task_id="task-1",
            agent_id="did:web:bot-1",
            proposed_cost=100.0,
            proposed_duration_seconds=7200,
            privacy_guarantee="tee_enclave_sgx",
            reputation_bond=25.0,
        )
        assert bid.privacy_guarantee == "tee_enclave_sgx"
        assert bid.reputation_bond == 25.0
