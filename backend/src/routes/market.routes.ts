/**
 * Market Hub — API Routes
 *
 * REST endpoints for the decentralized task marketplace:
 *   POST   /api/v1/market/:taskId/bids      → Submit a bid
 *   GET    /api/v1/market/:taskId/bids       → List bids for a task
 *   POST   /api/v1/market/:taskId/evaluate   → Run the 3-phase evaluation pipeline
 *   POST   /api/v1/market/:taskId/select     → Accept a bid and generate contract
 */

import { Router, type Request, type Response } from "express";
import { prisma } from "../lib/prisma";
import { param } from "../lib/params";
import { SubmitBidSchema, SelectBidSchema } from "../schemas/bid.schema";
import {
  evaluateBids,
  acceptBidAndCreateContract,
  MarketHubError,
} from "../services/market-hub.service";

export const marketRouter = Router();

/**
 * POST /api/v1/market/:taskId/bids
 */
marketRouter.post("/:taskId/bids", async (req: Request, res: Response) => {
  const taskId = param(req, "taskId");

  const parsed = SubmitBidSchema.safeParse({ ...req.body, taskId });
  if (!parsed.success) {
    return res.status(400).json({
      error: "Validation failed",
      issues: parsed.error.issues,
    });
  }

  try {
    const task = await prisma.task.findUniqueOrThrow({
      where: { id: taskId },
    });

    if (task.status !== "BIDDING" && task.status !== "PENDING") {
      return res.status(409).json({
        error: `Task is in ${task.status} state and is not accepting bids`,
        code: "TASK_NOT_ACCEPTING_BIDS",
      });
    }

    const agent = await prisma.agent.findUniqueOrThrow({
      where: { id: parsed.data.agentId },
    });

    if (!agent.activeStatus) {
      return res.status(403).json({
        error: "Agent is deactivated (circuit breaker triggered)",
        code: "AGENT_INACTIVE",
      });
    }

    const bid = await prisma.bid.create({
      data: {
        taskId,
        agentId: parsed.data.agentId,
        proposedCost: parsed.data.proposedCost,
        proposedDurationSeconds: parsed.data.proposedDurationSeconds,
        confidence: parsed.data.confidence,
        privacyGuarantee: parsed.data.privacyGuarantee,
        reputationBond: parsed.data.reputationBond,
        message: parsed.data.message,
      },
      include: { agent: true },
    });

    if (task.status === "PENDING") {
      await prisma.task.update({
        where: { id: taskId },
        data: { status: "BIDDING" },
      });
    }

    return res.status(201).json(bid);
  } catch (error) {
    return handleMarketError(res, error);
  }
});

/**
 * GET /api/v1/market/:taskId/bids
 */
marketRouter.get("/:taskId/bids", async (req: Request, res: Response) => {
  const taskId = param(req, "taskId");

  try {
    const bids = await prisma.bid.findMany({
      where: { taskId },
      include: { agent: true },
      orderBy: { submittedAt: "asc" },
    });

    return res.status(200).json({ taskId, bids, count: bids.length });
  } catch (error) {
    return handleMarketError(res, error);
  }
});

/**
 * POST /api/v1/market/:taskId/evaluate
 */
marketRouter.post("/:taskId/evaluate", async (req: Request, res: Response) => {
  const taskId = param(req, "taskId");

  try {
    const result = await evaluateBids(taskId);
    return res.status(200).json(result);
  } catch (error) {
    return handleMarketError(res, error);
  }
});

/**
 * POST /api/v1/market/:taskId/select
 */
marketRouter.post("/:taskId/select", async (req: Request, res: Response) => {
  const taskId = param(req, "taskId");

  const parsed = SelectBidSchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).json({
      error: "Validation failed",
      issues: parsed.error.issues,
    });
  }

  try {
    const contract = await acceptBidAndCreateContract(taskId, parsed.data);
    return res.status(201).json(contract);
  } catch (error) {
    return handleMarketError(res, error);
  }
});

function handleMarketError(res: Response, error: unknown): Response {
  if (error instanceof MarketHubError) {
    return res.status(400).json({
      error: error.message,
      code: "MARKET_HUB_ERROR",
    });
  }
  if (
    error instanceof Error &&
    error.message.includes("Record to update not found")
  ) {
    return res.status(404).json({
      error: "Resource not found",
      code: "NOT_FOUND",
    });
  }
  console.error("[MarketRoutes] Unexpected error:", error);
  return res.status(500).json({
    error: "Internal server error",
    code: "INTERNAL_ERROR",
  });
}
