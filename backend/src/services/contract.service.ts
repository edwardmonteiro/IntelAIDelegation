/**
 * Contract Service — lifecycle management for SmartContracts.
 *
 * Manages the full contract lifecycle:
 *   PROPOSED → ACCEPTED → ACTIVE → COMPLETED / BREACHED / TERMINATED
 *
 * Each state transition is validated, and terminal states trigger
 * LedgerTransaction recording for the reputation system.
 */

import { createHash } from "crypto";
import { v4 as uuid } from "uuid";
import { prisma } from "../lib/prisma";

// ============================================================================
// Contract Lifecycle Operations
// ============================================================================

/**
 * Accept a proposed contract — both parties agree to the terms.
 * Transitions: PROPOSED → ACCEPTED
 */
export async function acceptContract(contractId: string) {
  const contract = await prisma.smartContract.findUniqueOrThrow({
    where: { id: contractId },
  });

  if (contract.status !== "PROPOSED") {
    throw new ContractLifecycleError(
      `Cannot accept contract in ${contract.status} state`
    );
  }

  return prisma.smartContract.update({
    where: { id: contractId },
    data: { status: "ACCEPTED" },
  });
}

/**
 * Activate an accepted contract — execution begins.
 * Transitions: ACCEPTED → ACTIVE
 *
 * Side effects:
 *   - Task status → IN_PROGRESS
 *   - Permission grants created for the delegatee
 */
export async function activateContract(contractId: string) {
  const contract = await prisma.smartContract.findUniqueOrThrow({
    where: { id: contractId },
  });

  if (contract.status !== "ACCEPTED") {
    throw new ContractLifecycleError(
      `Cannot activate contract in ${contract.status} state`
    );
  }

  const now = new Date();

  // Activate contract
  const updated = await prisma.smartContract.update({
    where: { id: contractId },
    data: { status: "ACTIVE", activatedAt: now },
  });

  // Transition task to IN_PROGRESS
  await prisma.task.update({
    where: { id: contract.taskId },
    data: { status: "IN_PROGRESS" },
  });

  // Grant just-in-time permissions
  if (contract.permissionsGranted.length > 0) {
    const expiresAt = contract.slaMaxDurationSeconds
      ? new Date(now.getTime() + contract.slaMaxDurationSeconds * 1000)
      : undefined;

    await prisma.permissionGrant.createMany({
      data: contract.permissionsGranted.map((scope) => ({
        id: uuid(),
        agentId: contract.delegateeId,
        taskId: contract.taskId,
        contractId: contract.id,
        scope,
        resource: "*",
        expiresAt,
      })),
    });
  }

  return updated;
}

/**
 * Complete a contract — task verified successfully.
 * Transitions: ACTIVE → COMPLETED
 *
 * Side effects:
 *   - Task status → COMPLETED
 *   - LedgerTransaction recorded with SUCCESS
 *   - All permission grants revoked
 */
export async function completeContract(
  contractId: string,
  qualityScore: number = 1.0,
  transparencyScore: number = 1.0,
  safetyScore: number = 1.0,
  resourceConsumed: object = {}
) {
  const contract = await prisma.smartContract.findUniqueOrThrow({
    where: { id: contractId },
  });

  if (contract.status !== "ACTIVE") {
    throw new ContractLifecycleError(
      `Cannot complete contract in ${contract.status} state`
    );
  }

  const now = new Date();

  // Complete contract
  const updated = await prisma.smartContract.update({
    where: { id: contractId },
    data: { status: "COMPLETED", completedAt: now },
  });

  // Complete task
  await prisma.task.update({
    where: { id: contract.taskId },
    data: { status: "COMPLETED" },
  });

  // Record immutable ledger transaction
  await prisma.ledgerTransaction.create({
    data: {
      id: uuid(),
      taskId: contract.taskId,
      delegateeId: contract.delegateeId,
      delegatorId: contract.delegatorId,
      contractId: contract.id,
      completionStatus: "SUCCESS",
      qualityScore,
      transparencyScore,
      safetyScore,
      resourceConsumed,
    },
  });

  // Revoke all JIT permissions for this task
  await revokePermissionsForTask(contract.taskId);

  return updated;
}

/**
 * Report a contract breach — verification failed or terms violated.
 * Transitions: ACTIVE → BREACHED
 *
 * Side effects:
 *   - Task status → FAILED
 *   - LedgerTransaction recorded with FAILURE
 *   - ContractPenalty records created
 *   - All permissions revoked
 *   - Agent reputation may trigger circuit breaker
 */
