import { z } from "zod";

// ---------------------------------------------------------------------------
// Bid Submission — input from agents bidding on tasks
// ---------------------------------------------------------------------------

export const SubmitBidSchema = z.object({
  taskId: z.string().uuid(),
  agentId: z.string().min(1, "Agent DID is required"),
  proposedCost: z.number().nonnegative(),
  proposedDurationSeconds: z.number().positive(),
  confidence: z.number().min(0).max(1).default(1.0),
  privacyGuarantee: z
    .enum(["none", "tee_enclave_sgx", "tee_enclave_sev", "zk_snark", "mpc"])
    .default("none"),
  reputationBond: z.number().nonnegative().default(0),
  message: z.string().default(""),
});
export type SubmitBid = z.infer<typeof SubmitBidSchema>;

// ---------------------------------------------------------------------------
// Bid Ranking — output of the multi-objective optimization pipeline
// ---------------------------------------------------------------------------

export const BidRankingSchema = z.object({
  bidId: z.string().uuid(),
  agentId: z.string(),
  compositeScore: z.number(),
  costScore: z.number(),
  durationScore: z.number(),
  reputationScore: z.number(),
  isParetoOptimal: z.boolean(),
  rejected: z.boolean().default(false),
  rejectionReason: z.string().optional(),
});
export type BidRanking = z.infer<typeof BidRankingSchema>;

// ---------------------------------------------------------------------------
// Select Bid Request
// ---------------------------------------------------------------------------

export const SelectBidSchema = z.object({
  bidId: z.string().uuid(),
  verificationMethod: z
    .enum([
      "DIRECT_INSPECTION",
      "THIRD_PARTY_AUDIT",
      "CRYPTOGRAPHIC_ZK_PROOF",
      "CONSENSUS_GAME",
      "AUTOMATED_TEST",
    ])
    .default("DIRECT_INSPECTION"),
  monitoringCadence: z
    .enum(["real_time", "every_1m", "every_5m", "on_checkpoint", "on_completion"])
    .default("on_completion"),
  permissionsToGrant: z.array(z.string()).default([]),
});
export type SelectBid = z.infer<typeof SelectBidSchema>;
