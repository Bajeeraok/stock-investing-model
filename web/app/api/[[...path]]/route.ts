/**
 * Proxy API requests to the backend with extended timeout.
 * Dashboard load can take 1–3 minutes (cold start, many FMP/yfinance calls); shared/public use must not 502.
 * Ticker detail does many external fetches – can exceed 5 min for slow APIs.
 * Timeout: 15 min for /api/dashboard; 12 min for /api/ticker/*; 5 min for other endpoints.
 * Retries: 2 retries with backoff for long-running endpoints on 5xx or connection failure.
 */
import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_API_URL || "http://localhost:8002";
const TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes default
const DASHBOARD_TIMEOUT_MS = 15 * 60 * 1000; // 15 min – cold start + full run; shared use
const TICKER_TIMEOUT_MS = 12 * 60 * 1000;   // 12 min – ticker detail (many fetches)
const INSIGHTS_TIMEOUT_MS = 3 * 60 * 1000;  // 3 min – Yahoo + SEC 13F on cache miss

function getTimeoutMs(apiPath: string): number {
  if (apiPath === "dashboard" || apiPath.startsWith("dashboard/")) return DASHBOARD_TIMEOUT_MS;
  if (apiPath.startsWith("ticker/")) return TICKER_TIMEOUT_MS;
  if (apiPath.startsWith("insights/")) return INSIGHTS_TIMEOUT_MS;
  if (apiPath === "roadmaps") return 8 * 60 * 1000; // 8 min – N ticker details
  return TIMEOUT_MS;
}

function isDashboardPath(apiPath: string): boolean {
  return apiPath === "dashboard" || apiPath.startsWith("dashboard/");
}

/** Create undici Agent with high headers/body timeout to avoid HeadersTimeoutError on slow backend. */
function createAgent(timeoutMs: number) {
  const { Agent } = require("undici");
  return new Agent({
    headersTimeout: timeoutMs,
    bodyTimeout: timeoutMs,
    connectTimeout: 30000,
  });
}

async function fetchWithTimeout(
  url: string,
  timeoutMs: number,
  init?: RequestInit
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  const dispatcher = createAgent(timeoutMs);
  try {
    const res = await fetch(url, {
      ...init,
      signal: controller.signal,
      headers: { Accept: "application/json", ...(init?.headers as Record<string, string>) },
      cache: "no-store",
      // @ts-expect-error Node fetch accepts dispatcher from undici
      dispatcher,
    });
    clearTimeout(timeoutId);
    return res;
  } catch (e) {
    clearTimeout(timeoutId);
    throw e;
  }
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path?: string[] }> }
) {
  const { path = [] } = await params;
  const apiPath = path.length ? path.join("/") : "";
  const backendUrl = `${BACKEND.replace(/\/$/, "")}/api/${apiPath}`;
  const search = request.nextUrl.search;
  const url = backendUrl + search;
  const timeoutMs = getTimeoutMs(apiPath);
  const dashboardLike = isDashboardPath(apiPath);
  const tickerLike = apiPath.startsWith("ticker/");
  const longRunning = dashboardLike || tickerLike; // retry on 5xx for these

  const doFetch = async (): Promise<Response> => {
    return fetchWithTimeout(url, timeoutMs);
  };

  const backoffMs = [3000, 8000]; // first retry 3s, second 8s
  let lastErr: unknown = null;

  try {
    let res = await doFetch();
    // Up to 2 retries for long-running endpoints on 5xx (backend starting / overloaded)
    for (let i = 0; i < backoffMs.length && !res.ok && longRunning && res.status >= 500; i++) {
      console.warn("[proxy]", apiPath, "returned", res.status, ", retry", i + 1, "in", backoffMs[i] / 1000, "s");
      await new Promise((r) => setTimeout(r, backoffMs[i]));
      res = await doFetch();
    }
    const body = await res.text();
    return new NextResponse(body, {
      status: res.status,
      headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
    });
  } catch (e) {
    lastErr = e;
    const isAbort = e instanceof Error && (e as Error & { name?: string }).name === "AbortError";
    const cause = e instanceof Error && "cause" in e ? (e as Error & { cause?: unknown }).cause : null;
    const msg = isAbort
      ? `Request timed out after ${timeoutMs / 60000} minutes. Dashboard can take 2–3 min on first load; try again or check backend.`
      : e instanceof Error ? e.message : "Proxy failed";
    console.error("[proxy] Failed to proxy", url, msg, cause ? `(cause: ${String(cause)})` : "");

    // Up to 2 retries on connection/network failure for long-running endpoints
    if (longRunning) {
      for (let i = 0; i < backoffMs.length; i++) {
        try {
          console.warn("[proxy] Retry", i + 1, "in", backoffMs[i] / 1000, "s...");
          await new Promise((r) => setTimeout(r, backoffMs[i]));
          const res = await doFetch();
          const body = await res.text();
          return new NextResponse(body, {
            status: res.status,
            headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
          });
        } catch (retryErr) {
          lastErr = retryErr;
          const retryCause = retryErr instanceof Error && "cause" in retryErr ? (retryErr as Error & { cause?: unknown }).cause : null;
          console.error("[proxy] Retry", i + 1, "failed", url, retryCause ? String(retryCause) : retryErr);
        }
      }
    }

    const finalMsg = lastErr instanceof Error && (lastErr as Error & { name?: string }).name === "AbortError"
      ? `Request timed out after ${timeoutMs / 60000} minutes.`
      : msg;
    return NextResponse.json(
      { error: finalMsg, url },
      { status: 502 }
    );
  }
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path?: string[] }> }
) {
  const { path = [] } = await params;
  const apiPath = path.length ? path.join("/") : "";
  const search = request.nextUrl.search;
  const backendUrl = `${BACKEND.replace(/\/$/, "")}/api/${apiPath}${search}`;

  const timeoutMs = getTimeoutMs(apiPath);
  const contentType = request.headers.get("Content-Type");
  const body = contentType?.includes("multipart/form-data")
    ? await request.formData()
    : await request.text();
  const headers: Record<string, string> = { Accept: "application/json" };
  if (contentType && !contentType.includes("multipart/form-data")) {
    headers["Content-Type"] = contentType;
  }

  try {
    const res = await fetchWithTimeout(backendUrl, timeoutMs, {
      method: "POST",
      headers,
      body: body as BodyInit,
    });
    const resBody = await res.text();
    return new NextResponse(resBody, {
      status: res.status,
      headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
    });
  } catch (e) {
    const isAbort = e instanceof Error && (e as Error & { name?: string }).name === "AbortError";
    const msg = isAbort
      ? `Request timed out after ${timeoutMs / 60000} minutes.`
      : e instanceof Error ? e.message : "Proxy failed";
    console.error("[proxy] POST failed", backendUrl, msg);
    return NextResponse.json({ error: msg }, { status: 502 });
  }
}
