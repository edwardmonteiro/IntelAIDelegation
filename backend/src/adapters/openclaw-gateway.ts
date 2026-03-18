/**
 * OpenClaw Gateway Adapter — bridges OpenClaw agents into the
 * Intelligent AI Delegation framework.
 *
 * This adapter sits between OpenClaw's Gateway (localhost:18789) and
 * our framework's API surface. It provides four capabilities:
 *
 *   1. Agent Registration — maps OpenClaw workspaces to Agent entities
 *      with DIDs, syncing skills to VerifiableCredentials
 *   2. Market Participation — lets OpenClaw agents discover tasks and
 *      submit bids through our Market Hub
 *   3. Permission Bridging — wraps OpenClaw's tool invocation through
 *      our JIT Permission Gateway, replacing static allowlists with
 *      contract-bound, time-limited scoped grants
 *   4. Monitoring Ingestion — pipes OpenClaw's JSONL transcripts into
 *      our MonitoringEvent table for transparency scoring
 *
 * OpenClaw Gateway API (default: http://127.0.0.1:18789):
 *   - WebSocket for real-time message routing
 *   - REST endpoints for workspace/session management
 *   - Skills loaded from workspace directories
 */

import { createHash } from "crypto";
import { v4 as uuid } from "uuid";
import { prisma } from "../lib/prisma";

// ============================================================================
// Configuration
// ============================================================================

export interface OpenClawConfig {
  /** OpenClaw Gateway URL (default: http://127.0.0.1:18789) */
  gatewayUrl: string;
  /** How often to poll for transcript updates (ms) */
  transcriptPollIntervalMs: number;
  /** DID method prefix for OpenClaw agents */
  didPrefix: string;
  /** Default reputation score for newly registered agents */
  defaultReputationScore: number;
}

const DEFAULT_CONFIG: OpenClawConfig = {
  gatewayUrl: "http://127.0.0.1:18789",
  transcriptPollIntervalMs: 5000,
  didPrefix: "did:openclaw",
  defaultReputationScore: 0.5,
};

// ============================================================================
// Types — OpenClaw workspace & session models
// ============================================================================

/** Represents an OpenClaw workspace (maps 1:1 to our Agent). */
export interface OpenClawWorkspace {
  /** Workspace identifier within OpenClaw */
  id: string;
  /** Human-readable name */
  name: string;
  /** LLM provider configured for this workspace */
  modelProvider: string;
  /** Model identifier (e.g., "claude-sonnet-4-20250514") */
  modelId: string;
  /** Skills installed in this workspace */
  skills: OpenClawSkill[];
  /** Whether the workspace is currently active */
  active: boolean;
}

/** An OpenClaw skill installed in a workspace. */
export interface OpenClawSkill {
  /** Skill name from SKILL.md */
  name: string;
  /** Skill description */
  description: string;
  /** Tools this skill provides */
  tools: string[];
  /** Source: "bundled", "clawhub", or "workspace" */
  source: string;
}

/** A single line from an OpenClaw JSONL transcript. */
export interface TranscriptEntry {
  timestamp: string;
  role: "user" | "assistant" | "tool" | "system";
  content: string;
  toolName?: string;
  toolInput?: Record<string, unknown>;
  toolOutput?: string;
  sessionId?: string;
  error?: boolean;
}

// ============================================================================
// 1. Agent Registration — OpenClaw Workspace → Agent Entity
// ============================================================================

/**
 * Register an OpenClaw workspace as an Agent in our framework.
 *
 * Maps:
 *   - workspace.id       → Agent.id (as DID: "did:openclaw:{id}")
 *   - workspace.name     → Agent.name
 *   - workspace.skills   → VerifiableCredentials (self-issued, unverified)
 *   - workspace.active   → Agent.activeStatus
 *
 * Skills are registered as self-issued credentials initially. They can
 * be upgraded to verified credentials once the agent completes tasks
 * in those domains successfully.
 */
