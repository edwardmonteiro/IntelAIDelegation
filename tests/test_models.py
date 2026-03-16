"""Tests for core data models."""

from datetime import timedelta

from intel_ai_delegation.models.agent import Agent, AgentCapability, AgentType
from intel_ai_delegation.models.contract import (
    Contract,
    ContractStatus,
    Penalty,
    ServiceLevelAgreement,
)
from intel_ai_delegation.models.task import (
    ResourceRequirements,
    Task,
    TaskPriority,
    TaskStatus,
    VerificationCriteria,
)


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
        assert task.status == TaskStatus.DRAFT
        assert task.priority == TaskPriority.MEDIUM
        assert task.is_leaf is True
        assert task.is_terminal is False
        assert task.task_id  # auto-generated

    def test_task_with_sub_tasks(self):
        task = Task(
            name="Parent",
            description="Parent task",
            verification=VerificationCriteria(method="direct_inspection", specification="all sub-tasks pass"),
            sub_task_ids=["child-1", "child-2"],
        )
        assert task.is_leaf is False

    def test_terminal_states(self):
        for status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            task = Task(
                name="t",
                description="d",
                verification=VerificationCriteria(method="direct_inspection", specification="ok"),
                status=status,
            )
            assert task.is_terminal is True

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
        assert agent.trust_score == 0.5
        assert agent.has_capacity is True
        assert agent.agent_id

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

    def test_unavailable_agent(self):
        agent = Agent(name="Offline", is_available=False)
        assert agent.has_capacity is False


class TestContract:
    def test_create_contract(self):
        contract = Contract(
            task_id="task-1",
            delegator_id="alice",
            delegatee_id="bot-1",
        )
        assert contract.status == ContractStatus.PROPOSED
        assert contract.is_active is False
        assert contract.is_terminal is False

    def test_active_contract(self):
        contract = Contract(
            task_id="task-1",
            delegator_id="alice",
            delegatee_id="bot-1",
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
