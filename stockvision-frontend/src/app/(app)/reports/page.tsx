"use client";

import * as React from "react";
import {
  Download,
  FileSpreadsheet,
  FileText,
  ShieldAlert,
  Sparkles,
  Trash2,
  Wallet,
} from "lucide-react";

import {
  downloadReport,
  useDeleteReport,
  useGenerateReport,
  useReports,
} from "@/hooks/use-platform";
import { useDefaultPortfolio, usePortfolios } from "@/hooks/use-portfolio";
import { formatBytes, formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ReportFormat, ReportType } from "@/types";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/states";

const REPORT_DEFINITIONS: {
  type: ReportType;
  title: string;
  description: string;
  icon: React.ElementType;
  accent: string;
  needsPortfolio: boolean;
}[] = [
  {
    type: "portfolio",
    title: "Portfolio Report",
    description:
      "Holdings, cost basis, realized and unrealized P&L, sector allocation and weights.",
    icon: Wallet,
    accent: "border-gain/25 bg-gain/12 text-gain",
    needsPortfolio: true,
  },
  {
    type: "prediction",
    title: "Prediction Report",
    description: "Model registry with validation metrics, plus every recently generated signal.",
    icon: Sparkles,
    accent: "border-accent/25 bg-accent/12 text-accent",
    needsPortfolio: false,
  },
  {
    type: "risk",
    title: "Risk Report",
    description:
      "VaR across three methods, Sharpe, Sortino, drawdown, stress scenarios and correlations.",
    icon: ShieldAlert,
    accent: "border-warn/25 bg-warn/12 text-warn",
    needsPortfolio: true,
  },
  {
    type: "tax",
    title: "Tax Report",
    description: "Capital-gains summary and the complete transaction ledger. Not tax advice.",
    icon: FileText,
    accent: "border-primary/25 bg-primary/12 text-primary",
    needsPortfolio: true,
  },
];

const FORMATS: { value: ReportFormat; label: string; icon: React.ElementType }[] = [
  { value: "pdf", label: "PDF", icon: FileText },
  { value: "excel", label: "Excel", icon: FileSpreadsheet },
  { value: "csv", label: "CSV", icon: FileSpreadsheet },
];

export default function ReportsPage() {
  const [format, setFormat] = React.useState<ReportFormat>("pdf");
  const [selectedId, setSelectedId] = React.useState<string | undefined>();
  const [pending, setPending] = React.useState<ReportType | null>(null);

  const portfoliosQuery = usePortfolios();
  const defaultQuery = useDefaultPortfolio();
  const portfolioId = selectedId ?? defaultQuery.data?.id ?? portfoliosQuery.data?.[0]?.id;

  const reportsQuery = useReports();
  const generate = useGenerateReport();
  const deleteReport = useDeleteReport();

  const run = async (type: ReportType) => {
    setPending(type);
    try {
      await generate.mutateAsync({
        report_type: type,
        report_format: format,
        portfolio_id: portfolioId,
      });
    } finally {
      setPending(null);
    }
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title="Reports"
        description="Generate downloadable PDF, Excel and CSV artifacts from live platform data"
        actions={
          <>
            {(portfoliosQuery.data?.length ?? 0) > 1 ? (
              <Select value={portfolioId} onValueChange={setSelectedId}>
                <SelectTrigger className="w-[184px]">
                  <SelectValue placeholder="Portfolio" />
                </SelectTrigger>
                <SelectContent>
                  {portfoliosQuery.data?.map((portfolio) => (
                    <SelectItem key={portfolio.id} value={portfolio.id}>
                      {portfolio.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : null}
            <div className="flex gap-1 rounded-xl border border-line bg-elevated/60 p-1">
              {FORMATS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setFormat(option.value)}
                  aria-pressed={format === option.value}
                  className={cn(
                    "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
                    format === option.value
                      ? "bg-primary/15 text-primary"
                      : "text-ink-subtle hover:text-ink",
                  )}
                >
                  <option.icon className="size-3.5" aria-hidden />
                  {option.label}
                </button>
              ))}
            </div>
          </>
        }
      />

      <section className="grid gap-4 sm:grid-cols-2">
        {REPORT_DEFINITIONS.map((definition) => {
          const blocked = definition.needsPortfolio && !portfolioId;
          const Icon = definition.icon;
          return (
            <Card key={definition.type} className="flex flex-col p-5">
              <div className="flex items-start gap-3">
                <span
                  className={cn(
                    "grid size-10 shrink-0 place-items-center rounded-xl border",
                    definition.accent,
                  )}
                >
                  <Icon className="size-5" aria-hidden />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-ink">{definition.title}</p>
                  <p className="mt-1 text-xs leading-relaxed text-ink-subtle">
                    {definition.description}
                  </p>
                </div>
              </div>
              <div className="mt-4 flex items-center gap-2">
                <Button
                  variant="primary"
                  size="sm"
                  disabled={blocked}
                  loading={pending === definition.type}
                  onClick={() => run(definition.type)}
                >
                  <Download aria-hidden /> Generate {format.toUpperCase()}
                </Button>
                {blocked ? (
                  <span className="text-2xs text-ink-faint">Requires a portfolio</span>
                ) : null}
              </div>
            </Card>
          );
        })}
      </section>

      <Card>
        <CardHeader>
          <div>
            <CardTitle>Generated Reports</CardTitle>
            <p className="mt-0.5 text-2xs text-ink-faint">
              Files are stored server-side and can be re-downloaded at any time
            </p>
          </div>
        </CardHeader>
        <CardContent>
          {reportsQuery.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, index) => (
                <Skeleton key={index} className="h-14 w-full rounded-xl" />
              ))}
            </div>
          ) : !reportsQuery.data?.length ? (
            <EmptyState
              icon={FileText}
              title="No reports generated yet"
              description="Generate one above and it will download immediately and appear in this list."
            />
          ) : (
            <ul className="space-y-2">
              {reportsQuery.data.map((report) => (
                <li
                  key={report.id}
                  className="flex flex-wrap items-center gap-3 rounded-xl border border-line bg-elevated/40 px-3 py-2.5"
                >
                  <FileText className="size-4 shrink-0 text-ink-faint" aria-hidden />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-medium text-ink">{report.title}</p>
                    <p className="text-2xs text-ink-faint">
                      {report.filename} · {formatBytes(report.size_bytes)} ·{" "}
                      {formatDate(report.created_at, "datetime")}
                    </p>
                  </div>
                  <Badge variant="outline">{report.report_format.toUpperCase()}</Badge>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Download"
                    onClick={() => downloadReport(report)}
                  >
                    <Download aria-hidden />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Delete report"
                    onClick={() => deleteReport.mutate(report.id)}
                  >
                    <Trash2 aria-hidden />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <p className="text-2xs leading-relaxed text-ink-faint">
        Reports are built from the same service calls that render these pages, so a report can never
        disagree with the screen it was generated from. The tax report summarises disposal data only
        — it is not tax advice and does not compute a liability.
      </p>
    </div>
  );
}