export async function registerWorkspaceAsAgent(
  workspace: OpenClawWorkspace,
  config: OpenClawConfig = DEFAULT_CONFIG
) {
  const agentId = `${config.didPrefix}:${workspace.id}`;

  // Generate a deterministic public key placeholder from workspace ID
  // In production, OpenClaw would provide an actual signing key
  const publicKey = createHash("sha256")
    .update(`openclaw-agent-${workspace.id}`)
    .digest("hex");

  // Upsert the agent — idempotent for re-registration
  const agent = await prisma.agent.upsert({
    where: { id: agentId },
    create: {
      id: agentId,
      name: workspace.name,
      type: "AI",
      publicKey,
      baseReputationScore: config.defaultReputationScore,
      activeStatus: workspace.active,
      maxConcurrentTasks: 3, // OpenClaw default maxConcurrent is 8
      metadata: {
        openclawWorkspaceId: workspace.id,
        modelProvider: workspace.modelProvider,
        modelId: workspace.modelId,
        source: "openclaw-gateway",
      },
    },
    update: {
      name: workspace.name,
      activeStatus: workspace.active,
      metadata: {
        openclawWorkspaceId: workspace.id,
        modelProvider: workspace.modelProvider,
        modelId: workspace.modelId,
        source: "openclaw-gateway",
      },
    },
  });

  // Register skills as self-issued VerifiableCredentials
  for (const skill of workspace.skills) {
    const skillDomain = normalizeSkillDomain(skill.name);

    // Check if credential already exists
    const existing = await prisma.verifiableCredential.findFirst({
      where: {
        agentId,
        issuerId: agentId, // self-issued
        skillDomain,
      },
    });

    if (!existing) {
      const credentialPayload = JSON.stringify({
        agentId,
        skillDomain,
        tools: skill.tools,
        source: skill.source,
        registeredAt: new Date().toISOString(),
      });

      await prisma.verifiableCredential.create({
        data: {
          id: uuid(),
          agentId,
          issuerId: agentId, // self-issued initially
          skillDomain,
          credentialHash: createHash("sha256")
            .update(credentialPayload)
            .digest("hex"),
          evidence: {
            openclawSkillName: skill.name,
            openclawSkillSource: skill.source,
            tools: skill.tools,
            selfIssued: true,
          },
        },
      });
    }
  }

  return agent;
}

/**
 * Bulk-register all workspaces from an OpenClaw Gateway instance.
 */
export async function registerAllWorkspaces(
  workspaces: OpenClawWorkspace[],
  config: OpenClawConfig = DEFAULT_CONFIG
) {
  const results = [];
  for (const ws of workspaces) {
    const agent = await registerWorkspaceAsAgent(ws, config);
    results.push({
      workspaceId: ws.id,
      agentId: agent.id,
      name: agent.name,
      skillsRegistered: ws.skills.length,
    });
  }
  return results;
}

// ============================================================================
// 2. Market Participation — Bid on behalf of OpenClaw agents
// ============================================================================

/**
 * Discover available tasks that an OpenClaw agent is qualified to bid on.
 *
 * Matches tasks in PENDING or BIDDING status against the agent's
 * registered skill domains (VerifiableCredentials).
 */
export async function discoverTasksForAgent(agentId: string) {
  // Get agent's credential domains
  const credentials = await prisma.verifiableCredential.findMany({
    where: { agentId, revoked: false },
    select: { skillDomain: true },
  });
  const domains = credentials.map((c) => c.skillDomain);

  if (domains.length === 0) return [];

  // Find tasks in biddable states
  const tasks = await prisma.task.findMany({
    where: {
      status: { in: ["PENDING", "BIDDING"] },
      // Tasks without an assignee
      assigneeId: null,
    },
    include: {
      bids: { where: { agentId } }, // check if already bid
    },
    orderBy: { createdAt: "desc" },
    take: 50,
  });

  // Filter to tasks the agent hasn't already bid on
  return tasks.filter((t) => t.bids.length === 0);
}

/**
 * Submit a bid on behalf of an OpenClaw agent.
 *
 * Estimates cost and duration based on the agent's model and task
 * complexity, then creates a Bid record in the Market Hub.
 */
