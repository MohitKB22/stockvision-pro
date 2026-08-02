"use client";

import { useQuery } from "@tanstack/react-query";

import { get } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { cn } from "@/lib/utils";
import type { SystemHealth } from "@/types";

/**
 * Live API health indicator.
 *
 * A real probe of GET /admin/health, not a decorative green dot: if the backend is
 * down or its database is unreachable this turns red, and every page that follows
 * will show an error state consistent with it.
 */
export function SystemStatusDot({ collapsed = false }: { collapsed?: boolean }) {
  const { data, isError } = useQuery({
    queryKey: queryKeys.adminHealth,
    queryFn: () => get<SystemHealth>("/admin/health"),
    refetchInterval: 60_000,
    retry: 1,
    staleTime: 30_000,
  });

  const healthy = !isError && data?.database_connected;
  const label = isError ? "API unreachable" : healthy ? "All systems operational" : "Degraded";

  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-lg px-2.5 py-2 text-2xs",
        collapsed && "justify-center px-0",
      )}
      title={label}
    >
      <span className="relative flex size-2 shrink-0">
        <span
          className={cn(
            "absolute inline-flex size-full rounded-full opacity-60",
            healthy ? "animate-ping bg-gain" : "bg-loss",
          )}
          aria-hidden
        />
        <span
          className={cn(
            "relative inline-flex size-2 rounded-full",
            healthy ? "bg-gain" : "bg-loss",
          )}
          aria-hidden
        />
      </span>
      {!collapsed ? (
        <span className="truncate text-ink-subtle">
          {label}
          {data?.version ? <span className="text-ink-faint"> · v{data.version}</span> : null}
        </span>
      ) : null}
      <span className="sr-only" role="status">
        {label}
      </span>
    </div>
  );
}
