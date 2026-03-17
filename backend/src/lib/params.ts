/**
 * Utility for safely extracting Express route params.
 *
 * Express 5 types define req.params values as `string | string[]`.
 * This helper narrows the type to `string` for single-value params.
 */
import type { Request } from "express";

export function param(req: Request, name: string): string {
  const value = req.params[name];
  if (Array.isArray(value)) return value[0];
  return value ?? "";
}
