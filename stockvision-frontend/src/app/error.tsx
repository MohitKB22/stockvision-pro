"use client";

import * as React from "react";
import { AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";

/**
 * Route-level error boundary.
 *
 * Without this, an exception thrown during render replaces the entire page with
 * Next.js's default error screen and loses the app shell. This keeps the user
 * inside the product and gives them a working recovery action.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  React.useEffect(() => {
    // Surfaced in the browser console for local debugging; in production the
    // `digest` is the handle that correlates with the server-side log entry.
    console.error("Unhandled render error:", error);
  }, [error]);

  return (
    <div className="grid min-h-[60vh] place-items-center px-6">
      <div className="text-center">
        <div className="mx-auto mb-5 grid size-14 place-items-center rounded-2xl border border-loss/30 bg-loss/10">
          <AlertTriangle className="size-6 text-loss" aria-hidden />
        </div>
        <h1 className="text-xl font-semibold tracking-tight text-ink">
          Something broke on this page
        </h1>
        <p className="mx-auto mt-2 max-w-md text-sm text-ink-subtle">
          {error.message || "An unexpected error occurred while rendering."}
        </p>
        {error.digest ? (
          <p className="mt-2 font-mono text-2xs text-ink-faint">Digest: {error.digest}</p>
        ) : null}
        <div className="mt-6 flex justify-center gap-2">
          <Button variant="primary" onClick={reset}>
            Try again
          </Button>
          <Button variant="outline" onClick={() => window.location.assign("/dashboard")}>
            Go to dashboard
          </Button>
        </div>
      </div>
    </div>
  );
}
