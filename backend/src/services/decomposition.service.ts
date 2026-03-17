/**
 * Task Decomposition Engine — contract-first recursive decomposition.
 *
 * Enforces the paper's core rule: a task is recursively broken down until
 * every leaf sub-task has an outcome that can be **strictly and precisely
 * verified**. The engine produces a Task Specification payload containing
 * roles, resource boundaries, monitoring policy, and verification policy.
 *
 * Three-phase API:
 *   1. analyze   — decompose a high-level objective into sub-task drafts
 *   2. verify    — recursively check that every sub-task is verifiable
 *   3. finalize  — produce the formal TaskSpecification payload
 */

import { v4 as uuid } from "uuid";
import { prisma } from "../lib/prisma";
import type {
  AnalyzeRequest,
  AnalyzeResponse,
  SubTaskDraft,
  VerifyOutcomesResponse,
  TaskSpecification,
  MonitoringPolicy,
  VerificationPolicy,
  ResourceBoundaries,
  RoleSpec,
} from "../schemas/task.schema";

// ---------------------------------------------------------------------------
// In-memory job store — tracks decomposition sessions in progress.
// In production this would be Redis or a database table.
// ---------------------------------------------------------------------------

interface DecompositionJob {
  jobId: string;
  rootObjective: string;
  delegatorId: string;
  criticality: "LOW" | "MEDIUM" | "HIGH";
  reversible: boolean;
  deadline?: string;
  maxBudget?: number;
  subTasks: SubTaskDraft[];
  iterationCount: number;
  finalized: boolean;
  createdAt: string;
}

const jobStore = new Map<string, DecompositionJob>();

// ---------------------------------------------------------------------------
// Phase 1: Analyze — decompose objective into sub-task drafts
// ---------------------------------------------------------------------------

/**
 * Accept a high-level objective and return an initial decomposition draft.
 *
 * The decomposition heuristic:
 *   - High criticality objectives get finer-grained decomposition
 *   - Each sub-task is annotated with a `verifiable` flag based on whether
 *     its outcome can be expressed as a deterministic assertion
 *   - Non-verifiable sub-tasks are flagged for further decomposition in
 *     the verify phase
 */
export async function analyzeObjective(
  req: AnalyzeRequest
): Promise<AnalyzeResponse> {
  const jobId = uuid();

  // Heuristic decomposition — in production this would call an LLM or a
  // domain-specific planning engine. Here we apply structural rules.
  const subTasks = decomposeByStructure(req.objective, req.criticality);

  const job: DecompositionJob = {
    jobId,
    rootObjective: req.objective,
    delegatorId: req.delegatorId,
    criticality: req.criticality,
    reversible: req.reversible,
    deadline: req.deadline,
    maxBudget: req.maxBudget,
    subTasks,
    iterationCount: 0,
    finalized: false,
    createdAt: new Date().toISOString(),
  };
  jobStore.set(jobId, job);

  const unverifiableCount = subTasks.filter((t) => !t.verifiable).length;

  return {
    jobId,
    rootObjective: req.objective,
    delegatorId: req.delegatorId,
    subTasks,
    allVerifiable: unverifiableCount === 0,
    unverifiableCount,
    createdAt: job.createdAt,
  };
}

// ---------------------------------------------------------------------------
// Phase 2: Verify Outcomes — recursively check verifiability
// ---------------------------------------------------------------------------

/**
 * Iteratively refine sub-tasks until every outcome is verifiable.
 *
 * For each non-verifiable sub-task, the engine either:
 *   a) further decomposes it into smaller verifiable units, or
 *   b) assigns a concrete verification specification that makes it verifiable.
 *
 * The process halts when all leaves are verifiable or a max iteration
 * limit is reached.
 */
