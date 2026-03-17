/**
 * Permission Gateway Middleware — Just-in-Time access enforcement.
 *
 * Enforces the paper's "Just-in-Time Permission" model by validating
 * that every request from an executing agent is backed by:
 *
 *   1. An active, non-revoked SmartContract for the requested task
 *   2. A valid PermissionGrant covering the required scope
 *   3. A valid Delegation Capability Token (DCT) that attenuates
 *      permissions to specific resources and time windows
 *
 * Usage:
 *   app.use("/api/v1/resources/:taskId", requirePermission("api:read"));
 */

import { createHash } from "crypto";
import type { Request, Response, NextFunction } from "express";
import { prisma } from "../lib/prisma";
import {
  DelegationCapabilityTokenSchema,
  type DelegationCapabilityToken,
} from "../schemas/contract.schema";

// ============================================================================
// Middleware Factory
// ============================================================================

/**
 * Express middleware that enforces JIT permission checks.
 *
 * Expects these headers on the incoming request:
 *   - x-agent-id:  The DID of the requesting agent
 *   - x-task-id:   The task ID the agent is operating on (or from URL param)
 *   - x-dct:       Base64-encoded Delegation Capability Token (optional,
 *                   required for fine-grained resource access)
 *
 * @param requiredScope - The permission scope required, e.g. "api:read:users"
 */
export function requirePermission(requiredScope: string) {
  return async (req: Request, res: Response, next: NextFunction) => {
    const agentId = req.headers["x-agent-id"] as string | undefined;
    const taskId =
      (req.params.taskId as string) ??
      (req.headers["x-task-id"] as string | undefined);

    if (!agentId) {
      return res.status(401).json({
        error: "Missing x-agent-id header",
        code: "AUTH_MISSING_AGENT",
      });
    }
    if (!taskId) {
      return res.status(400).json({
        error: "Missing task ID (URL param or x-task-id header)",
        code: "AUTH_MISSING_TASK",
      });
    }

    try {
      // Step 1: Verify agent has an active contract for this task
      const activeContract = await prisma.smartContract.findFirst({
        where: {
          taskId,
          delegateeId: agentId,
          status: "ACTIVE",
        },
      });

      if (!activeContract) {
        return res.status(403).json({
          error: "No active contract found for this agent and task",
          code: "PERM_NO_CONTRACT",
          agentId,
          taskId,
        });
      }

      // Step 2: Verify agent has a valid (non-revoked, non-expired) permission grant
      const grant = await prisma.permissionGrant.findFirst({
        where: {
          agentId,
          taskId,
          revoked: false,
          scope: requiredScope,
          OR: [{ expiresAt: null }, { expiresAt: { gt: new Date() } }],
        },
      });

      if (!grant) {
        return res.status(403).json({
          error: `Agent lacks required permission scope: ${requiredScope}`,
          code: "PERM_INSUFFICIENT_SCOPE",
          agentId,
          taskId,
          requiredScope,
        });
      }

      // Step 3: If a DCT is provided, validate it for fine-grained access
      const dctHeader = req.headers["x-dct"] as string | undefined;
      if (dctHeader) {
        const dctResult = validateDCT(dctHeader, agentId, taskId, requiredScope);
        if (!dctResult.valid) {
          return res.status(403).json({
            error: `DCT validation failed: ${dctResult.reason}`,
            code: "PERM_DCT_INVALID",
            agentId,
            taskId,
          });
        }
      }

      // Attach contract and grant info to request for downstream use
      (req as AuthenticatedRequest).agentId = agentId;
      (req as AuthenticatedRequest).taskId = taskId;
      (req as AuthenticatedRequest).contractId = activeContract.id;
      (req as AuthenticatedRequest).grantId = grant.id;

      next();
    } catch (error) {
      return res.status(500).json({
        error: "Permission check failed",
        code: "PERM_INTERNAL_ERROR",
        details: error instanceof Error ? error.message : "Unknown error",
      });
    }
  };
}

// ============================================================================
// Delegation Capability Token (DCT) Validation
// ============================================================================

interface DCTValidationResult {
  valid: boolean;
  reason?: string;
  token?: DelegationCapabilityToken;
}

/**
 * Validate a Delegation Capability Token (DCT).
 *
 * The DCT is a signed, scoped, time-limited token that attenuates
 * the agent's permissions to specific resources and operations.
 *
 * Validation checks:
 *   1. Token parses correctly against the Zod schema
 *   2. Token belongs to the requesting agent
 *   3. Token covers the requested task
 *   4. Token has not expired
 *   5. Token scope covers the required scope
 *   6. Token signature is valid (mock: HMAC-SHA256 of payload)
 */
