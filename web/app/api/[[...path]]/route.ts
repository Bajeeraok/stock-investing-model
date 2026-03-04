/**
 * Proxy API requests to the backend with extended timeout.
 * Dashboard load can take 1-2 minutes (longer under load); default proxy timeouts cause ECONNRESET.
 * Ticker detail does many external fetches (OHLCV, FMP, peers) – can exceed 5 min for slow APIs.
 * Timeout: 10 minutes for /api/dashboard and /api/ticker/*; 5 minutes for other endpoints.
 * Node fetch (undici) has a default headers timeout (~5 min); we use undici Agent to raise it.
 */
import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_API_URL || "http://localhost:8002";
const TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes default
const LONG_TIMEOUT_MS = 10 * 60 * 1000; // 10 minutes for heavy endpoints

function getTimeoutMs(apiPath: string): number {
  if (apiPath === "dashboard" || apiPath.startsWith("dashboard/")) return LONG_TIMEOUT_MS;
  if (apiPath.startsWith("ticker/")) return LONG_TIMEOUT_MS; // ticker detail: many fetches
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

  try {
    let res = await doFetch();
    // One retry for long-running endpoints if first attempt fails (e.g. ECONNRESET)
    if (!res.ok && longRunning && res.status >= 500) {
      console.warn("[proxy] Dashboard returned", res.status, ", retrying in 3s...");
      await new Promise((r) => setTimeout(r, 3000));
      res = await doFetch();
    }
    const body = await res.text();
    return new NextResponse(body, {
      status: res.status,
      headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
    });
  } catch (e) {
    const isAbort = e instanceof Error && (e as Error & { name?: string }).name === "AbortError";
    const cause = e instanceof Error && "cause" in e ? (e as Error & { cause?: unknown }).cause : null;
    const msg = isAbort
      ? `Request timed out after ${timeoutMs / 60000} minutes. Dashboard can take 1–2 min; check backend is running and not overloaded.`
      : e instanceof Error ? e.message : "Proxy failed";
    console.error("[proxy] Failed to proxy", url, msg, cause ? `(cause: ${String(cause)})` : "");

    if (longRunning && !isAbort) {
      try {
        console.warn("[proxy] Retrying dashboard in 3s...");
        await new Promise((r) => setTimeout(r, 3000));
        const res = await doFetch();
        const body = await res.text();
        return new NextResponse(body, {
          status: res.status,
          headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
        });
      } catch (retryErr) {
        const retryCause = retryErr instanceof Error && "cause" in retryErr ? (retryErr as Error & { cause?: unknown }).cause : null;
        console.error("[proxy] Retry failed", url, retryCause ? String(retryCause) : retryErr);
      }
    }

    return NextResponse.json(
      { error: msg, url },
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
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const contentType = request.headers.get("Content-Type");
    const body = contentType?.includes("multipart/form-data")
      ? await request.formData()
      : await request.text();
    const headers: Record<string, string> = { Accept: "application/json" };
    if (contentType && !contentType.includes("multipart/form-data")) {
      headers["Content-Type"] = contentType;
    }
    const res = await fetch(backendUrl, {
      method: "POST",
      signal: controller.signal,
      headers,
      body: body as BodyInit,
      cache: "no-store",
    });
    const resBody = await res.text();
    clearTimeout(timeoutId);
    return new NextResponse(resBody, {
      status: res.status,
      headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
    });
  } catch (e) {
    clearTimeout(timeoutId);
    const isAbort = e instanceof Error && (e as Error & { name?: string }).name === "AbortError";
    const msg = isAbort
      ? `Request timed out after ${timeoutMs / 60000} minutes.`
      : e instanceof Error ? e.message : "Proxy failed";
    console.error("[proxy] POST failed", backendUrl, msg);
    return NextResponse.json({ error: msg }, { status: 502 });
  }
}