export async function verifyOutcomes(
  jobId: string
): Promise<VerifyOutcomesResponse> {
  const job = jobStore.get(jobId);
  if (!job) {
    throw new DecompositionError(`Job ${jobId} not found`);
  }
  if (job.finalized) {
    throw new DecompositionError(`Job ${jobId} is already finalized`);
  }

  const MAX_ITERATIONS = 5;
  let iterations = 0;

  while (iterations < MAX_ITERATIONS) {
    iterations++;
    const unverifiable = job.subTasks.filter((t) => !t.verifiable);
    if (unverifiable.length === 0) break;

    // Attempt to make each unverifiable task verifiable
    const refined: SubTaskDraft[] = [];
    for (const task of job.subTasks) {
      if (task.verifiable) {
        refined.push(task);
        continue;
      }

      // Strategy 1: If the task can be given a concrete verification spec,
      // mark it verifiable directly.
      const spec = inferVerificationSpec(task);
      if (spec) {
        refined.push({
          ...task,
          verifiable: true,
          verificationHint: spec,
        });
        continue;
      }

      // Strategy 2: Decompose further into smaller verifiable pieces.
      const children = decomposeByStructure(task.objective, job.criticality);
      refined.push(...children);
    }

    job.subTasks = refined;
  }

  job.iterationCount += iterations;

  const annotated = job.subTasks.map((t) => ({
    ...t,
    verificationReason: t.verifiable
      ? `Outcome verifiable via: ${t.verificationHint ?? "deterministic assertion"}`
      : "Could not determine verification method within iteration limit",
  }));

  return {
    jobId,
    subTasks: annotated,
    allVerifiable: job.subTasks.every((t) => t.verifiable),
    iterationCount: job.iterationCount,
  };
}

// ---------------------------------------------------------------------------
// Phase 3: Finalize — produce the formal TaskSpecification
// ---------------------------------------------------------------------------

/**
 * Generate the final TaskSpecification payload.
 *
 * This persists the task tree into the database and produces the
 * specification that the Market Hub will use to solicit bids.
 */
