/**
 * Task Decomposition Engine — API Routes
 *
 * REST endpoints for the three-phase decomposition pipeline:
 *   POST /api/v1/decompose/analyze        → Decompose objective into sub-tasks
 *   POST /api/v1/decompose/:jobId/verify  → Verify sub-task outcomes are checkable
 *   POST /api/v1/decompose/:jobId/finalize → Generate formal TaskSpecification
 */

import { Router, type Request, type Response } from "express";
import { AnalyzeRequestSchema } from "../schemas/task.schema";
import { param } from "../lib/params";
import {
  analyzeObjective,
  verifyOutcomes,
  finalizeDecomposition,
  DecompositionError,
} from "../services/decomposition.service";

export const decomposeRouter = Router();

/**
 * POST /api/v1/decompose/analyze
 */
decomposeRouter.post("/analyze", async (req: Request, res: Response) => {
  const parsed = AnalyzeRequestSchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).json({
      error: "Validation failed",
      issues: parsed.error.issues,
    });
  }

  try {
    const result = await analyzeObjective(parsed.data);
    return res.status(200).json(result);
  } catch (error) {
    return handleServiceError(res, error);
  }
});

/**
 * POST /api/v1/decompose/:jobId/verify-outcomes
 */
decomposeRouter.post(
  "/:jobId/verify-outcomes",
  async (req: Request, res: Response) => {
    try {
      const result = await verifyOutcomes(param(req, "jobId"));
      return res.status(200).json(result);
    } catch (error) {
      return handleServiceError(res, error);
    }
  }
);

/**
 * POST /api/v1/decompose/:jobId/finalize
 */
decomposeRouter.post(
  "/:jobId/finalize",
  async (req: Request, res: Response) => {
    try {
      const spec = await finalizeDecomposition(param(req, "jobId"));
      return res.status(201).json(spec);
    } catch (error) {
      return handleServiceError(res, error);
    }
  }
);

function handleServiceError(res: Response, error: unknown): Response {
  if (error instanceof DecompositionError) {
    return res.status(400).json({
      error: error.message,
      code: "DECOMPOSITION_ERROR",
    });
  }
  console.error("[DecomposeRoutes] Unexpected error:", error);
  return res.status(500).json({
    error: "Internal server error",
    code: "INTERNAL_ERROR",
  });
}