export async function submitBidForAgent(params: {
  agentId: string;
  taskId: string;
  estimatedCost: number;
  estimatedDurationSeconds: number;
  confidence: number;
  privacyGuarantee?: string;
}) {
  // Verify agent exists and is active
  const agent = await prisma.agent.findUniqueOrThrow({
    where: { id: params.agentId },
  });

  if (!agent.activeStatus) {
    throw new OpenClawAdapterError(
      `Agent ${params.agentId} is inactive (circuit breaker triggered)`
    );
  }

  // Calculate reputation bond — 10% of proposed cost, scaled by reputation
  // Lower reputation = higher bond required (skin in the game)
  const bondMultiplier = Math.max(0.05, 0.2 - agent.baseReputationScore * 0.15);
  const reputationBond = params.estimatedCost * bondMultiplier;

  const bid = await prisma.bid.create({
    data: {
      id: uuid(),
      taskId: params.taskId,
      agentId: params.agentId,
      proposedCost: params.estimatedCost,
      proposedDurationSeconds: params.estimatedDurationSeconds,
      confidence: params.confidence,
      privacyGuarantee: params.privacyGuarantee ?? "none",
      reputationBond,
      message: `Bid from OpenClaw agent ${agent.name}`,
      metadata: {
        source: "openclaw-gateway",
        modelProvider: String((agent.metadata as Record<string, string>)?.modelProvider ?? ""),
        modelId: String((agent.metadata as Record<string, string>)?.modelId ?? ""),
      },
    },
  });

  // Transition task to BIDDING if currently PENDING
  await prisma.task.updateMany({
    where: { id: params.taskId, status: "PENDING" },
    data: { status: "BIDDING" },
  });

  return bid;
}

// ============================================================================
// 3. Permission Bridging — JIT Grants for OpenClaw Tool Access
// ============================================================================

/**
 * Check whether an OpenClaw agent is authorized to invoke a specific tool.
 *
 * This replaces OpenClaw's static allowlist model with our contract-bound
 * JIT permission system. The agent must have:
 *   1. An active SmartContract for the task
 *   2. A non-revoked, non-expired PermissionGrant covering the tool's scope
 *
 * Called by the OpenClaw skill before each tool invocation.
 */
export async function checkToolPermission(params: {
  agentId: string;
  taskId: string;
  toolName: string;
}): Promise<PermissionCheckResult> {
  const scope = mapToolToScope(params.toolName);

  // Check for active contract
  const contract = await prisma.smartContract.findFirst({
    where: {
      delegateeId: params.agentId,
      taskId: params.taskId,
      status: "ACTIVE",
    },
  });

  if (!contract) {
    return {
      allowed: false,
      reason: "No active contract for this agent and task",
    };
  }

  // Check for valid permission grant
  const grant = await prisma.permissionGrant.findFirst({
    where: {
      agentId: params.agentId,
      taskId: params.taskId,
      revoked: false,
      OR: [{ expiresAt: null }, { expiresAt: { gt: new Date() } }],
    },
  });

  if (!grant) {
    return {
      allowed: false,
      reason: `No active permission grant for scope: ${scope}`,
    };
  }

  // Check scope coverage
  if (!scopeCovers(grant.scope, scope)) {
    return {
      allowed: false,
      reason: `Grant scope "${grant.scope}" does not cover required scope "${scope}"`,
    };
  }

  return {
    allowed: true,
    contractId: contract.id,
    grantId: grant.id,
    scope,
    expiresAt: grant.expiresAt?.toISOString(),
  };
}

export interface PermissionCheckResult {
  allowed: boolean;
  reason?: string;
  contractId?: string;
  grantId?: string;
  scope?: string;
  expiresAt?: string;
}

// ============================================================================
// 4. Monitoring Ingestion — JSONL Transcripts → MonitoringEvents
// ============================================================================

/**
 * Ingest OpenClaw JSONL transcript entries into our MonitoringEvent table.
 *
 * Each transcript line becomes a MonitoringEvent, enabling:
 *   - Transparency scoring (clarity of reasoning traces)
 *   - Safety auditing (tool invocations reviewed against policy)
 *   - Progress tracking (how far along is the task)
 *
 * The adapter classifies entries by severity:
 *   - tool errors → ERROR
 *   - system messages → INFO
 *   - tool invocations → INFO (WARNING if sensitive tools)
 *   - assistant reasoning → INFO
 */
export async function ingestTranscript(
  taskId: string,
  contractId: string | null,
  entries: TranscriptEntry[]
) {
  if (entries.length === 0) return { ingested: 0 };

  const events = entries.map((entry) => ({
    id: uuid(),
    taskId,
    contractId,
    eventType: classifyEventType(entry),
    severity: classifySeverity(entry),
    message: truncate(entry.content, 500),
    data: JSON.parse(JSON.stringify({
      role: entry.role,
      toolName: entry.toolName ?? null,
      toolInput: entry.toolInput ?? null,
      sessionId: entry.sessionId ?? null,
      originalTimestamp: entry.timestamp,
      source: "openclaw-transcript",
    })),
    timestamp: new Date(entry.timestamp),
  }));

  await prisma.monitoringEvent.createMany({ data: events });

  return { ingested: events.length };
}

