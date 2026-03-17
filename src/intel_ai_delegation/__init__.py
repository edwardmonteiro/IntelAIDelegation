"""
Intel AI Delegation - Open Format Framework for Intelligent AI Task Delegation.

An open-format implementation of the Intelligent AI Delegation framework,
enabling safe and effective distribution of tasks among AI agents and humans.

Core concepts:
    - Contract-First Decomposition: Recursive task breakdown with verifiable outcomes
    - Market-Based Assignment: Decentralized agent discovery and bidding
    - Smart Contracts: Formal agreements with automated verification and penalties
    - Dynamic Monitoring: Progress tracking from outcome-level to process-level
    - Adaptive Coordination: Runtime re-delegation and fault recovery
    - Just-In-Time Permissions: Scoped, time-limited access grants
    - Verifiable Completion: Inspection, audit, and cryptographic proof of results
    - Trust & Reputation: Immutable ledger of agent performance history
"""

__version__ = "0.1.0"

from intel_ai_delegation.models.agent import Agent, AgentCapability, AgentType
from intel_ai_delegation.models.contract import Contract, ContractStatus, VerificationMethod
from intel_ai_delegation.models.credential import VerifiableCredential
from intel_ai_delegation.models.ledger import CompletionStatus, LedgerTransaction
from intel_ai_delegation.models.task import Task, TaskCriticality, TaskPriority, TaskStatus

__all__ = [
    "Agent",
    "AgentCapability",
    "AgentType",
    "CompletionStatus",
    "Contract",
    "ContractStatus",
    "LedgerTransaction",
    "Task",
    "TaskCriticality",
    "TaskPriority",
    "TaskStatus",
    "VerifiableCredential",
    "VerificationMethod",
]
