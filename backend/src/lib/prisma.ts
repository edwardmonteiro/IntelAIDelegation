import { PrismaClient } from "@prisma/client";

/**
 * Singleton Prisma client instance.
 *
 * In development, hot-reload can create multiple PrismaClient instances.
 * This module ensures a single connection pool is reused across the app.
 */

const globalForPrisma = globalThis as unknown as {
  prisma: PrismaClient | undefined;
};

export const prisma =
  globalForPrisma.prisma ??
  new PrismaClient({
    log:
      process.env.NODE_ENV === "development"
        ? ["query", "error", "warn"]
        : ["error"],
  });

if (process.env.NODE_ENV !== "production") {
  globalForPrisma.prisma = prisma;
}