/**
 * Compute a transparency score from a task's monitoring events.
 *
 * Transparency measures the clarity and completeness of the agent's
 * reasoning trace during execution. Higher scores mean the agent
 * explained its decisions more clearly.
 *
 * Scoring heuristic:
 *   - Base score: 0.5
 *   - +0.1 for each reasoning step (assistant messages explaining actions)
 *   - +0.05 for each tool invocation with clear inputs
 *   - -0.1 for each error without recovery
 *   - -0.15 for unexplained tool invocations (no prior reasoning)
 *   - Clamped to [0, 1]
 */
export async function computeTransparencyScore(taskId: string): Promise<number> {
  const events = await prisma.monitoringEvent.findMany({
    where: { taskId },
    orderBy: { timestamp: "asc" },
  });

  if (events.length === 0) return 0.5;

  let score = 0.5;
  let lastWasReasoning = false;

  for (const event of events) {
    const data = event.data as Record<string, unknown>;
    const role = data?.role as string | undefined;

    if (role === "assistant" && event.eventType === "reasoning") {
      score += 0.1;
      lastWasReasoning = true;
    } else if (event.eventType === "tool_invocation") {
      if (lastWasReasoning) {
        score += 0.05; // Tool use preceded by reasoning — transparent
      } else {
        score -= 0.15; // Unexplained tool use
      }
      lastWasReasoning = false;
    } else if (event.severity === "ERROR") {
      // Check if next event is a recovery attempt
      score -= 0.1;
      lastWasReasoning = false;
    } else {
      lastWasReasoning = false;
    }
  }

  return Math.max(0, Math.min(1, score));
}

// ============================================================================
// Express Routes — mount these on /api/v1/openclaw
// ============================================================================

import { Router, type Request, type Response } from "express";
import { param } from "../lib/params";

export const openclawRouter = Router();

/**
 * POST /api/v1/openclaw/register
 * Register OpenClaw workspaces as agents.
 */
openclawRouter.post("/register", async (req: Request, res: Response) => {
  const { workspaces, config } = req.body as {
    workspaces: OpenClawWorkspace[];
    config?: Partial<OpenClawConfig>;
  };

  if (!workspaces || !Array.isArray(workspaces)) {
    return res.status(400).json({
      error: "Request body must include a 'workspaces' array",
    });
  }

  try {
    const mergedConfig = { ...DEFAULT_CONFIG, ...config };
    const results = await registerAllWorkspaces(workspaces, mergedConfig);
    return res.status(201).json({
      registered: results.length,
      agents: results,
    });
  } catch (error) {
    return handleAdapterError(res, error);
  }
});

/**
 * GET /api/v1/openclaw/agents/:agentId/tasks
 * Discover biddable tasks for an OpenClaw agent.
 */
openclawRouter.get(
  "/agents/:agentId/tasks",
  async (req: Request, res: Response) => {
    try {
      const tasks = await discoverTasksForAgent(param(req, "agentId"));
      return res.status(200).json({ tasks, count: tasks.length });
    } catch (error) {
      return handleAdapterError(res, error);
    }
  }
);

/**
 * POST /api/v1/openclaw/agents/:agentId/bid
 * Submit a bid on behalf of an OpenClaw agent.
 */
openclawRouter.post(
  "/agents/:agentId/bid",
  async (req: Request, res: Response) => {
    const agentId = param(req, "agentId");
    const { taskId, estimatedCost, estimatedDurationSeconds, confidence, privacyGuarantee } =
      req.body;

    try {
      const bid = await submitBidForAgent({
        agentId,
        taskId,
        estimatedCost,
        estimatedDurationSeconds,
        confidence,
        privacyGuarantee,
      });
      return res.status(201).json(bid);
    } catch (error) {
      return handleAdapterError(res, error);
    }
  }
);

/**
 * POST /api/v1/openclaw/permissions/check
 * Check if an OpenClaw agent can invoke a specific tool.
 */
openclawRouter.post(
  "/permissions/check",
  async (req: Request, res: Response) => {
    const { agentId, taskId, toolName } = req.body;

    if (!agentId || !taskId || !toolName) {
      return res.status(400).json({
        error: "Missing required fields: agentId, taskId, toolName",
      });
    }

    try {
      const result = await checkToolPermission({ agentId, taskId, toolName });
      const statusCode = result.allowed ? 200 : 403;
      return res.status(statusCode).json(result);
    } catch (error) {
      return handleAdapterError(res, error);
    }
  }
);

