import { z } from "zod";

// ---------------------------------------------------------------------------
// Enums — match Prisma enums exactly
// ---------------------------------------------------------------------------

export const TaskCriticalitySchema = z.enum(["LOW", "MEDIUM", "HIGH"]);
export const TaskPrioritySchema = z.enum(["CRITICAL", "HIGH", "MEDIUM", "LOW"]);
export const TaskStatusSchema = z.enum([
  "PENDING",
  "BIDDING",
  "ASSIGNED",
  "IN_PROGRESS",
  "PAUSED",
  "UNDER_VERIFICATION",
  "COMPLETED",
  "FAILED",
  "CANCELLED",
  "DISPUTED",
  "RE_DELEGATED",
]);
export const VerificationMethodSchema = z.enum([
  "DIRECT_INSPECTION",
  "THIRD_PARTY_AUDIT",
  "CRYPTOGRAPHIC_ZK_PROOF",
  "CONSENSUS_GAME",
  "AUTOMATED_TEST",
]);

// ---------------------------------------------------------------------------
// Resource Boundaries — limits the agent's resource consumption
// ---------------------------------------------------------------------------

export const ResourceBoundariesSchema = z.object({
  maxCost: z.number().nonnegative().optional(),
  maxDurationSeconds: z.number().positive().optional(),
  requiredCapabilities: z.array(z.string()).default([]),
  requiredPermissions: z.array(z.string()).default([]),
});
export type ResourceBoundaries = z.infer<typeof ResourceBoundariesSchema>;

// ---------------------------------------------------------------------------
// Monitoring Policy — how the delegator will observe progress
// ---------------------------------------------------------------------------

export const MonitoringPolicySchema = z.object({
  cadence: z
    .enum(["real_time", "every_1m", "every_5m", "on_checkpoint", "on_completion"])
    .default("on_completion"),
  escalationThreshold: z.number().min(0).max(1).default(0.3),
  healthCheckIntervalSeconds: z.number().positive().optional(),
});
export type MonitoringPolicy = z.infer<typeof MonitoringPolicySchema>;

// ---------------------------------------------------------------------------
// Verification Policy — how outcomes are judged
// ---------------------------------------------------------------------------

export const VerificationPolicySchema = z.object({
  method: VerificationMethodSchema.default("DIRECT_INSPECTION"),
  specification: z.string().min(1, "Verification specification is required"),
  acceptanceThreshold: z.number().min(0).max(1).default(1.0),
  timeoutSeconds: z.number().positive().optional(),
});
export type VerificationPolicy = z.infer<typeof VerificationPolicySchema>;

// ---------------------------------------------------------------------------
// Sub-Task Draft — output of the initial decomposition analysis
// ---------------------------------------------------------------------------

export const SubTaskDraftSchema = z.object({
  name: z.string().min(1),
  description: z.string().min(1),
  objective: z.string().min(1),
  criticality: TaskCriticalitySchema.default("MEDIUM"),
  reversible: z.boolean().default(true),
  priority: TaskPrioritySchema.default("MEDIUM"),
  estimatedDurationSeconds: z.number().positive().optional(),
  estimatedCost: z.number().nonnegative().optional(),
  requiredCapabilities: z.array(z.string()).default([]),
  verifiable: z.boolean().default(false),
  verificationHint: z.string().optional(),
});
export type SubTaskDraft = z.infer<typeof SubTaskDraftSchema>;

// ---------------------------------------------------------------------------
// Analyze Request — input to POST /api/v1/decompose/analyze
// ---------------------------------------------------------------------------

export const AnalyzeRequestSchema = z.object({
  objective: z.string().min(5, "Objective must be at least 5 characters"),
  delegatorId: z.string().min(1, "Delegator ID (DID) is required"),
  criticality: TaskCriticalitySchema.default("MEDIUM"),
  reversible: z.boolean().default(true),
  deadline: z.string().datetime().optional(),
  maxBudget: z.number().nonnegative().optional(),
  context: z.record(z.unknown()).optional(),
});
export type AnalyzeRequest = z.infer<typeof AnalyzeRequestSchema>;

// ---------------------------------------------------------------------------
// Analyze Response — output of decomposition analysis
// ---------------------------------------------------------------------------

export const AnalyzeResponseSchema = z.object({
  jobId: z.string().uuid(),
  rootObjective: z.string(),
  delegatorId: z.string(),
  subTasks: z.array(SubTaskDraftSchema),
  allVerifiable: z.boolean(),
  unverifiableCount: z.number().int().nonnegative(),
  createdAt: z.string().datetime(),
});
export type AnalyzeResponse = z.infer<typeof AnalyzeResponseSchema>;

// ---------------------------------------------------------------------------
// Verify Outcomes Response
// ---------------------------------------------------------------------------

export const VerifyOutcomesResponseSchema = z.object({
  jobId: z.string().uuid(),
  subTasks: z.array(
    SubTaskDraftSchema.extend({
      verifiable: z.boolean(),
      verificationReason: z.string().optional(),
    })
  ),
  allVerifiable: z.boolean(),
  iterationCount: z.number().int().positive(),
});
export type VerifyOutcomesResponse = z.infer<typeof VerifyOutcomesResponseSchema>;

// ---------------------------------------------------------------------------
// Task Specification — the final, formalized output of decomposition
// ---------------------------------------------------------------------------

export const RoleSpecSchema = z.object({
  role: z.enum(["delegatee", "verifier", "monitor"]),
  requiredCapabilities: z.array(z.string()),
  minReputationScore: z.number().min(0).max(1).default(0.0),
  requiredCredentialDomains: z.array(z.string()).default([]),
});
export type RoleSpec = z.infer<typeof RoleSpecSchema>;

export const TaskSpecificationSchema = z.object({
  jobId: z.string().uuid(),
  rootTaskId: z.string().uuid(),
  delegatorId: z.string(),
  tasks: z.array(
    z.object({
      taskId: z.string().uuid(),
      parentTaskId: z.string().uuid().nullable(),
      name: z.string(),
      description: z.string(),
      objective: z.string(),
      criticality: TaskCriticalitySchema,
      reversible: z.boolean(),
      priority: TaskPrioritySchema,
      roles: z.array(RoleSpecSchema),
      resourceBoundaries: ResourceBoundariesSchema,
      monitoringPolicy: MonitoringPolicySchema,
      verificationPolicy: VerificationPolicySchema,
    })
  ),
  totalEstimatedCost: z.number().nonnegative().optional(),
  totalEstimatedDurationSeconds: z.number().positive().optional(),
  finalizedAt: z.string().datetime(),
});
export type TaskSpecification = z.infer<typeof TaskSpecificationSchema>;
