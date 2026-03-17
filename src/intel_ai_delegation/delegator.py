"""Delegator — the top-level orchestrator for intelligent AI task delegation.

The Delegator ties together all framework components into a coherent
workflow: decompose -> advertise -> bid -> contract -> monitor -> verify.
It implements the adaptive coordination loop that reacts to monitoring
events and can re-delegate tasks at runtime.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from intel_ai_delegation.contracts.protocol import ContractManager
from intel_ai_delegation.coordination.protocol import ActionType, Coordinator
from intel_ai_delegation.decomposition.protocol import TaskDecomposer
from intel_ai_delegation.market.protocol import MarketHub
from intel_ai_delegation.models.contract import Contract
from intel_ai_delegation.models.ledger import CompletionStatus, LedgerTransaction
from intel_ai_delegation.models.task import Task, TaskStatus
from intel_ai_delegation.monitoring.protocol import Monitor
from intel_ai_delegation.permissions.protocol import PermissionManager
from intel_ai_delegation.trust.protocol import TrustLedger
from intel_ai_delegation.verification.protocol import Verifier, VerificationStatus

logger = logging.getLogger(__name__)


@dataclass
class DelegationResult:
    """Outcome of a full delegation cycle.

    Attributes:
        task: The root task (with sub-tasks populated).
        contracts: All contracts created during execution.
        success: Whether the overall task was verified successfully.
        verification_score: Aggregate verification score.
    """

    task: Task
    contracts: list[Contract]
    success: bool
    verification_score: float = 0.0


class Delegator:
    """Orchestrates the full intelligent delegation workflow.

    This is the primary entry point for users of the framework. It
    coordinates all subsystems to execute a task from start to finish.

    Usage::

        delegator = Delegator(
            decomposer=my_decomposer,
            market=my_market,
            contracts=my_contract_mgr,
            monitor=my_monitor,
            coordinator=my_coordinator,
            permissions=my_permission_mgr,
            verifier=my_verifier,
            trust=my_trust_ledger,
        )
        result = await delegator.delegate(task)
    """

    def __init__(
        self,
        decomposer: TaskDecomposer,
        market: MarketHub,
        contracts: ContractManager,
        monitor: Monitor,
        coordinator: Coordinator,
        permissions: PermissionManager,
        verifier: Verifier,
        trust: TrustLedger,
    ):
        self._decomposer = decomposer
        self._market = market
        self._contracts = contracts
        self._monitor = monitor
        self._coordinator = coordinator
        self._permissions = permissions
        self._verifier = verifier
        self._trust = trust

        self._task_registry: dict[str, Task] = {}
        self._contract_registry: dict[str, Contract] = {}

    async def delegate(self, task: Task) -> DelegationResult:
        """Execute the full delegation workflow for a task.

        Steps:
            1. Decompose into verifiable sub-tasks.
            2. For each leaf task: advertise, collect bids, assign.
            3. Create and activate contracts.
            4. Grant just-in-time permissions.
            5. Monitor execution with adaptive coordination.
            6. Verify completion.
            7. Record reputation on ledger and revoke permissions.

        Args:
            task: The task to delegate.

        Returns:
            DelegationResult with the outcome.
        """
        logger.info("Starting delegation for task %s: %s", task.task_id, task.name)

        # Step 1: Decompose
        task = await self._decomposer.decompose_recursive(task)
        self._register_task_tree(task)

        # Step 2-7: Execute all leaf tasks
        all_contracts = []
        leaf_tasks = self._get_leaf_tasks(task)

        for leaf in leaf_tasks:
            contract = await self._execute_leaf(leaf)
            if contract:
                all_contracts.append(contract)

        # Final verification of the root task
        overall_success = all(
            self._task_registry[tid].status == TaskStatus.COMPLETED
            for tid in self._get_all_task_ids(task)
            if self._task_registry[tid].is_leaf
        )

        if overall_success:
            task.status = TaskStatus.COMPLETED
        else:
            task.status = TaskStatus.FAILED

        return DelegationResult(
            task=task,
            contracts=all_contracts,
            success=overall_success,
        )

    async def _execute_leaf(self, task: Task) -> Contract | None:
        """Execute a single leaf task through the full lifecycle."""
        # Advertise on market (enter bidding phase)
        task.status = TaskStatus.BIDDING
        await self._market.advertise_task(task)

        # Collect bids and select best
        bids = await self._market.get_bids(task.task_id)
        if not bids:
            logger.warning("No bids received for task %s", task.task_id)
            task.status = TaskStatus.FAILED
            return None

        # Select best bid (first one for now — implementations can rank)
        best_bid = bids[0]
        await self._market.select_bid(task.task_id, best_bid.bid_id)

        # Create and activate contract
        contract = await self._contracts.create_contract(task, best_bid)
        contract = await self._contracts.activate_contract(contract.contract_id)
        self._contract_registry[contract.contract_id] = contract

        # Grant just-in-time permissions
        for perm in contract.permissions_granted:
            await self._permissions.grant(
                agent_id=contract.delegatee_id,
                task_id=task.task_id,
                scope=perm,
            )

        # Assign and monitor
        task.assignee_id = contract.delegatee_id
        task.status = TaskStatus.IN_PROGRESS
        await self._monitor.start_monitoring(task.task_id, contract.contract_id)

        # Adaptive coordination loop
        task = await self._coordination_loop(task, contract)

        # Verify
        if task.status == TaskStatus.UNDER_VERIFICATION:
            result = await self._verifier.verify(task)
            if result.status == VerificationStatus.PASSED:
                task.status = TaskStatus.COMPLETED
                await self._contracts.complete_contract(contract.contract_id)
                completion = CompletionStatus.SUCCESS
            else:
                task.status = TaskStatus.FAILED
                await self._contracts.report_breach(
                    contract.contract_id, "Verification failed"
                )
                completion = CompletionStatus.FAILURE

            # Record on immutable ledger
            await self._trust.record_transaction(
                LedgerTransaction(
                    task_id=task.task_id,
                    delegatee_id=contract.delegatee_id,
                    delegator_id=contract.delegator_id,
                    contract_id=contract.contract_id,
                    completion_status=completion,
                    quality_score=result.score,
                )
            )

        # Revoke all JIT permissions
        await self._permissions.revoke_all_for_task(task.task_id)
        await self._monitor.stop_monitoring(task.task_id)

        return contract

    async def _coordination_loop(self, task: Task, contract: Contract) -> Task:
        """Run the adaptive coordination loop until the task reaches a terminal or verification state."""
        while task.status == TaskStatus.IN_PROGRESS:
            events = await self._monitor.get_events(task.task_id)
            action = await self._coordinator.evaluate(events)

            if action.action_type == ActionType.CONTINUE:
                # Check if task reported completion
                for event in events:
                    if event.event_type == "completed":
                        task.status = TaskStatus.UNDER_VERIFICATION
                        break
                else:
                    continue

            elif action.action_type == ActionType.RE_DELEGATE:
                logger.info("Re-delegating task %s: %s", task.task_id, action.reason)
                await self._contracts.terminate_contract(
                    contract.contract_id, action.reason
                )
                await self._permissions.revoke_all_for_task(task.task_id)
                task.status = TaskStatus.RE_DELEGATED
                break

            elif action.action_type == ActionType.CANCEL:
                logger.info("Cancelling task %s: %s", task.task_id, action.reason)
                await self._contracts.terminate_contract(
                    contract.contract_id, action.reason
                )
                task.status = TaskStatus.CANCELLED
                break

            elif action.action_type == ActionType.PAUSE:
                task.status = TaskStatus.PAUSED

            elif action.action_type == ActionType.RESUME:
                task.status = TaskStatus.IN_PROGRESS

            else:
                await self._coordinator.execute_action(action)

        return task

    def _register_task_tree(self, task: Task) -> None:
        """Recursively register all tasks in the internal registry."""
        self._task_registry[task.task_id] = task

    def _get_leaf_tasks(self, task: Task) -> list[Task]:
        """Collect all leaf tasks from the registry."""
        return [t for t in self._task_registry.values() if t.is_leaf]

    def _get_all_task_ids(self, task: Task) -> list[str]:
        """Get all task IDs in the registry."""
        return list(self._task_registry.keys())
