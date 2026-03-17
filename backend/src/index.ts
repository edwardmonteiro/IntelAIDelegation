/**
 * Intelligent AI Delegation — Express Application Entry Point
 *
 * Wires together all routes, middleware, and error handling for the
 * framework's backend API server.
 *
 * API surface:
 *   /api/v1/decompose/*     → Task Decomposition Engine
 *   /api/v1/market/*        → Decentralized Market Hub
 *   /api/v1/contracts/*     → Smart Contract Lifecycle
 *   /api/v1/resources/*     → Permission-gated mock resource (demo)
 */

import express, { type Request, type Response, type NextFunction } from "express";
import { decomposeRouter } from "./routes/decompose.routes";
import { marketRouter } from "./routes/market.routes";
import { contractRouter } from "./routes/contract.routes";
import {
  requirePermission,
  type AuthenticatedRequest,
} from "./middleware/permission-gateway";

const app = express();
const PORT = process.env.PORT ?? 3000;

// ---------------------------------------------------------------------------
// Global middleware
// ---------------------------------------------------------------------------

app.use(express.json({ limit: "1mb" }));

// Request logging
app.use((req: Request, _res: Response, next: NextFunction) => {
  const start = Date.now();
  const originalEnd = _res.end.bind(_res);
  _res.end = function (...args: Parameters<typeof originalEnd>) {
    const duration = Date.now() - start;
    console.log(
      `[${new Date().toISOString()}] ${req.method} ${req.originalUrl} → ${_res.statusCode} (${duration}ms)`
    );
    return originalEnd(...args);
  } as typeof _res.end;
  next();
});

// ---------------------------------------------------------------------------
// API Routes
// ---------------------------------------------------------------------------

// Task Decomposition Engine
app.use("/api/v1/decompose", decomposeRouter);

// Decentralized Market Hub
app.use("/api/v1/market", marketRouter);

// Smart Contract Lifecycle
app.use("/api/v1/contracts", contractRouter);

// ---------------------------------------------------------------------------
// Permission-Gated Resource (demo endpoint)
// ---------------------------------------------------------------------------
// This demonstrates the PermissionGateway middleware in action.
// An agent must have an active contract and the "api:read" scope
// to access this endpoint.

app.get(
  "/api/v1/resources/:taskId",
  requirePermission("api:read"),
  (req: Request, res: Response) => {
    const authed = req as AuthenticatedRequest;
    res.status(200).json({
      message: "Access granted — JIT permission verified",
      agentId: authed.agentId,
      taskId: authed.taskId,
      contractId: authed.contractId,
      grantId: authed.grantId,
      data: {
        example: "This is a protected resource",
        timestamp: new Date().toISOString(),
      },
    });
  }
);

app.post(
  "/api/v1/resources/:taskId",
  requirePermission("api:write"),
  (req: Request, res: Response) => {
    const authed = req as AuthenticatedRequest;
    res.status(200).json({
      message: "Write access granted — JIT permission verified",
      agentId: authed.agentId,
      taskId: authed.taskId,
      contractId: authed.contractId,
      body: req.body,
    });
  }
);

// ---------------------------------------------------------------------------
// Health check
// ---------------------------------------------------------------------------

app.get("/health", (_req: Request, res: Response) => {
  res.status(200).json({
    status: "healthy",
    service: "intel-ai-delegation-backend",
    version: "0.1.0",
    timestamp: new Date().toISOString(),
  });
});

// ---------------------------------------------------------------------------
// 404 & global error handler
// ---------------------------------------------------------------------------

app.use((_req: Request, res: Response) => {
  res.status(404).json({ error: "Not found", code: "NOT_FOUND" });
});

app.use((err: Error, _req: Request, res: Response, _next: NextFunction) => {
  console.error("[GlobalErrorHandler]", err);
  res.status(500).json({
    error: "Internal server error",
    code: "INTERNAL_ERROR",
    ...(process.env.NODE_ENV === "development" && { details: err.message }),
  });
});

// ---------------------------------------------------------------------------
// Start server
// ---------------------------------------------------------------------------

if (require.main === module) {
  app.listen(PORT, () => {
    console.log(`
  ┌─────────────────────────────────────────────────┐
  │  Intelligent AI Delegation — Backend API        │
  │  Running on http://localhost:${PORT}               │
  │                                                 │
  │  Endpoints:                                     │
  │    POST /api/v1/decompose/analyze               │
  │    POST /api/v1/decompose/:jobId/verify-outcomes│
  │    POST /api/v1/decompose/:jobId/finalize       │
  │    POST /api/v1/market/:taskId/bids             │
  │    GET  /api/v1/market/:taskId/bids             │
  │    POST /api/v1/market/:taskId/evaluate         │
  │    POST /api/v1/market/:taskId/select           │
  │    GET  /api/v1/contracts/:id                   │
  │    POST /api/v1/contracts/:id/accept            │
  │    POST /api/v1/contracts/:id/activate          │
  │    POST /api/v1/contracts/:id/complete          │
  │    POST /api/v1/contracts/:id/breach            │
  │    POST /api/v1/contracts/:id/terminate         │
  │    GET  /api/v1/contracts/:id/verify            │
  │    GET  /api/v1/resources/:taskId (gated)       │
  │    GET  /health                                 │
  └─────────────────────────────────────────────────┘
    `);
  });
}

export { app };
