"use client";

import * as React from "react";
import type { ColumnDef } from "@tanstack/react-table";
import {
  Activity,
  AlertCircle,
  Bot,
  Cpu,
  Database,
  FileText,
  HardDrive,
  Server,
  Timer,
  Zap,
} from "lucide-react";

import { useAdminOverview, useAuditLogs } from "@/hooks/use-platform";
import { formatBytes, formatDate, formatDuration, formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { AuditEntry } from "@/types";
import { TimeSeriesChart } from "@/components/charts/area-chart";
import { StatCard } from "@/components/dashboard/stat-card";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { Progress } from "@/components/ui/misc";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SkeletonChart, SkeletonStatCard, SkeletonTable } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ErrorState } from "@/components/ui/states";

const CARD_ICONS: Record<string, React.ElementType> = {
  api_calls: Zap,
  predictions: Cpu,
  signals: Activity,
  documents: FileText,
  models: Cpu,
  copilot: Bot,
  error_rate: AlertCircle,
  latency: Timer,
};

const WINDOWS = [
  { value: "1", label: "Last hour" },
  { value: "24", label: "Last 24 hours" },
  { value: "168", label: "Last 7 days" },
  { value: "720", label: "Last 30 days" },
];

/**
 * Admin dashboard.
 *
 * Scoping note kept deliberately visible in the UI: this platform has no user
 * accounts and no billing, so there is no "Users" or "Subscriptions" panel.
 * Rendering those with invented numbers would be a fabricated component; what is
 * shown here is aggregated entirely from the audit log and the data tables this
 * application actually writes to.
 */
