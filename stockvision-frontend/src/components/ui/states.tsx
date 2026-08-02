"use client";

import { AlertTriangle, Inbox, RefreshCw, WifiOff } from "lucide-react";

import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

import { Button } from "./button";

/**
 * The three non-success states every data view needs.
 *
 * One implementation is what makes them consistent: previously each page invented
 * its own "nothing here" markup, or more often rendered nothing at all and left
 * the user staring at blank space.
 */

export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
  className,
}: {
  icon?: React.ElementType;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn("flex flex-col items-center justify-center px-6 py-12 text-center", className)}
    >
      <div className="mb-4 grid size-12 place-items-center rounded-2xl border border-line bg-elevated">
        <Icon className="size-5 text-ink-subtle" aria-hidden />
      </div>
      <p className="text-sm font-medium text-ink">{title}</p>
      {description ? (
        <p className="mt-1.5 max-w-sm text-xs text-ink-subtle">{description}</p>
      ) : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  const apiError = error instanceof ApiError ? error : null;

  // "Nothing has been created yet" is not a failure. Rendering it as a red error
  // box trains users to ignore red error boxes.
  if (apiError?.isEmptyState) {
    return (
      <EmptyState
        title={apiError.message}
        description="This view will populate once the underlying data exists."
        className={className}
      />
    );
  }

  const isNetwork = apiError?.isNetwork ?? false;
  const Icon = isNetwork ? WifiOff : AlertTriangle;

  return (
    <div
      className={cn("flex flex-col items-center justify-center px-6 py-12 text-center", className)}
    >
      <div className="mb-4 grid size-12 place-items-center rounded-2xl border border-loss/30 bg-loss/10">
        <Icon className="size-5 text-loss" aria-hidden />
      </div>
      <p className="text-sm font-medium text-ink">
        {isNetwork ? "Cannot reach the API" : "Something went wrong"}
      </p>
      <p className="mt-1.5 max-w-md text-xs text-ink-subtle">
        {apiError?.message ??
          (error instanceof Error ? error.message : "An unexpected error occurred.")}
      </p>
      {apiError?.requestId ? (
        <p className="mt-2 font-mono text-2xs text-ink-faint">Request ID: {apiError.requestId}</p>
      ) : null}
      {onRetry ? (
        <Button variant="outline" size="sm" className="mt-5" onClick={onRetry}>
          <RefreshCw aria-hidden />
          Try again
        </Button>
      ) : null}
    </div>
  );
}
