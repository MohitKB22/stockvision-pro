"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useMarket } from "@/context/market-context";
import { API_URL, ApiError, del, get, patch, post } from "@/lib/api";
import { downloadDemoReport, IS_DEMO } from "@/lib/demo";
import { queryKeys } from "@/lib/query-keys";
import type {
  AdminOverview,
  AppSettings,
  AuditEntry,
  GeneratedReport,
  IntegrationStatus,
  NewsFeed,
  OperationResult,
  ReportFormat,
  ReportType,
  SentimentSummary,
  Watchlist,
} from "@/types";

// --- News ---------------------------------------------------------------
export function useNews(symbol?: string, limit = 30) {
  const { market } = useMarket();
  return useQuery({
    queryKey: queryKeys.news(market, symbol, limit),
    queryFn: () => get<NewsFeed>("/news", { market, symbol, limit }),
    staleTime: 2 * 60_000,
  });
}

export function useMarketSentiment(days = 7) {
  const { market } = useMarket();
  return useQuery({
    queryKey: [...queryKeys.sentiment(market), days],
    queryFn: () => get<SentimentSummary>("/news/sentiment", { market, days }),
    staleTime: 5 * 60_000,
  });
}

// --- Watchlist -----------------------------------------------------------
export function useWatchlist() {
  const { market } = useMarket();
  return useQuery({
    queryKey: queryKeys.defaultWatchlist(market),
    queryFn: () => get<Watchlist>("/watchlists/default", { market }),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}

export function useAddToWatchlist(watchlistId: string | undefined) {
  const queryClient = useQueryClient();
  const { market } = useMarket();
  return useMutation({
    mutationFn: (payload: { symbol: string; alert_above?: number; alert_below?: number }) =>
      post<Watchlist>(`/watchlists/${watchlistId}/items`, payload),
    onSuccess: (_data, variables) => {
      toast.success(`${variables.symbol.toUpperCase()} added to watchlist`);
      queryClient.invalidateQueries({ queryKey: queryKeys.defaultWatchlist(market) });
    },
    onError: (error: ApiError) =>
      toast.error("Could not add symbol", { description: error.message }),
  });
}

export function useRemoveFromWatchlist(watchlistId: string | undefined) {
  const queryClient = useQueryClient();
  const { market } = useMarket();
  return useMutation({
    mutationFn: (symbol: string) => del<Watchlist>(`/watchlists/${watchlistId}/items/${symbol}`),
    onSuccess: (_data, symbol) => {
      toast.success(`${symbol} removed from watchlist`);
      queryClient.invalidateQueries({ queryKey: queryKeys.defaultWatchlist(market) });
    },
    onError: (error: ApiError) =>
      toast.error("Could not remove symbol", { description: error.message }),
  });
}

// --- Reports ----------------------------------------------------------------
export function useReports(reportType?: ReportType) {
  return useQuery({
    queryKey: queryKeys.reports(reportType),
    queryFn: () => get<GeneratedReport[]>("/reports", { report_type: reportType, limit: 50 }),
    staleTime: 30_000,
  });
}

/**
 * Downloads a generated artifact.
 *
 * The URL is built from API_URL rather than the relative `download_url` the API
 * returns, because the frontend and backend are separate origins in the default
 * development setup — a relative link would resolve against :3000 and 404.
 */
export function downloadReport(report: GeneratedReport) {
  // In demo mode there is no server to stream the artifact from, so the file is
  // assembled in the browser instead. Same click, same filename, real file.
  if (IS_DEMO) {
    downloadDemoReport(report);
    return;
  }
  const base = API_URL.replace(/\/api\/v1\/?$/, "");
  const anchor = document.createElement("a");
  anchor.href = `${base}${report.download_url}`;
  anchor.download = report.filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

export function useGenerateReport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      report_type: ReportType;
      report_format: ReportFormat;
      portfolio_id?: string;
      lookback_days?: number;
    }) => post<GeneratedReport>("/reports/generate", payload),
    onSuccess: (report) => {
      toast.success("Report generated", { description: report.filename });
      queryClient.invalidateQueries({ queryKey: ["reports"] });
      // Trigger the download immediately — generating a report the user then has to
      // hunt for in a list is a needless extra step.
      downloadReport(report);
    },
    onError: (error: ApiError) =>
      toast.error("Report generation failed", { description: error.message }),
  });
}

export function useDeleteReport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (reportId: string) => del<OperationResult>(`/reports/${reportId}`),
    onSuccess: () => {
      toast.success("Report deleted");
      queryClient.invalidateQueries({ queryKey: ["reports"] });
    },
    onError: (error: ApiError) => toast.error("Delete failed", { description: error.message }),
  });
}

// --- Settings ------------------------------------------------------------------
export function useSettings() {
  return useQuery({
    queryKey: queryKeys.settings,
    queryFn: () => get<AppSettings>("/settings"),
    staleTime: 5 * 60_000,
  });
}

export function useUpdateSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<AppSettings>) => patch<AppSettings>("/settings", payload),
    onSuccess: (settings) => {
      // Write the response straight into the cache so the toggle the user just
      // flipped does not visually snap back while a refetch is in flight.
      queryClient.setQueryData(queryKeys.settings, settings);
      toast.success("Preferences saved");
    },
    onError: (error: ApiError) =>
      toast.error("Could not save preferences", { description: error.message }),
  });
}

export function useResetSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => post<AppSettings>("/settings/reset"),
    onSuccess: (settings) => {
      queryClient.setQueryData(queryKeys.settings, settings);
      toast.success("Preferences restored to defaults");
    },
  });
}

export function useIntegrations() {
  return useQuery({
    queryKey: queryKeys.integrations,
    queryFn: () => get<IntegrationStatus[]>("/settings/integrations"),
    staleTime: 5 * 60_000,
  });
}

// --- Admin ----------------------------------------------------------------------
export function useAdminOverview(windowHours = 24) {
  return useQuery({
    queryKey: queryKeys.adminOverview(windowHours),
    queryFn: () => get<AdminOverview>("/admin/overview", { window_hours: windowHours }),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}

export function useAuditLogs(limit = 100, action?: string) {
  return useQuery({
    queryKey: queryKeys.adminLogs(limit, action),
    queryFn: () => get<AuditEntry[]>("/admin/logs", { limit, action }),
    staleTime: 15_000,
  });
}