export default function AdminPage() {
  const [window, setWindow] = React.useState("24");
  const overviewQuery = useAdminOverview(Number(window));
  const logsQuery = useAuditLogs(150);

  const overview = overviewQuery.data;
  const health = overview?.health;

  const callSeries = React.useMemo(
    () =>
      (overview?.api_calls_series ?? []).map((point) => ({
        label: formatDate(point.timestamp, "time"),
        value: point.value,
      })),
    [overview],
  );

  const logColumns = React.useMemo<ColumnDef<AuditEntry>[]>(
    () => [
      {
        accessorKey: "timestamp",
        header: "Time",
        cell: ({ row }) => (
          <span className="text-2xs text-ink-muted">
            {formatDate(row.original.timestamp, "datetime")}
          </span>
        ),
      },
      {
        accessorKey: "action",
        header: "Action",
        cell: ({ row }) => <Badge variant="outline">{row.original.action}</Badge>,
      },
      {
        accessorKey: "resource",
        header: "Resource",
        cell: ({ row }) => (
          <span className="truncate font-mono text-2xs text-ink-subtle">
            {row.original.resource || "—"}
          </span>
        ),
      },
      {
        accessorKey: "status_code",
        header: "Status",
        cell: ({ row }) => {
          const status = row.original.status_code;
          if (status === null) return <span className="text-2xs text-ink-faint">—</span>;
          return (
            <Badge variant={status >= 500 ? "loss" : status >= 400 ? "warn" : "gain"}>
              {status}
            </Badge>
          );
        },
      },
      {
        accessorKey: "duration_ms",
        header: "Latency",
        cell: ({ row }) => (
          <span
            className={cn(
              "tabular text-2xs",
              (row.original.duration_ms ?? 0) > 1000 ? "text-warn" : "text-ink-muted",
            )}
          >
            {row.original.duration_ms ? `${row.original.duration_ms.toFixed(0)} ms` : "—"}
          </span>
        ),
      },
      {
        accessorKey: "request_id",
        header: "Request ID",
        enableSorting: false,
        cell: ({ row }) => (
          <span className="font-mono text-2xs text-ink-faint">
            {row.original.request_id ? row.original.request_id.slice(0, 12) : "—"}
          </span>
        ),
      },
    ],
    [],
  );

  return (
    <div className="space-y-5">
      <PageHeader
        title="Admin"
        description="Usage analytics, system health and the audit trail — all aggregated from real telemetry"
        actions={
          <Select value={window} onValueChange={setWindow}>
            <SelectTrigger className="w-[164px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {WINDOWS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        }
      />

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {overviewQuery.isLoading ? (
          Array.from({ length: 8 }).map((_, index) => <SkeletonStatCard key={index} />)
        ) : overviewQuery.isError ? (
          <div className="sm:col-span-2 xl:col-span-4">
            <Card>
              <CardContent className="pt-5">
                <ErrorState error={overviewQuery.error} onRetry={() => overviewQuery.refetch()} />
              </CardContent>
            </Card>
          </div>
        ) : (
          overview?.cards.map((card) => (
            <StatCard
              key={card.key}
              label={card.label}
              value={card.display}
              change={card.change_pct}
              changeLabel={card.change_pct === null ? card.hint : undefined}
              hint={card.change_pct === null ? undefined : card.hint}
              icon={CARD_ICONS[card.key] ?? Activity}
              accent={card.key === "error_rate" && card.value > 0.05 ? "loss" : "primary"}
              tone={card.change_pct === null ? "flat" : undefined}
            />
          ))
        )}
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <div>
              <CardTitle>API Traffic</CardTitle>
              <p className="mt-0.5 text-2xs text-ink-faint">
                Requests per hour, recorded by the audit middleware on every API call
              </p>
            </div>
          </CardHeader>
          <CardContent>
            {overviewQuery.isLoading ? (
              <SkeletonChart />
            ) : (
              <TimeSeriesChart
                data={callSeries}
                height={240}
                tone="primary"
                valueFormatter={(value) => value.toFixed(0)}
              />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <Server className="size-3.5 text-primary" aria-hidden />
              System Health
            </CardTitle>
            {health ? (
              <Badge variant={health.status === "healthy" ? "gain" : "loss"}>{health.status}</Badge>
            ) : null}
          </CardHeader>
          <CardContent>
            {overviewQuery.isLoading ? (
              <SkeletonChart className="h-[240px]" />
            ) : health ? (
              <dl className="space-y-2.5">
                <HealthRow label="Environment" value={health.environment} />
                <HealthRow label="Version" value={`v${health.version}`} />
                <HealthRow label="Uptime" value={formatDuration(health.uptime_seconds)} />
                <HealthRow
                  label="Database"
                  value={`${health.database_dialect} · ${health.database_latency_ms.toFixed(1)} ms`}
                  tone={health.database_connected ? "gain" : "loss"}
                />
                <HealthRow
                  label="Redis"
                  value={health.redis_configured ? "Configured" : "Not configured"}
                  hint="Configured, not verified-connected — this process holds no open Redis connection."
                />
                <HealthRow
                  label="LLM provider"
                  value={health.llm_provider}
                  tone={health.llm_provider === "extractive_fallback" ? undefined : "gain"}
                />
                <HealthRow label="Python" value={health.python_version} />
                <HealthRow label="CPU cores" value={String(health.cpu_count)} />

                <div className="pt-2">
                  <div className="mb-1 flex justify-between text-2xs">
                    <span className="text-ink-subtle">Disk usage</span>
                    <span className="tabular text-ink-muted">
                      {formatPercent(health.disk_usage_pct, { signed: false, decimals: 0 })}
                    </span>
                  </div>
                  <Progress
                    value={health.disk_usage_pct * 100}
                    indicatorClassName={health.disk_usage_pct > 0.85 ? "bg-loss" : "bg-primary"}
                  />
                </div>
              </dl>
            ) : null}
          </CardContent>
        </Card>
      </section>

      <Tabs defaultValue="storage">
        <TabsList className="flex-wrap">
          <TabsTrigger value="storage">
            <HardDrive aria-hidden /> Storage &amp; Data
          </TabsTrigger>
          <TabsTrigger value="endpoints">Endpoint Usage</TabsTrigger>
          <TabsTrigger value="logs">Audit Log</TabsTrigger>
        </TabsList>

        <TabsContent value="storage">
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-1.5">
                  <Database className="size-3.5 text-info" aria-hidden />
                  Record Counts
                </CardTitle>
              </CardHeader>
              <CardContent>
                <dl className="grid grid-cols-2 gap-x-6 gap-y-2.5">
                  {Object.entries(overview?.data_counts ?? {}).map(([key, count]) => (
                    <div
                      key={key}
                      className="flex items-baseline justify-between gap-2 border-b border-line/60 pb-1.5"
                    >
                      <dt className="truncate text-2xs capitalize text-ink-subtle">
                        {key.replace(/_/g, " ")}
                      </dt>
                      <dd className="tabular shrink-0 text-xs font-medium text-ink">
                        {count.toLocaleString()}
                      </dd>
                    </div>
                  ))}
                </dl>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-1.5">
                  <HardDrive className="size-3.5 text-accent" aria-hidden />
                  Storage Consumption
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <StorageRow
                  label="Document corpus"
                  bytes={health?.document_storage_bytes ?? 0}
                  hint="Uploaded PDFs indexed by the AI Copilot"
                />
                <StorageRow
                  label="Model artifacts"
                  bytes={health?.model_storage_bytes ?? 0}
                  hint="Serialized trained models in the registry"
                />
                <StorageRow
                  label="Generated reports"
                  bytes={health?.report_storage_bytes ?? 0}
                  hint="PDF, Excel and CSV exports on disk"
                />
                <p className="border-t border-line pt-3 text-2xs leading-relaxed text-ink-faint">
                  Report artifacts accumulate on disk. Deleting a report from the Reports page
                  removes both its database record and its file.
                </p>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="endpoints">
          <Card>
            <CardHeader>
              <div>
                <CardTitle>Operations by Type</CardTitle>
                <p className="mt-0.5 text-2xs text-ink-faint">
                  Audit-log entries grouped by action over the selected window
                </p>
              </div>
            </CardHeader>
            <CardContent>
              <ActionBreakdown counts={overview?.calls_by_action ?? {}} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="logs">
          <Card>
            <CardHeader>
              <div>
                <CardTitle>Audit Log</CardTitle>
                <p className="mt-0.5 text-2xs text-ink-faint">
                  Every entry carries the request ID that correlates it with the application logs
                </p>
              </div>
            </CardHeader>
            <CardContent>
              {logsQuery.isLoading ? (
                <SkeletonTable rows={10} columns={6} />
              ) : (
                <DataTable
                  columns={logColumns}
                  data={logsQuery.data ?? []}
                  emptyTitle="No audit entries"
                  pageSize={20}
                  dense
                />
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <p className="rounded-lg border border-line bg-elevated/40 px-3 py-2 text-2xs leading-relaxed text-ink-faint">
        <strong className="text-ink-subtle">Scope note:</strong> this platform has no user accounts
        and no billing, so there are no Users or Subscriptions panels here. Every figure above is
        aggregated from the audit log and the tables the application actually writes to.
      </p>
    </div>
  );
}

function ActionBreakdown({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  if (!entries.length) {
    return (
      <p className="py-8 text-center text-xs text-ink-faint">
        No activity recorded in this window.
      </p>
    );
  }
  const max = Math.max(...entries.map(([, count]) => count), 1);

  return (
    <ul className="space-y-2.5">
      {entries.map(([action, count]) => (
        <li key={action}>
          <div className="mb-1 flex items-baseline justify-between text-2xs">
            <span className="capitalize text-ink-muted">{action.replace(/_/g, " ")}</span>
            <span className="tabular text-ink">{count.toLocaleString()}</span>
          </div>
          <Progress value={(count / max) * 100} />
        </li>
      ))}
    </ul>
  );
}

function HealthRow({
  label,
  value,
  tone,
  hint,
}: {
  label: string;
  value: string;
  tone?: "gain" | "loss";
  hint?: string;
}) {
  return (
    <div
      className="flex items-baseline justify-between gap-3 border-b border-line/60 pb-1.5"
      title={hint}
    >
      <dt className="text-2xs text-ink-subtle">{label}</dt>
      <dd
        className={cn(
          "truncate text-2xs font-medium",
          tone === "gain" ? "text-gain" : tone === "loss" ? "text-loss" : "text-ink",
        )}
      >
        {value}
      </dd>
    </div>
  );
}

function StorageRow({ label, bytes, hint }: { label: string; bytes: number; hint: string }) {
  // 1 GB reference ceiling for the bar — the absolute figure is authoritative, the
  // bar is only there for at-a-glance relative scale.
  const share = Math.min(bytes / 1_073_741_824, 1);
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <span className="text-xs text-ink-muted">{label}</span>
        <span className="tabular text-xs font-medium text-ink">{formatBytes(bytes)}</span>
      </div>
      <Progress value={share * 100} />
      <p className="mt-1 text-2xs text-ink-faint">{hint}</p>
    </div>
  );
}