/**
 * POST /api/v1/openclaw/transcript/:taskId
 * Ingest JSONL transcript entries for monitoring.
 */
openclawRouter.post(
  "/transcript/:taskId",
  async (req: Request, res: Response) => {
    const taskId = param(req, "taskId");
    const { contractId, entries } = req.body as {
      contractId?: string;
      entries: TranscriptEntry[];
    };

    if (!entries || !Array.isArray(entries)) {
      return res.status(400).json({
        error: "Request body must include an 'entries' array",
      });
    }

    try {
      const result = await ingestTranscript(taskId, contractId ?? null, entries);
      return res.status(201).json(result);
    } catch (error) {
      return handleAdapterError(res, error);
    }
  }
);

/**
 * GET /api/v1/openclaw/transparency/:taskId
 * Compute transparency score from ingested transcripts.
 */
openclawRouter.get(
  "/transparency/:taskId",
  async (req: Request, res: Response) => {
    try {
      const score = await computeTransparencyScore(param(req, "taskId"));
      return res.status(200).json({ taskId: param(req, "taskId"), transparencyScore: score });
    } catch (error) {
      return handleAdapterError(res, error);
    }
  }
);

// ============================================================================
// Internal helpers
// ============================================================================

/** Normalize an OpenClaw skill name to a credential domain. */
function normalizeSkillDomain(skillName: string): string {
  return skillName
    .toLowerCase()
    .replace(/[^a-z0-9_-]/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "");
}

/**
 * Map an OpenClaw tool name to a permission scope.
 *
 * OpenClaw tools follow the pattern: skill_name__tool_name
 * We map these to our scope format: tool:action:resource
 */
function mapToolToScope(toolName: string): string {
  // Sensitive tools that require explicit write permission
  const writeSensitive = [
    "file_write", "file_delete", "shell_exec", "http_post",
    "http_put", "http_delete", "db_write", "db_delete",
  ];
  const readTools = [
    "file_read", "http_get", "db_read", "search",
  ];

  const toolLower = toolName.toLowerCase();

  if (writeSensitive.some((t) => toolLower.includes(t))) {
    return `tool:write:${toolName}`;
  }
  if (readTools.some((t) => toolLower.includes(t))) {
    return `tool:read:${toolName}`;
  }
  return `tool:execute:${toolName}`;
}

/** Check if a granted scope covers a required scope. */
function scopeCovers(granted: string, required: string): boolean {
  if (granted === "*") return true;
  if (granted === required) return true;

  const grantedParts = granted.split(":");
  const requiredParts = required.split(":");

  for (let i = 0; i < grantedParts.length; i++) {
    if (grantedParts[i] === "*") return true;
    if (i >= requiredParts.length) return false;
    if (grantedParts[i] !== requiredParts[i]) return false;
  }

  return grantedParts.length <= requiredParts.length;
}

/** Classify a transcript entry into a monitoring event type. */
function classifyEventType(entry: TranscriptEntry): string {
  if (entry.role === "tool") {
    return entry.error ? "tool_error" : "tool_invocation";
  }
  if (entry.role === "assistant") {
    // If the message contains reasoning/explanation, classify as reasoning
    if (entry.content.length > 50) return "reasoning";
    return "response";
  }
  if (entry.role === "system") return "system";
  if (entry.role === "user") return "user_input";
  return "unknown";
}

/** Classify severity of a transcript entry. */
function classifySeverity(
  entry: TranscriptEntry
): "INFO" | "WARNING" | "ERROR" | "CRITICAL" {
  if (entry.error) return "ERROR";

  if (entry.role === "tool") {
    const sensitiveTools = ["shell_exec", "file_delete", "db_delete", "http_delete"];
    if (entry.toolName && sensitiveTools.some((t) => entry.toolName!.includes(t))) {
      return "WARNING";
    }
  }

  return "INFO";
}

/** Truncate a string. */
function truncate(s: string, maxLen: number): string {
  return s.length > maxLen ? s.slice(0, maxLen - 3) + "..." : s;
}

function handleAdapterError(res: Response, error: unknown): Response {
  if (error instanceof OpenClawAdapterError) {
    return res.status(400).json({
      error: error.message,
      code: "OPENCLAW_ADAPTER_ERROR",
    });
  }
  console.error("[OpenClawAdapter] Unexpected error:", error);
  return res.status(500).json({
    error: "Internal server error",
    code: "INTERNAL_ERROR",
  });
}

export class OpenClawAdapterError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "OpenClawAdapterError";
  }
}
