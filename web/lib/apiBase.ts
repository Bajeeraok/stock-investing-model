/**
 * API base for browser fetches.
 *
 * Railway / UAT: leave NEXT_PUBLIC_API_URL **unset** on the web service.
 * Server-side proxy uses BACKEND_API_URL (runtime). Browser uses same-origin `/api/*`.
 *
 * If NEXT_PUBLIC_API_URL points at localhost or http:// from an https:// deployed site,
 * ignore it — that causes "Failed to fetch" in the ticker modal and elsewhere.
 */
export function getApiBase(): string {
  const env = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");
  if (typeof window === "undefined") return env;

  const { protocol, hostname } = window.location;
  const onLocalDev = hostname === "localhost" || hostname === "127.0.0.1";

  if (!env) return "";

  if (!onLocalDev && /localhost|127\.0\.0\.1|:8002\b/.test(env)) {
    return "";
  }
  if (protocol === "https:" && env.startsWith("http://")) {
    return "";
  }
  return env;
}

export function apiUrl(path: string): string {
  const base = getApiBase();
  const p = path.startsWith("/") ? path : `/${path}`;
  return base ? `${base}${p}` : p;
}

export function isMobileLikeBrowser(): boolean {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia("(max-width: 768px)").matches ||
    ("ontouchstart" in window && !window.matchMedia("(pointer: fine)").matches)
  );
}

export function formatFetchError(err: unknown, context = "API"): string {
  const msg = err instanceof Error ? err.message : String(err);
  if (
    (err instanceof TypeError && /failed to fetch|networkerror|load failed/i.test(msg)) ||
    /timed out|timeout|aborted/i.test(msg)
  ) {
    const mobileHint = isMobileLikeBrowser()
      ? " Mobile Safari often cuts off requests after ~60s — tap Retry (second load is usually faster from cache)."
      : "";
    return (
      `${context}: could not reach the server.${mobileHint} ` +
      `On Railway UAT: set BACKEND_API_URL on the web service, add the web URL to backend CORS_ORIGINS, ` +
      `and leave NEXT_PUBLIC_API_URL empty so requests use the /api/* proxy.`
    );
  }
  if (err instanceof Error) return err.message;
  return String(err);
}

/** Same-origin or explicit API base; retries transient network/502 failures (mobile-friendly). */
export async function fetchJsonWithRetry<T = unknown>(
  path: string,
  opts?: {
    retries?: number;
    retryDelayMs?: number[];
    signal?: AbortSignal;
    cache?: RequestCache;
  }
): Promise<T> {
  const url = apiUrl(path);
  const delays = opts?.retryDelayMs ?? [3000, 8000];
  const maxAttempts = (opts?.retries ?? delays.length) + 1;
  let lastErr: unknown;

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      const res = await fetch(url, {
        signal: opts?.signal,
        cache: opts?.cache ?? "no-store",
        headers: { Accept: "application/json" },
      });
      if (!res.ok) {
        let detail = "";
        try {
          const body = await res.json();
          detail = typeof body?.error === "string" ? body.error : "";
        } catch {
          /* non-json body */
        }
        throw new Error(detail || `HTTP ${res.status}`);
      }
      return (await res.json()) as T;
    } catch (e) {
      lastErr = e;
      if (e instanceof DOMException && e.name === "AbortError") throw e;
      if (attempt < maxAttempts - 1) {
        const delay = delays[attempt] ?? delays[delays.length - 1] ?? 3000;
        await new Promise((r) => setTimeout(r, delay));
      }
    }
  }
  throw lastErr;
}
