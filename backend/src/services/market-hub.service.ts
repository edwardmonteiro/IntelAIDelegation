/**
 * Decentralized Market Hub — bid evaluation and agent matching.
 *
 * Implements a three-phase pipeline for evaluating bids:
 *
 *   Phase 1 — Hard Filtering:
 *     Reject bids where the agent lacks required VerifiableCredentials,
 *     exceeds the task's max budget or duration, or has insufficient
 *     reputation.
 *
 *   Phase 2 — Multi-Objective Optimization:
 *     Rank surviving bids using a Pareto-optimal scoring function that
 *     balances cost, duration, and agent reputation. Identifies the
 *     Pareto frontier and selects the bid with the highest composite score.
 *
 *   Phase 3 — Contract Generation:
 *     Once a winning bid is selected, generate the SmartContract record
 *     linking the task, bid, and agreed verification/monitoring terms.
 */

import { createHash } from "crypto";
import { v4 as uuid } from "uuid";
import { prisma } from "../lib/prisma";
import type { BidRanking, SelectBid } from "../schemas/bid.schema";

// ============================================================================
// Phase 1: Hard Filtering
// ============================================================================

export interface FilterResult {
  eligible: EligibleBid[];
  rejected: RejectedBid[];
}

interface EligibleBid {
  bidId: string;
  agentId: string;
  proposedCost: number;
  proposedDurationSeconds: number;
  confidence: number;
  reputationBond: number;
  privacyGuarantee: string;
  agentReputation: number;
}

interface RejectedBid {
  bidId: string;
  agentId: string;
  reason: string;
}

/**
 * Phase 1: Apply hard filters to reject ineligible bids.
 *
 * Rejection criteria:
 *   1. Agent is inactive (circuit breaker triggered)
 *   2. Agent lacks required VerifiableCredentials for the task's domain
 *   3. Proposed cost exceeds the task's maximum budget (from SLA or spec)
 *   4. Proposed duration exceeds the task's deadline window
 *   5. Agent reputation below the task's criticality threshold
 */
export async function filterBids(taskId: string): Promise<FilterResult> {
  const task = await prisma.task.findUniqueOrThrow({
    where: { id: taskId },
    include: {
      bids: { include: { agent: true } },
    },
  });

  // Determine budget/duration constraints from the task
  const maxCost = (task.metadata as Record<string, unknown>)?.maxCost as
    | number
    | undefined;
  const deadlineMs = task.deadline
    ? task.deadline.getTime() - Date.now()
    : undefined;
  const maxDurationSeconds = deadlineMs
    ? Math.max(0, deadlineMs / 1000)
    : undefined;

  // Reputation threshold scales with criticality
  const reputationThreshold =
    task.criticality === "HIGH" ? 0.8 : task.criticality === "MEDIUM" ? 0.5 : 0.2;

  // Required credential domains: extracted from task metadata or verification spec
  const requiredDomains = extractRequiredDomains(task);

  const eligible: EligibleBid[] = [];
  const rejected: RejectedBid[] = [];

  for (const bid of task.bids) {
    const agent = bid.agent;

    // 1. Agent must be active
    if (!agent.activeStatus) {
      rejected.push({
        bidId: bid.id,
        agentId: bid.agentId,
        reason: "Agent is inactive (circuit breaker triggered)",
      });
      continue;
    }

    // 2. Agent must hold required credentials
    if (requiredDomains.length > 0) {
      const credentials = await prisma.verifiableCredential.findMany({
        where: {
          agentId: agent.id,
          revoked: false,
          skillDomain: { in: requiredDomains },
          OR: [{ expiresAt: null }, { expiresAt: { gt: new Date() } }],
        },
      });
      const heldDomains = new Set(credentials.map((c) => c.skillDomain));
      const missing = requiredDomains.filter((d) => !heldDomains.has(d));
      if (missing.length > 0) {
        rejected.push({
          bidId: bid.id,
          agentId: bid.agentId,
          reason: `Missing required credentials: ${missing.join(", ")}`,
        });
        continue;
      }
    }

    // 3. Cost must not exceed budget
    if (maxCost !== undefined && bid.proposedCost > maxCost) {
      rejected.push({
        bidId: bid.id,
        agentId: bid.agentId,
        reason: `Proposed cost ${bid.proposedCost} exceeds max budget ${maxCost}`,
      });
      continue;
    }

    // 4. Duration must not exceed deadline
    if (
      maxDurationSeconds !== undefined &&
      bid.proposedDurationSeconds > maxDurationSeconds
    ) {
      rejected.push({
        bidId: bid.id,
        agentId: bid.agentId,
        reason: `Proposed duration ${bid.proposedDurationSeconds}s exceeds available time ${maxDurationSeconds.toFixed(0)}s`,
      });
      continue;
    }

    // 5. Reputation must meet threshold
    if (agent.baseReputationScore < reputationThreshold) {
      rejected.push({
        bidId: bid.id,
        agentId: bid.agentId,
        reason: `Agent reputation ${agent.baseReputationScore} below threshold ${reputationThreshold}`,
      });
      continue;
    }

    eligible.push({
      bidId: bid.id,
      agentId: bid.agentId,
      proposedCost: bid.proposedCost,
      proposedDurationSeconds: bid.proposedDurationSeconds,
      confidence: bid.confidence,
      reputationBond: bid.reputationBond,
      privacyGuarantee: bid.privacyGuarantee,
      agentReputation: agent.baseReputationScore,
    });
  }

  return { eligible, rejected };
}

