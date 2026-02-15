/**
 * Proxy API requests to the backend with extended timeout.
 * Dashboard load can take 1-2 minutes; default proxy timeouts cause ECONNRESET.
 * Timeout: 5 minutes for long-running endpoints like /api/dashboard.
 */
import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_API_URL || "http://localhost:8002";
const TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path?: string[] }> }
) {
  const { path = [] } = await params;
  const apiPath = path.length ? path.join("/") : "";
  const backendUrl = `${BACKEND.replace(/\/$/, "")}/api/${apiPath}`;
  const search = request.nextUrl.search;
  const url = backendUrl + search;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const res = await fetch(url, {
      signal: controller.signal,
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const body = await res.text();
    clearTimeout(timeoutId);
    return new NextResponse(body, {
      status: res.status,
      headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
    });
  } catch (e) {
    clearTimeout(timeoutId);
    const msg = e instanceof Error ? e.message : "Proxy failed";
    console.error("[proxy] Failed to proxy", url, msg);
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
  const backendUrl = `${BACKEND.replace(/\/$/, "")}/api/${apiPath}`;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

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
    const msg = e instanceof Error ? e.message : "Proxy failed";
    console.error("[proxy] POST failed", backendUrl, msg);
    return NextResponse.json({ error: msg }, { status: 502 });
  }
}
