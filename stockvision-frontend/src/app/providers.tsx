"use client";

import * as React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";

import { MarketProvider } from "@/context/market-context";
import { ApiError } from "@/lib/api";
import { TooltipProvider } from "@/components/ui/misc";

/**
 * Application providers.
 *
 * The QueryClient is created inside `useState` so each browser session gets its
 * own instance. A module-level client would be shared across every request in a
 * server-rendered context — i.e. one user's cached portfolio could be served to
 * another. That is a real data-leak class of bug, not a theoretical one.
 */
export function AppProviders({ children }: { children: React.ReactNode }) {
  const [client] = React.useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            gcTime: 5 * 60_000,
            refetchOnWindowFocus: false,
            retry: (failureCount, error) => {
              // Retrying a 404 or a validation error just delays the inevitable and
              // triples the load on an already-failing endpoint. Only transient
              // failures are worth a second attempt.
              if (error instanceof ApiError) {
                if (error.status >= 400 && error.status < 500) return false;
                if (error.code === "timeout") return failureCount < 1;
              }
              return failureCount < 2;
            },
            retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
          },
          mutations: { retry: 0 },
        },
      }),
  );

  return (
    <QueryClientProvider client={client}>
      <MarketProvider>
        <TooltipProvider delayDuration={200} skipDelayDuration={400}>
          {children}
          <Toaster
            theme="dark"
            position="bottom-right"
            richColors
            closeButton
            toastOptions={{
              classNames: {
                toast: "glass-strong !rounded-xl !border-line !text-ink",
                description: "!text-ink-subtle",
              },
            }}
          />
        </TooltipProvider>
      </MarketProvider>
    </QueryClientProvider>
  );
}