export async function finalizeDecomposition(
  jobId: string
): Promise<TaskSpecification> {
  const job = jobStore.get(jobId);
  if (!job) {
    throw new DecompositionError(`Job ${jobId} not found`);
  }
  if (job.finalized) {
    throw new DecompositionError(`Job ${jobId} is already finalized`);
  }

  const unverifiable = job.subTasks.filter((t) => !t.verifiable);
  if (unverifiable.length > 0) {
    throw new DecompositionError(
      `Cannot finalize: ${unverifiable.length} sub-task(s) are not yet verifiable. ` +
        `Call POST /api/v1/decompose/${jobId}/verify-outcomes first.`
    );
  }

  // Persist root task
  const rootTaskId = uuid();
  await prisma.task.create({
    data: {
      id: rootTaskId,
      name: job.rootObjective.slice(0, 100),
      description: job.rootObjective,
      objective: job.rootObjective,
      criticality: job.criticality,
      reversible: job.reversible,
      priority: criticalityToPriority(job.criticality),
      delegatorId: job.delegatorId,
      status: "PENDING",
      deadline: job.deadline ? new Date(job.deadline) : undefined,
    },
  });

  // Persist each sub-task and build the specification
  const taskSpecs = await Promise.all(
    job.subTasks.map(async (draft) => {
      const taskId = uuid();

      const verificationPolicy: VerificationPolicy = {
        method: inferVerificationMethod(draft),
        specification: draft.verificationHint ?? "assert outcome meets specification",
        acceptanceThreshold:
          job.criticality === "HIGH" ? 0.99 : job.criticality === "MEDIUM" ? 0.95 : 0.9,
      };

      const monitoringPolicy: MonitoringPolicy = {
        cadence: job.criticality === "HIGH" ? "every_1m" : "on_checkpoint",
        escalationThreshold: job.criticality === "HIGH" ? 0.2 : 0.3,
      };

      const resourceBoundaries: ResourceBoundaries = {
        maxCost: draft.estimatedCost,
        maxDurationSeconds: draft.estimatedDurationSeconds,
        requiredCapabilities: draft.requiredCapabilities,
        requiredPermissions: [],
      };

      const roles: RoleSpec[] = [
        {
          role: "delegatee",
          requiredCapabilities: draft.requiredCapabilities,
          minReputationScore: job.criticality === "HIGH" ? 0.8 : 0.5,
          requiredCredentialDomains: draft.requiredCapabilities,
        },
      ];

      // Add a verifier role for high-criticality tasks
      if (job.criticality === "HIGH") {
        roles.push({
          role: "verifier",
          requiredCapabilities: ["verification", ...draft.requiredCapabilities],
          minReputationScore: 0.85,
          requiredCredentialDomains: ["verification"],
        });
      }

      await prisma.task.create({
        data: {
          id: taskId,
          parentTaskId: rootTaskId,
          name: draft.name,
          description: draft.description,
          objective: draft.objective,
          criticality: draft.criticality,
          reversible: draft.reversible,
          priority: draft.priority,
          verificationMethod: verificationPolicy.method
            .toLowerCase()
            .replace(/_([a-z])/g, (_, c: string) => c.toUpperCase()),
          verificationSpec: verificationPolicy.specification,
          acceptanceThreshold: verificationPolicy.acceptanceThreshold,
          delegatorId: job.delegatorId,
          status: "PENDING",
        },
      });

      return {
        taskId,
        parentTaskId: rootTaskId,
        name: draft.name,
        description: draft.description,
        objective: draft.objective,
        criticality: draft.criticality,
        reversible: draft.reversible,
        priority: draft.priority,
        roles,
        resourceBoundaries,
        monitoringPolicy,
        verificationPolicy,
      };
    })
  );

  job.finalized = true;

  const now = new Date().toISOString();

  return {
    jobId,
    rootTaskId,
    delegatorId: job.delegatorId,
    tasks: taskSpecs,
    totalEstimatedCost: job.subTasks.reduce(
      (sum, t) => sum + (t.estimatedCost ?? 0),
      0
    ),
    totalEstimatedDurationSeconds: Math.max(
      ...job.subTasks.map((t) => t.estimatedDurationSeconds ?? 0),
      0
    ),
    finalizedAt: now,
  };
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Structural decomposition heuristic.
 *
 * Breaks an objective into sub-tasks based on common patterns:
 *   - Data gathering / analysis / implementation / verification steps
 *   - Higher criticality = more granular decomposition
 *
 * In production, an LLM-based planner would replace this.
 */
function decomposeByStructure(
  objective: string,
  criticality: "LOW" | "MEDIUM" | "HIGH"
): SubTaskDraft[] {
  const objectiveLower = objective.toLowerCase();
  const tasks: SubTaskDraft[] = [];

  // Phase 1: Research / data gathering
  tasks.push({
    name: `Research: ${truncate(objective, 60)}`,
    description: `Gather requirements, context, and constraints for: ${objective}`,
    objective: `Produce a structured requirements document for: ${objective}`,
    criticality,
    reversible: true,
    priority: "HIGH",
    requiredCapabilities: ["research", "analysis"],
    verifiable: true,
    verificationHint:
      "Verify that the requirements document covers all specified constraints",
  });

  // Phase 2: Implementation / execution
  tasks.push({
    name: `Execute: ${truncate(objective, 60)}`,
    description: `Carry out the core work for: ${objective}`,
    objective: `Deliver the primary output for: ${objective}`,
    criticality,
    reversible: criticality !== "HIGH",
    priority: "HIGH",
    requiredCapabilities: inferCapabilities(objectiveLower),
    verifiable: hasVerifiableOutcome(objectiveLower),
    verificationHint: hasVerifiableOutcome(objectiveLower)
      ? "Output matches specification and passes acceptance tests"
      : undefined,
  });

  // Phase 3: Validation (always present for MEDIUM/HIGH criticality)
  if (criticality !== "LOW") {
    tasks.push({
      name: `Validate: ${truncate(objective, 60)}`,
      description: `Verify the output quality and correctness for: ${objective}`,
      objective: `Confirm the deliverable meets acceptance criteria for: ${objective}`,
      criticality,
      reversible: true,
      priority: "MEDIUM",
      requiredCapabilities: ["verification", "quality_assurance"],
      verifiable: true,
      verificationHint:
        "Validation report confirms all acceptance criteria are met",
    });
  }

  // Phase 4: Additional safety review for HIGH criticality
  if (criticality === "HIGH") {
    tasks.push({
      name: `Safety Review: ${truncate(objective, 60)}`,
      description: `Independent safety and compliance review for: ${objective}`,
      objective: `Produce safety attestation confirming no policy violations for: ${objective}`,
      criticality: "HIGH",
      reversible: true,
      priority: "CRITICAL",
      requiredCapabilities: ["safety_review", "compliance"],
      verifiable: true,
      verificationHint:
        "Safety attestation signed by qualified reviewer with no violations",
    });
  }

  return tasks;
}

/**
 * Attempt to infer a concrete verification specification for a task.
 * Returns null if the task is too vague to verify directly.
 */
function inferVerificationSpec(task: SubTaskDraft): string | null {
  const obj = task.objective.toLowerCase();

  if (obj.includes("document") || obj.includes("report")) {
    return "Document exists, is non-empty, and covers all required sections";
  }
  if (obj.includes("test") || obj.includes("validate")) {
    return "All test cases pass with >= 95% coverage";
  }
  if (obj.includes("code") || obj.includes("implement")) {
    return "Code compiles, passes linter, and all unit tests succeed";
  }
  if (obj.includes("translate")) {
    return "Translation reviewed by qualified human or backtranslation score >= 0.9";
  }
  if (obj.includes("review") || obj.includes("audit")) {
    return "Review checklist completed with all items addressed";
  }
  if (obj.includes("deploy") || obj.includes("deliver")) {
    return "Deployment health check passes and rollback plan verified";
  }

  // Fallback: if the task has required capabilities, use them as verification basis
  if (task.requiredCapabilities.length > 0) {
    return `Output verified against ${task.requiredCapabilities.join(", ")} domain standards`;
  }

  return null;
}

/**
 * Infer verification method from task characteristics.
 */
function inferVerificationMethod(
  task: SubTaskDraft
): "DIRECT_INSPECTION" | "THIRD_PARTY_AUDIT" | "CRYPTOGRAPHIC_ZK_PROOF" | "CONSENSUS_GAME" | "AUTOMATED_TEST" {
  const obj = task.objective.toLowerCase();

  if (obj.includes("test") || obj.includes("compile") || obj.includes("build")) {
    return "AUTOMATED_TEST";
  }
  if (obj.includes("safety") || obj.includes("audit") || obj.includes("compliance")) {
    return "THIRD_PARTY_AUDIT";
  }
  if (obj.includes("privacy") || obj.includes("confidential") || obj.includes("secret")) {
    return "CRYPTOGRAPHIC_ZK_PROOF";
  }
  if (task.criticality === "HIGH") {
    return "THIRD_PARTY_AUDIT";
  }
  return "DIRECT_INSPECTION";
}

/** Infer required capabilities from an objective string. */
function inferCapabilities(objectiveLower: string): string[] {
  const caps: string[] = [];

  if (objectiveLower.includes("code") || objectiveLower.includes("program"))
    caps.push("software_development");
  if (objectiveLower.includes("translate")) caps.push("translation");
  if (objectiveLower.includes("legal")) caps.push("legal_analysis");
  if (objectiveLower.includes("data") || objectiveLower.includes("analy"))
    caps.push("data_analysis");
  if (objectiveLower.includes("deploy") || objectiveLower.includes("infra"))
    caps.push("infrastructure");
  if (objectiveLower.includes("write") || objectiveLower.includes("document"))
    caps.push("technical_writing");
  if (objectiveLower.includes("test")) caps.push("testing");
  if (objectiveLower.includes("design")) caps.push("design");

  return caps.length > 0 ? caps : ["general"];
}

/** Check if an objective likely has a deterministic verifiable outcome. */
function hasVerifiableOutcome(objectiveLower: string): boolean {
  const verifiablePatterns = [
    "test", "code", "compile", "deploy", "build", "calculate",
    "generate", "create file", "produce", "deliver",
  ];
  return verifiablePatterns.some((p) => objectiveLower.includes(p));
}

/** Map criticality to default priority. */
function criticalityToPriority(
  c: "LOW" | "MEDIUM" | "HIGH"
): "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" {
  return c === "HIGH" ? "CRITICAL" : c === "MEDIUM" ? "HIGH" : "MEDIUM";
}

/** Truncate a string with ellipsis. */
function truncate(s: string, maxLen: number): string {
  return s.length > maxLen ? s.slice(0, maxLen - 3) + "..." : s;
}

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

export class DecompositionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DecompositionError";
  }
}
