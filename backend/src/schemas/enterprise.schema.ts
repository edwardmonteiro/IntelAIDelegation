/**
 * Enterprise Feature Schemas — Zod validation for RBAC, Audit, Org, Metering, Analytics.
 */

import { z } from "zod";

// ---------------------------------------------------------------------------
// RBAC Schemas
// ---------------------------------------------------------------------------

export const PermissionSchema = z.object({
  resource: z.string().min(1),
  action: z.string().min(1),
  description: z.string().default(""),
});
export type Permission = z.infer<typeof PermissionSchema>;

export const CreateRoleSchema = z.object({
  name: z.string().min(1).max(64),
  permissions: z.array(PermissionSchema).default([]),
  description: z.string().default(""),
  orgId: z.string().uuid().optional(),
});
export type CreateRole = z.infer<typeof CreateRoleSchema>;

export const RoleBindingSchema = z.object({
  agentId: z.string().min(1),
  roleId: z.string().uuid(),
  orgId: z.string().uuid().optional(),
  teamId: z.string().uuid().optional(),
  grantedBy: z.string().default(""),
  expiresAt: z.string().datetime().optional(),
});
export type RoleBindingInput = z.infer<typeof RoleBindingSchema>;

export const PolicySchema = z.object({
  name: z.string().min(1).max(128),
  effect: z.enum(["allow", "deny"]),
  resource: z.string().min(1),
  action: z.string().min(1),
  conditions: z.record(z.unknown()).default({}),
  priority: z.number().int().default(0),
  orgId: z.string().uuid().optional(),
  description: z.string().default(""),
});
export type PolicyInput = z.infer<typeof PolicySchema>;

export const AccessCheckSchema = z.object({
  agentId: z.string().min(1),
  resource: z.string().min(1),
  action: z.string().min(1),
  resourceId: z.string().default(""),
  context: z.record(z.unknown()).default({}),
});
export type AccessCheckInput = z.infer<typeof AccessCheckSchema>;

// ---------------------------------------------------------------------------
// Audit Trail Schemas
// ---------------------------------------------------------------------------

export const AuditQuerySchema = z.object({
  actorId: z.string().optional(),
  action: z.string().optional(),
  category: z
    .enum([
      "task",
      "contract",
      "delegation",
      "permission",
      "rbac",
      "agent",
      "market",
      "verification",
      "organization",
      "system",
    ])
    .optional(),
  level: z.enum(["debug", "info", "warning", "critical"]).optional(),
  resourceType: z.string().optional(),
  resourceId: z.string().optional(),
  orgId: z.string().uuid().optional(),
  startTime: z.string().datetime().optional(),
  endTime: z.string().datetime().optional(),
  limit: z.number().int().min(1).max(1000).default(100),
  offset: z.number().int().min(0).default(0),
});
export type AuditQueryInput = z.infer<typeof AuditQuerySchema>;

export const AuditExportSchema = z.object({
  query: AuditQuerySchema,
  format: z.enum(["json", "csv", "syslog"]).default("json"),
});
export type AuditExportInput = z.infer<typeof AuditExportSchema>;

// ---------------------------------------------------------------------------
// Organization Schemas
// ---------------------------------------------------------------------------

export const CreateOrgSchema = z.object({
  name: z.string().min(1).max(128),
  slug: z
    .string()
    .min(1)
    .max(64)
    .regex(/^[a-z0-9-]+$/),
  ownerId: z.string().min(1),
  settings: z.record(z.unknown()).default({}),
  maxAgents: z.number().int().min(1).default(100),
  maxTeams: z.number().int().min(1).default(20),
  maxTasksPerMonth: z.number().int().min(1).default(10000),
  billingEmail: z.string().email().optional(),
});
export type CreateOrgInput = z.infer<typeof CreateOrgSchema>;

export const UpdateOrgSchema = z.object({
  name: z.string().min(1).max(128).optional(),
  settings: z.record(z.unknown()).optional(),
  maxAgents: z.number().int().min(1).optional(),
  maxTeams: z.number().int().min(1).optional(),
  maxTasksPerMonth: z.number().int().min(1).optional(),
  billingEmail: z.string().email().optional(),
});
export type UpdateOrgInput = z.infer<typeof UpdateOrgSchema>;

export const CreateTeamSchema = z.object({
  orgId: z.string().uuid(),
  name: z.string().min(1).max(128),
  description: z.string().default(""),
  leadId: z.string().default(""),
});
export type CreateTeamInput = z.infer<typeof CreateTeamSchema>;

export const AddMemberSchema = z.object({
  agentId: z.string().min(1),
  orgId: z.string().uuid(),
  teamId: z.string().uuid().optional(),
  role: z.enum(["owner", "admin", "member", "viewer"]).default("member"),
  invitedBy: z.string().default(""),
});
export type AddMemberInput = z.infer<typeof AddMemberSchema>;

// ---------------------------------------------------------------------------
// Metering & Quota Schemas
// ---------------------------------------------------------------------------

export const UsageRecordSchema = z.object({
  orgId: z.string().uuid(),
  agentId: z.string().min(1),
  dimension: z.enum([
    "task_delegations",
    "contract_creations",
    "agent_registrations",
    "compute_cost",
    "api_calls",
    "storage_bytes",
    "verification_runs",
  ]),
  quantity: z.number().min(0).default(1),
  teamId: z.string().uuid().optional(),
  taskId: z.string().uuid().optional(),
});
export type UsageRecordInput = z.infer<typeof UsageRecordSchema>;

export const SetQuotaSchema = z.object({
  orgId: z.string().uuid(),
  dimension: z.enum([
    "task_delegations",
    "contract_creations",
    "agent_registrations",
    "compute_cost",
    "api_calls",
    "storage_bytes",
    "verification_runs",
  ]),
  limit: z.number().min(0),
  period: z
    .enum(["hourly", "daily", "monthly", "yearly", "lifetime"])
    .default("monthly"),
  teamId: z.string().uuid().optional(),
  alertThreshold: z.number().min(0).max(1).default(0.8),
  hardLimit: z.boolean().default(true),
});
export type SetQuotaInput = z.infer<typeof SetQuotaSchema>;

export const QuotaCheckSchema = z.object({
  orgId: z.string().uuid(),
  dimension: z.enum([
    "task_delegations",
    "contract_creations",
    "agent_registrations",
    "compute_cost",
    "api_calls",
    "storage_bytes",
    "verification_runs",
  ]),
  quantity: z.number().min(0).default(1),
});
export type QuotaCheckInput = z.infer<typeof QuotaCheckSchema>;

// ---------------------------------------------------------------------------
// Trust Analytics Schemas
// ---------------------------------------------------------------------------

export const TrendQuerySchema = z.object({
  agentId: z.string().min(1),
  dimension: z.string().default("overall"),
  windowDays: z.number().int().min(1).max(365).default(30),
});
export type TrendQueryInput = z.infer<typeof TrendQuerySchema>;

export const AnomalyQuerySchema = z.object({
  agentId: z.string().min(1),
  sensitivity: z.number().min(0.5).max(5).default(2.0),
});
export type AnomalyQueryInput = z.infer<typeof AnomalyQuerySchema>;

export const CompareAgentsSchema = z.object({
  domain: z.string().min(1),
  topN: z.number().int().min(1).max(100).default(10),
});
export type CompareAgentsInput = z.infer<typeof CompareAgentsSchema>;

export const RiskAssessmentSchema = z.object({
  taskId: z.string().uuid(),
  agentId: z.string().min(1),
});
export type RiskAssessmentInput = z.infer<typeof RiskAssessmentSchema>;