// ============================================================================
// Phase 2: Multi-Objective Optimization (Pareto Ranking)
// ============================================================================

/**
 * Rank eligible bids using Pareto-optimal multi-objective scoring.
 *
 * Three objectives (all normalized to [0, 1], higher = better):
 *   1. Cost efficiency:    1 - (bid_cost / max_cost_among_bids)
 *   2. Speed:              1 - (bid_duration / max_duration_among_bids)
 *   3. Reputation trust:   agent.baseReputationScore (already in [0, 1])
 *
 * A bid is Pareto-optimal if no other bid dominates it on ALL three
 * objectives simultaneously.
 *
 * The composite score weights: cost 35%, speed 25%, reputation 40%.
 * Reputation is weighted highest because the paper prioritizes trust.
 */
export function rankBids(eligible: EligibleBid[]): BidRanking[] {
  if (eligible.length === 0) return [];

  const maxCost = Math.max(...eligible.map((b) => b.proposedCost), 1);
  const maxDuration = Math.max(
    ...eligible.map((b) => b.proposedDurationSeconds),
    1
  );

  // Compute normalized scores for each bid
  const scored = eligible.map((bid) => {
    const costScore = 1 - bid.proposedCost / maxCost;
    const durationScore = 1 - bid.proposedDurationSeconds / maxDuration;
    const reputationScore = bid.agentReputation;

    // Weighted composite — reputation weighted highest per paper
    const compositeScore =
      costScore * 0.35 + durationScore * 0.25 + reputationScore * 0.4;

    return {
      bid,
      costScore,
      durationScore,
      reputationScore,
      compositeScore,
    };
  });

  // Determine Pareto frontier
  const paretoOptimal = new Set<string>();
  for (const candidate of scored) {
    let dominated = false;
    for (const other of scored) {
      if (other.bid.bidId === candidate.bid.bidId) continue;
      // 'other' dominates 'candidate' if it's >= on all objectives and > on at least one
      if (
        other.costScore >= candidate.costScore &&
        other.durationScore >= candidate.durationScore &&
        other.reputationScore >= candidate.reputationScore &&
        (other.costScore > candidate.costScore ||
          other.durationScore > candidate.durationScore ||
          other.reputationScore > candidate.reputationScore)
      ) {
        dominated = true;
        break;
      }
    }
    if (!dominated) {
      paretoOptimal.add(candidate.bid.bidId);
    }
  }

  // Sort by composite score descending
  scored.sort((a, b) => b.compositeScore - a.compositeScore);

  return scored.map(
    (s): BidRanking => ({
      bidId: s.bid.bidId,
      agentId: s.bid.agentId,
      compositeScore: round(s.compositeScore, 4),
      costScore: round(s.costScore, 4),
      durationScore: round(s.durationScore, 4),
      reputationScore: round(s.reputationScore, 4),
      isParetoOptimal: paretoOptimal.has(s.bid.bidId),
      rejected: false,
    })
  );
}