export async function reportBreach(
  contractId: string,
  reason: string,
  penaltySeverity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" = "MEDIUM"
) {
  const contract = await prisma.smartContract.findUniqueOrThrow({
    where: { id: contractId },
  });

  if (contract.status !== "ACTIVE") {
    throw new ContractLifecycleError(
      `Cannot breach contract in ${contract.status} state`
    );
  }

  const now = new Date();

  // Breach contract
  const updated = await prisma.smartContract.update({
    where: { id: contractId },
    data: { status: "BREACHED", completedAt: now },
  });

  // Fail the task
  await prisma.task.update({
    where: { id: contract.taskId },
    data: { status: "FAILED" },
  });

  // Determine reputation impact based on severity
  const reputationImpact =
    penaltySeverity === "CRITICAL"
      ? 0.2
      : penaltySeverity === "HIGH"
        ? 0.1
        : penaltySeverity === "MEDIUM"
          ? 0.05
          : 0.02;

  // Record penalty
  await prisma.contractPenalty.create({
    data: {
      id: uuid(),
      contractId: contract.id,
      condition: reason,
      severity: penaltySeverity,
      reputationImpact,
      description: `Contract breach: ${reason}`,
    },
  });

  // Record failure on the immutable ledger
  await prisma.ledgerTransaction.create({
    data: {
      id: uuid(),
      taskId: contract.taskId,
      delegateeId: contract.delegateeId,
      delegatorId: contract.delegatorId,
      contractId: contract.id,
      completionStatus: "FAILURE",
      qualityScore: 0,
      transparencyScore: 0.5,
      safetyScore: 0.5,
    },
  });

  // Apply reputation penalty and check circuit breaker
  await applyReputationPenalty(contract.delegateeId, reputationImpact);

  // Revoke all permissions
  await revokePermissionsForTask(contract.taskId);

  return updated;
}

/**
 * Terminate a contract — voluntary early termination (e.g., re-delegation).
 * Transitions: ACTIVE | ACCEPTED → TERMINATED
 *
 * Side effects:
 *   - LedgerTransaction recorded with PARTIAL
 *   - Permissions revoked
 */
export async function terminateContract(contractId: string, reason: string) {
  const contract = await prisma.smartContract.findUniqueOrThrow({
    where: { id: contractId },
  });

  if (contract.status !== "ACTIVE" && contract.status !== "ACCEPTED") {
    throw new ContractLifecycleError(
      `Cannot terminate contract in ${contract.status} state`
    );
  }

  const now = new Date();

  const updated = await prisma.smartContract.update({
    where: { id: contractId },
    data: { status: "TERMINATED", completedAt: now },
  });

  // Record partial completion on ledger
  await prisma.ledgerTransaction.create({
    data: {
      id: uuid(),
      taskId: contract.taskId,
      delegateeId: contract.delegateeId,
      delegatorId: contract.delegatorId,
      contractId: contract.id,
      completionStatus: "PARTIAL",
      qualityScore: 0.5,
      metadata: { terminationReason: reason },
    },
  });

  await revokePermissionsForTask(contract.taskId);

  return updated;
}

// ============================================================================
// Contract Terms Verification
// ============================================================================

/**
 * Verify the integrity of a contract's terms by comparing the stored
 * hash against a freshly computed hash of the current terms.
 */
export async function verifyContractIntegrity(
  contractId: string
): Promise<{ valid: boolean; storedHash: string; computedHash: string }> {
  const contract = await prisma.smartContract.findUniqueOrThrow({
    where: { id: contractId },
    include: { bid: true },
  });

  const terms = {
    taskId: contract.taskId,
    bidId: contract.bidId,
    delegatorId: contract.delegatorId,
    delegateeId: contract.delegateeId,
    proposedCost: contract.bid.proposedCost,
    proposedDuration: contract.bid.proposedDurationSeconds,
    reputationBond: contract.bid.reputationBond,
    verificationMethod: contract.verificationMethod,
    monitoringCadence: contract.monitoringCadence,
    permissionsToGrant: contract.permissionsGranted,
  };

  const computedHash = createHash("sha256")
    .update(JSON.stringify(terms))
    .digest("hex");

  return {
    valid: contract.contractTermsHash === computedHash,
    storedHash: contract.contractTermsHash,
    computedHash,
  };
}

// ============================================================================
// Internal helpers
// ============================================================================

/**
 * Revoke all active permission grants for a task.
 */
async function revokePermissionsForTask(taskId: string) {
  await prisma.permissionGrant.updateMany({
    where: { taskId, revoked: false },
    data: { revoked: true },
  });
}

/**
 * Apply a reputation penalty to an agent and check the circuit breaker.
 *
 * If the agent's reputation drops below 0.15, the circuit breaker triggers
 * and deactivates the agent automatically.
 */
async function applyReputationPenalty(agentId: string, impact: number) {
  const agent = await prisma.agent.findUniqueOrThrow({
    where: { id: agentId },
  });

  const newScore = Math.max(0, agent.baseReputationScore - impact);

  // Circuit breaker: deactivate if reputation drops below threshold
  const circuitBreakerThreshold = 0.15;
  const shouldDeactivate = newScore < circuitBreakerThreshold;

  await prisma.agent.update({
    where: { id: agentId },
    data: {
      baseReputationScore: newScore,
      activeStatus: shouldDeactivate ? false : agent.activeStatus,
    },
  });

  if (shouldDeactivate) {
    console.warn(
      `[CIRCUIT BREAKER] Agent ${agentId} deactivated — reputation ${newScore.toFixed(3)} ` +
        `below threshold ${circuitBreakerThreshold}`
    );
  }
}

// ============================================================================
// Errors
// ============================================================================

export class ContractLifecycleError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ContractLifecycleError";
  }
}
