import axios, { AxiosError, type AxiosInstance } from "axios";

import { installDemoAdapter, IS_DEMO } from "@/lib/demo";
import type { ApiErrorBody, ApiErrorEnvelope } from "@/types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

/**
 * The single HTTP client.
 *
 * CHANGE LOG (v2.0): the entire token/refresh interceptor stack is gone — there
 * is no authentication, so there is no Authorization header to attach, no 401 to
 * intercept and no refresh race to guard against. What replaces it is error
 * NORMALIZATION: the backend now returns one error envelope for every failure,
 * and this interceptor converts it into a typed `ApiError` so no component ever
 * inspects `error.response.data.detail[0].msg` again.
 */
export const api: AxiosInstance = axios.create({
  baseURL: API_URL,
  // A request that hangs forever is worse than one that fails: the query never
  // settles, the skeleton never resolves, and the user gets no feedback at all.
  timeout: 30_000,
  headers: { "Content-Type": "application/json" },
});

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly context?: Record<string, unknown>;
  readonly requestId?: string;

  constructor(body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.code = body.code;
    this.status = body.status;
    this.context = body.context;
    this.requestId = body.request_id;
  }

  /** Field-level validation errors, when the failure was a 422. */
  get fieldErrors(): { field: string; message: string }[] {
    const fields = this.context?.fields;
    return Array.isArray(fields) ? (fields as { field: string; message: string }[]) : [];
  }

  get isNotFound() {
    return this.status === 404;
  }

  /** True when the failure means "there is nothing here yet", which the UI renders
   *  as an empty state rather than as an error. */
  get isEmptyState() {
    return ["not_found", "insufficient_data", "model_not_trained", "no_portfolio"].includes(
      this.code,
    );
  }

  get isNetwork() {
    return this.code === "network_error" || this.code === "timeout";
  }
}

function toApiError(error: AxiosError): ApiError {
  if (error.code === "ECONNABORTED") {
    return new ApiError({
      code: "timeout",
      message: "The request timed out. The server may be busy — try again.",
      status: 408,
    });
  }
  if (!error.response) {
    return new ApiError({
      code: "network_error",
      message: "Could not reach the API. Check that the backend is running.",
      status: 0,
    });
  }

  const data = error.response.data as Partial<ApiErrorEnvelope> & { detail?: unknown };
  if (data?.error?.code) return new ApiError(data.error);

  // Defensive fallback: an error shape we do not recognize (a proxy error page, an
  // upstream gateway) must still become a typed ApiError rather than leaking an
  // unknown object into a component's error branch.
  return new ApiError({
    code: `http_${error.response.status}`,
    message:
      typeof data?.detail === "string"
        ? data.detail
        : (error.message ?? "The request failed unexpectedly."),
    status: error.response.status,
  });
}

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => Promise.reject(toApiError(error)),
);

/**
 * Demo mode swaps the transport, not the data layer.
 *
 * Replacing the ADAPTER (rather than mocking hooks) means every interceptor
 * above still runs: the demo's error envelopes become the same typed `ApiError`
 * a real 404 would, so empty states and error states are exercised for real.
 * With NEXT_PUBLIC_DEMO_MODE unset this branch is dead code and the module is
 * tree-shaken out of the bundle.
 */
if (IS_DEMO) {
  installDemoAdapter(api);
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong. Please try again.";
}

/** Typed helpers — keep `const { data } = await api.get<T>(...)` out of every hook
 *  and make the query functions one-liners. */
export async function get<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const { data } = await api.get<T>(url, { params });
  return data;
}

export async function post<T>(
  url: string,
  body?: unknown,
  params?: Record<string, unknown>,
): Promise<T> {
  const { data } = await api.post<T>(url, body, { params });
  return data;
}

export async function patch<T>(url: string, body?: unknown): Promise<T> {
  const { data } = await api.patch<T>(url, body);
  return data;
}

export async function del<T>(url: string): Promise<T> {
  const { data } = await api.delete<T>(url);
  return data;
}