// ============================================================================
// Phase 3: Contract Generation
// ============================================================================

/**
 * Accept a winning bid and generate the SmartContract record.
 *
 * The contract binds the task, bid, delegator, delegatee, and the
 * agreed-upon verification method, monitoring cadence, and permissions.
 * A SHA-256 hash of the terms is stored as `contractTermsHash` for
 * immutable integrity verification.
 */
export async function acceptBidAndCreateContract(
  taskId: string,
  selection: SelectBid
) {
  // Load bid with agent and task
  const bid = await prisma.bid.findUniqueOrThrow({
    where: { id: selection.bidId },
    include: { agent: true, task: true },
  });

  if (bid.taskId !== taskId) {
    throw new MarketHubError(
      `Bid ${selection.bidId} does not belong to task ${taskId}`
    );
  }

  // Build contract terms for hashing
  const terms = {
    taskId,
    bidId: selection.bidId,
    delegatorId: bid.task.delegatorId,
    delegateeId: bid.agentId,
    proposedCost: bid.proposedCost,
    proposedDuration: bid.proposedDurationSeconds,
    reputationBond: bid.reputationBond,
    verificationMethod: selection.verificationMethod,
    monitoringCadence: selection.monitoringCadence,
    permissionsToGrant: selection.permissionsToGrant,
    timestamp: new Date().toISOString(),
  };

  const contractTermsHash = createHash("sha256")
    .update(JSON.stringify(terms))
    .digest("hex");

  // Create the contract
  const contract = await prisma.smartContract.create({
    data: {
      id: uuid(),
      taskId,
      bidId: selection.bidId,
      delegatorId: bid.task.delegatorId ?? bid.agentId,
      delegateeId: bid.agentId,
      status: "PROPOSED",
      verificationMethod: selection.verificationMethod,
      monitoringCadence: selection.monitoringCadence,
      contractTermsHash,
      slaMaxDurationSeconds: bid.proposedDurationSeconds,
      slaMaxCost: bid.proposedCost,
      permissionsGranted: selection.permissionsToGrant,
    },
    include: {
      task: true,
      bid: true,
      delegator: true,
      delegatee: true,
    },
  });

  // Transition task to ASSIGNED status
  await prisma.task.update({
    where: { id: taskId },
    data: { status: "ASSIGNED", assigneeId: bid.agentId },
  });

  return contract;
}

// ---------------------------------------------------------------------------
// Full pipeline: filter → rank → return results
// ---------------------------------------------------------------------------

export async function evaluateBids(taskId: string) {
  const { eligible, rejected } = await filterBids(taskId);

  const rankings = rankBids(eligible);

  // Merge rejection info
  const allRankings: BidRanking[] = [
    ...rankings,
    ...rejected.map(
      (r): BidRanking => ({
        bidId: r.bidId,
        agentId: r.agentId,
        compositeScore: 0,
        costScore: 0,
        durationScore: 0,
        reputationScore: 0,
        isParetoOptimal: false,
        rejected: true,
        rejectionReason: r.reason,
      })
    ),
  ];

  return {
    taskId,
    totalBids: eligible.length + rejected.length,
    eligibleCount: eligible.length,
    rejectedCount: rejected.length,
    rankings: allRankings,
    winner: rankings.length > 0 ? rankings[0] : null,
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function extractRequiredDomains(task: {
  metadata: unknown;
  verificationSpec: string;
}): string[] {
  const meta = task.metadata as Record<string, unknown> | null;
  if (meta && Array.isArray(meta.requiredCredentialDomains)) {
    return meta.requiredCredentialDomains as string[];
  }
  return [];
}

function round(n: number, decimals: number): number {
  const factor = Math.pow(10, decimals);
  return Math.round(n * factor) / factor;
}

export class MarketHubError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "MarketHubError";
  }
}