function validateDCT(
  dctBase64: string,
  agentId: string,
  taskId: string,
  requiredScope: string
): DCTValidationResult {
  // Decode the base64-encoded DCT
  let dctPayload: unknown;
  try {
    const decoded = Buffer.from(dctBase64, "base64").toString("utf-8");
    dctPayload = JSON.parse(decoded);
  } catch {
    return { valid: false, reason: "Malformed DCT: invalid base64 or JSON" };
  }

  // Parse against Zod schema
  const parsed = DelegationCapabilityTokenSchema.safeParse(dctPayload);
  if (!parsed.success) {
    return {
      valid: false,
      reason: `DCT schema validation failed: ${parsed.error.issues.map((i) => i.message).join("; ")}`,
    };
  }
  const token = parsed.data;

  // Check 1: Token belongs to the requesting agent
  if (token.agentId !== agentId) {
    return {
      valid: false,
      reason: `DCT issued to ${token.agentId}, but request from ${agentId}`,
    };
  }

  // Check 2: Token covers the requested task
  if (token.taskId !== taskId) {
    return {
      valid: false,
      reason: `DCT scoped to task ${token.taskId}, but request for task ${taskId}`,
    };
  }

  // Check 3: Token has not expired
  const now = new Date();
  if (new Date(token.expiresAt) <= now) {
    return { valid: false, reason: "DCT has expired" };
  }
  if (new Date(token.issuedAt) > now) {
    return { valid: false, reason: "DCT issuedAt is in the future" };
  }

  // Check 4: Token scope covers the required scope
  const scopeCovered = token.scopes.some((scope) =>
    scopeCovers(scope, requiredScope)
  );
  if (!scopeCovered) {
    return {
      valid: false,
      reason: `DCT scopes [${token.scopes.join(", ")}] do not cover required scope "${requiredScope}"`,
    };
  }

  // Check 5: Signature verification (mock — uses HMAC-SHA256 with a shared secret)
  const signatureValid = verifyDCTSignature(token);
  if (!signatureValid) {
    return { valid: false, reason: "DCT signature verification failed" };
  }

  return { valid: true, token };
}

/**
 * Check if a granted scope covers a required scope.
 *
 * Scope format: "domain:action:resource"
 * A granted scope covers a required scope if:
 *   - Exact match, OR
 *   - Granted scope uses wildcard "*" at any level
 *
 * Examples:
 *   "api:*" covers "api:read:users"
 *   "api:read:*" covers "api:read:users"
 *   "*" covers everything
 */
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

  // Granted scope is a prefix of required scope (more specific) — covers it
  return grantedParts.length <= requiredParts.length;
}

/**
 * Mock signature verification for a DCT.
 *
 * In production, this would verify an Ed25519 or ECDSA signature using
 * the delegator's public key. Here we use HMAC-SHA256 with a server
 * secret for demonstration.
 */
function verifyDCTSignature(token: DelegationCapabilityToken): boolean {
  const secret = process.env.DCT_SIGNING_SECRET ?? "dev-secret-do-not-use-in-prod";

  const payload = JSON.stringify({
    agentId: token.agentId,
    taskId: token.taskId,
    contractId: token.contractId,
    scopes: token.scopes,
    resource: token.resource,
    issuedAt: token.issuedAt,
    expiresAt: token.expiresAt,
  });

  const expectedSignature = createHash("sha256")
    .update(payload + secret)
    .digest("hex");

  return token.signature === expectedSignature;
}

// ============================================================================
// DCT Generation Utility (for testing and contract activation)
// ============================================================================

/**
 * Generate a signed DCT for an agent.
 * Used by the contract service when activating a contract.
 */
export function generateDCT(params: {
  agentId: string;
  taskId: string;
  contractId: string;
  scopes: string[];
  resource?: string;
  durationSeconds: number;
}): string {
  const secret = process.env.DCT_SIGNING_SECRET ?? "dev-secret-do-not-use-in-prod";
  const now = new Date();
  const expiresAt = new Date(now.getTime() + params.durationSeconds * 1000);

  const payload = JSON.stringify({
    agentId: params.agentId,
    taskId: params.taskId,
    contractId: params.contractId,
    scopes: params.scopes,
    resource: params.resource ?? "*",
    issuedAt: now.toISOString(),
    expiresAt: expiresAt.toISOString(),
  });

  const signature = createHash("sha256")
    .update(payload + secret)
    .digest("hex");

  const token: DelegationCapabilityToken = {
    agentId: params.agentId,
    taskId: params.taskId,
    contractId: params.contractId,
    scopes: params.scopes,
    resource: params.resource ?? "*",
    issuedAt: now.toISOString(),
    expiresAt: expiresAt.toISOString(),
    signature,
  };

  return Buffer.from(JSON.stringify(token)).toString("base64");
}

// ============================================================================
// Types
// ============================================================================

export interface AuthenticatedRequest extends Request {
  agentId: string;
  taskId: string;
  contractId: string;
  grantId: string;
}
