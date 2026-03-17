/**
 * Contract Management — API Routes
 *
 * REST endpoints for SmartContract lifecycle management:
 *   GET    /api/v1/contracts/:contractId           → Get contract details
 *   POST   /api/v1/contracts/:contractId/accept    → Accept a proposed contract
 *   POST   /api/v1/contracts/:contractId/activate  → Activate (begin execution)
 *   POST   /api/v1/contracts/:contractId/complete  → Mark complete (verified)
 *   POST   /api/v1/contracts/:contractId/breach    → Report breach
 *   POST   /api/v1/contracts/:contractId/terminate → Early termination
 *   GET    /api/v1/contracts/:contractId/verify    → Verify terms integrity
 */

import { Router, type Request, type Response } from "express";
import { z } from "zod";
import { prisma } from "../lib/prisma";
import { param } from "../lib/params";
import {
  acceptContract,
  activateContract,
  completeContract,
  reportBreach,
  terminateContract,
  verifyContractIntegrity,
  ContractLifecycleError,
} from "../services/contract.service";

export const contractRouter = Router();

/**
 * GET /api/v1/contracts/:contractId
 */
contractRouter.get("/:contractId", async (req: Request, res: Response) => {
  try {
    const contract = await prisma.smartContract.findUniqueOrThrow({
      where: { id: param(req, "contractId") },
      include: {
        task: true,
        bid: true,
        delegator: true,
        delegatee: true,
        penalties: true,
        permissionGrants: { where: { revoked: false } },
      },
    });
    return res.status(200).json(contract);
  } catch {
    return res.status(404).json({
      error: "Contract not found",
      code: "NOT_FOUND",
    });
  }
});

/**
 * POST /api/v1/contracts/:contractId/accept
 */
contractRouter.post(
  "/:contractId/accept",
  async (req: Request, res: Response) => {
    try {
      const contract = await acceptContract(param(req, "contractId"));
      return res.status(200).json(contract);
    } catch (error) {
      return handleContractError(res, error);
    }
  }
);

/**
 * POST /api/v1/contracts/:contractId/activate
 */
contractRouter.post(
  "/:contractId/activate",
  async (req: Request, res: Response) => {
    try {
      const contract = await activateContract(param(req, "contractId"));
      return res.status(200).json(contract);
    } catch (error) {
      return handleContractError(res, error);
    }
  }
);

/**
 * POST /api/v1/contracts/:contractId/complete
 */
const CompleteBodySchema = z.object({
  qualityScore: z.number().min(0).max(1).default(1.0),
  transparencyScore: z.number().min(0).max(1).default(1.0),
  safetyScore: z.number().min(0).max(1).default(1.0),
  resourceConsumed: z.record(z.unknown()).default({}),
});

contractRouter.post(
  "/:contractId/complete",
  async (req: Request, res: Response) => {
    const parsed = CompleteBodySchema.safeParse(req.body);
    if (!parsed.success) {
      return res.status(400).json({
        error: "Validation failed",
        issues: parsed.error.issues,
      });
    }

    try {
      const contract = await completeContract(
        param(req, "contractId"),
        parsed.data.qualityScore,
        parsed.data.transparencyScore,
        parsed.data.safetyScore,
        parsed.data.resourceConsumed
      );
      return res.status(200).json(contract);
    } catch (error) {
      return handleContractError(res, error);
    }
  }
);

/**
 * POST /api/v1/contracts/:contractId/breach
 */
const BreachBodySchema = z.object({
  reason: z.string().min(1),
  severity: z.enum(["LOW", "MEDIUM", "HIGH", "CRITICAL"]).default("MEDIUM"),
});

contractRouter.post(
  "/:contractId/breach",
  async (req: Request, res: Response) => {
    const parsed = BreachBodySchema.safeParse(req.body);
    if (!parsed.success) {
      return res.status(400).json({
        error: "Validation failed",
        issues: parsed.error.issues,
      });
    }

    try {
      const contract = await reportBreach(
        param(req, "contractId"),
        parsed.data.reason,
        parsed.data.severity
      );
      return res.status(200).json(contract);
    } catch (error) {
      return handleContractError(res, error);
    }
  }
);

/**
 * POST /api/v1/contracts/:contractId/terminate
 */
const TerminateBodySchema = z.object({
  reason: z.string().min(1),
});

contractRouter.post(
  "/:contractId/terminate",
  async (req: Request, res: Response) => {
    const parsed = TerminateBodySchema.safeParse(req.body);
    if (!parsed.success) {
      return res.status(400).json({
        error: "Validation failed",
        issues: parsed.error.issues,
      });
    }

    try {
      const contract = await terminateContract(
        param(req, "contractId"),
        parsed.data.reason
      );
      return res.status(200).json(contract);
    } catch (error) {
      return handleContractError(res, error);
    }
  }
);

/**
 * GET /api/v1/contracts/:contractId/verify
 */
contractRouter.get(
  "/:contractId/verify",
  async (req: Request, res: Response) => {
    try {
      const result = await verifyContractIntegrity(param(req, "contractId"));
      const statusCode = result.valid ? 200 : 409;
      return res.status(statusCode).json({
        ...result,
        message: result.valid
          ? "Contract terms integrity verified"
          : "WARNING: Contract terms have been tampered with",
      });
    } catch (error) {
      return handleContractError(res, error);
    }
  }
);

// ---------------------------------------------------------------------------
// Error handling
// ---------------------------------------------------------------------------

function handleContractError(res: Response, error: unknown): Response {
  if (error instanceof ContractLifecycleError) {
    return res.status(409).json({
      error: error.message,
      code: "CONTRACT_LIFECYCLE_ERROR",
    });
  }
  if (error instanceof Error && error.message.includes("not found")) {
    return res.status(404).json({
      error: "Contract not found",
      code: "NOT_FOUND",
    });
  }
  console.error("[ContractRoutes] Unexpected error:", error);
  return res.status(500).json({
    error: "Internal server error",
    code: "INTERNAL_ERROR",
  });
}
