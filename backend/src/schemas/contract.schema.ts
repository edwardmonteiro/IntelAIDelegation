import { z } from "zod";

// ---------------------------------------------------------------------------
// Delegation Capability Token (DCT) — the JIT permission token
// ---------------------------------------------------------------------------

export const DelegationCapabilityTokenSchema = z.object({
  /** The agent this token is issued to (DID). */
  agentId: z.string().min(1),
  /** The task scope of this token. */
  taskId: z.string().uuid(),
  /** The governing contract. */
  contractId: z.string().uuid(),
  /** Permission scopes granted, e.g. ["api:read:users", "storage:write:temp"]. */
  scopes: z.array(z.string()).min(1),
  /** Resource the scopes apply to ("*" = all). */
  resource: z.string().default("*"),
  /** ISO-8601 datetime when the token was issued. */
  issuedAt: z.string().datetime(),
  /** ISO-8601 datetime when the token expires. */
  expiresAt: z.string().datetime(),
  /** Cryptographic signature from the delegator's private key. */
  signature: z.string().min(1),
});
export type DelegationCapabilityToken = z.infer<
  typeof DelegationCapabilityTokenSchema
>;

// ---------------------------------------------------------------------------
// Permission Check Request — middleware validates this per-request
// ---------------------------------------------------------------------------

export const PermissionCheckSchema = z.object({
  agentId: z.string().min(1),
  taskId: z.string().uuid(),
  requiredScope: z.string().min(1),
  resource: z.string().default("*"),
});
export type PermissionCheck = z.infer<typeof PermissionCheckSchema>;
