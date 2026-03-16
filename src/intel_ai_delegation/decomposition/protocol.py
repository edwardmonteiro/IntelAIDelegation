"""Protocol for task decomposition.

A TaskDecomposer recursively breaks a complex task into sub-tasks until
each leaf task's outcome can be strictly and precisely verified. This is
the "contract-first" approach: verification criteria must be defined
before a task is considered properly decomposed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from intel_ai_delegation.models.task import Task


class TaskDecomposer(ABC):
    """Abstract base for task decomposition strategies.

    Implementations may use LLM-based planning, rule engines, or
    domain-specific heuristics to break tasks down.
    """

    @abstractmethod
    async def decompose(self, task: Task) -> list[Task]:
        """Decompose a task into a list of verifiable sub-tasks.

        Each sub-task must have its own VerificationCriteria defined.
        The decomposition continues recursively until every leaf task
        is directly verifiable.

        Args:
            task: The parent task to decompose.

        Returns:
            A list of sub-tasks. An empty list means the task is already
            a leaf (directly executable and verifiable).

        Raises:
            DecompositionError: If the task cannot be meaningfully decomposed.
        """
        ...

    @abstractmethod
    async def is_verifiable(self, task: Task) -> bool:
        """Determine whether a task's outcome can be strictly verified.

        A task is verifiable if its verification criteria are sufficiently
        precise that an automated or human verifier can objectively assess
        whether the outcome meets the specification.

        Args:
            task: The task to evaluate.

        Returns:
            True if the task is directly verifiable without further decomposition.
        """
        ...

    async def decompose_recursive(self, task: Task) -> Task:
        """Recursively decompose until all leaves are verifiable.

        This is a convenience method that calls decompose() and
        is_verifiable() in a loop.

        Args:
            task: The root task.

        Returns:
            The root task with sub_task_ids populated throughout the tree.
        """
        if await self.is_verifiable(task):
            return task

        sub_tasks = await self.decompose(task)
        for sub_task in sub_tasks:
            sub_task.parent_id = task.task_id
            task.sub_task_ids.append(sub_task.task_id)
            await self.decompose_recursive(sub_task)

        return task


class DecompositionError(Exception):
    """Raised when a task cannot be decomposed."""
