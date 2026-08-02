/**
 * Demo mode: an in-browser stand-in for the FastAPI backend.
 *
 * WHY THIS EXISTS
 * ---------------
 * The deployed frontend and the FastAPI service are separate deployments. A
 * Vercel URL with no backend behind it renders every card as "Cannot reach the
 * API", which is a bad first impression of an otherwise complete application.
 * With `NEXT_PUBLIC_DEMO_MODE=true` the axios instance is handed a custom
 * ADAPTER instead of XHR, so requests never leave the page and are answered from
 * a generated dataset.
 *
 * WHY AN ADAPTER RATHER THAN MOCKED HOOKS
 * ---------------------------------------
 * Swapping the adapter means every hook, every query key, every error path and
 * every loading state runs unchanged. The demo exercises the real data layer -
 * including the error envelope and the empty-state codes - rather than bypassing
 * it. Deleting this directory and the two lines that reference it removes demo
 * mode completely, with no trace left in the components.
 *
 * WHAT IS HONEST ABOUT IT
 * -----------------------
 * Prices are synthetic (GBM with regime-switching volatility) exactly as the
 * Python seeder's are, and the UI says so via the demo badge. The ANALYTICS on
 * top of them - VaR, Sharpe, drawdown, beta, correlation, Monte Carlo, RSI,
 * MACD, ADX - are the real calculations, not decorative numbers.
 */

import type { AxiosInstance, AxiosResponse, InternalAxiosRequestConfig } from "axios";

import { DemoApiError, resolveRoute } from "./routes";
import type { DemoReport } from "./world";

/** Compile-time constant: Next.js inlines `process.env.NEXT_PUBLIC_*` at build. */
export const IS_DEMO = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Latency budget per endpoint family. Returning instantly is its own kind of
 * lie: skeleton states never render, and the app feels less real than it is.
 */
function latencyFor(path: string): number {
  if (path.includes("/models/train")) return 2_600;
  if (path.includes("/copilot/query")) return 900;
  if (path.includes("/documents/upload")) return 1_400;
  if (path.includes("monte-carlo")) return 420;
  if (path.includes("/predictions")) return 380;
  return 90 + Math.floor(Math.random() * 140);
}

function normalizeQuery(params: unknown): Record<string, string> {
  const query: Record<string, string> = {};
  if (params && typeof params === "object") {
    for (const [key, value] of Object.entries(params as Record<string, unknown>)) {
      if (value === undefined || value === null || value === "") continue;
      query[key] = String(value);
    }
  }
  return query;
}

function parseBody(data: unknown): unknown {
  if (typeof data === "string") {
    try {
      return JSON.parse(data);
    } catch {
      return {};
    }
  }
  return data;
}

/** Shaped like an AxiosError so `toApiError` in lib/api.ts normalizes it. */
function rejection(config: InternalAxiosRequestConfig, code: string, message: string, status: number) {
  return {
    isAxiosError: true,
    name: "AxiosError",
    message,
    config,
    response: {
      status,
      statusText: message,
      data: { error: { code, message, status } },
      headers: {},
      config,
    },
  };
}

export function installDemoAdapter(instance: AxiosInstance): void {
  instance.defaults.adapter = async (config: InternalAxiosRequestConfig) => {
    const rawUrl = config.url ?? "/";
    const path = rawUrl.split("?")[0];
    const method = (config.method ?? "get").toLowerCase();

    await delay(latencyFor(path));

    const match = resolveRoute(method, path);
    if (!match) {
      throw rejection(
        config,
        "not_found",
        `Demo mode has no handler for ${method.toUpperCase()} ${path}.`,
        404,
      );
    }

    try {
      const data = match.handler({
        params: match.params,
        query: normalizeQuery(config.params),
        body: parseBody(config.data),
        raw: config.data,
      });
      return {
        data,
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      } as unknown as AxiosResponse;
    } catch (error) {
      if (error instanceof DemoApiError) {
        throw rejection(config, error.code, error.message, error.status);
      }
      throw rejection(
        config,
        "demo_error",
        error instanceof Error ? error.message : "Demo mode failed to build a response.",
        500,
      );
    }
  };
}

// --- Report downloads ------------------------------------------------------------

function asciiSafe(text: string): string {
  // The hand-built PDF below counts bytes as characters, so the content stream
  // must stay single-byte. Rs replaces the rupee sign rather than dropping it.
  return text.replace(/₹/g, "Rs ").replace(/[^\x20-\x7E]/g, " ");
}

/** A genuinely valid single-page PDF, assembled with a correct xref table. */
function buildPdf(lines: string[]): Blob {
  const content = lines
    .map((line, index) => `BT /F1 ${index === 0 ? 16 : 10} Tf 56 ${770 - index * 20} Td (${asciiSafe(line).replace(/([()\\])/g, "\\$1")}) Tj ET`)
    .join("\n");

  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    `<< /Length ${content.length} >>\nstream\n${content}\nendstream`,
  ];

  let pdf = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((body, index) => {
    offsets.push(pdf.length);
    pdf += `${index + 1} 0 obj\n${body}\nendobj\n`;
  });

  const xrefOffset = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (const offset of offsets) {
    pdf += `${String(offset).padStart(10, "0")} 00000 n \n`;
  }
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`;

  return new Blob([pdf], { type: "application/pdf" });
}

function buildCsv(lines: string[]): Blob {
  const rows = ["field,value", ...lines.map((line) => `"${line.replace(/"/g, '""')}",`)];
  return new Blob([rows.join("\n")], { type: "text/csv" });
}

/**
 * Demo reports are generated in the browser, because there is no backend to
 * stream a file from. The artifact is real and opens - it just describes the
 * demo dataset instead of a persisted portfolio.
 */
export function downloadDemoReport(report: DemoReport): void {
  const lines = [
    report.title,
    "",
    `Report type: ${report.report_type}`,
    `Format requested: ${report.report_format}`,
    `Generated: ${new Date(report.created_at).toUTCString()}`,
    `Portfolio: ${report.portfolio_id ?? "not scoped to a portfolio"}`,
    "",
    "This artifact was produced by StockVision Pro running in DEMO MODE.",
    "The underlying dataset is synthetic (geometric Brownian motion with",
    "regime-switching volatility), and the file was assembled in the browser",
    "rather than by the FastAPI report service.",
    "",
    "Run the backend and set NEXT_PUBLIC_DEMO_MODE=false to generate the real",
    "PDF / Excel / CSV artifacts, which include full holdings, risk metrics and",
    "prediction tables.",
  ];

  const blob = report.report_format === "pdf" ? buildPdf(lines) : buildCsv(lines);
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download =
    report.report_format === "pdf" ? report.filename : report.filename.replace(/\.xlsx$/, ".csv");
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2_000);
}
