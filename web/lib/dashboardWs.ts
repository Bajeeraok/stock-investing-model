/**
 * WebSocket client for silent dashboard cache push (replaces aggressive HTTP polling).
 */
import { getApiBase, apiUrl } from "@/lib/apiBase";

export type DashboardWsEvent = {
  type: "dashboard_updated" | "pong";
  kind?: string;
  ts?: string;
  refresh_ts?: string;
  quotes_updated_at?: string;
  signals_updated_at?: string;
  as_of_date?: string;
};

type WsConfig = { enabled: boolean; url: string | null };

let cachedWsUrl: string | null | undefined;

function httpToWs(httpUrl: string): string {
  return httpUrl.replace(/^https:/, "wss:").replace(/^http:/, "ws:");
}

/** Resolve WebSocket URL for dashboard push channel. */
export async function resolveDashboardWsUrl(): Promise<string | null> {
  if (cachedWsUrl !== undefined) return cachedWsUrl;

  const apiBase = getApiBase();
  if (apiBase) {
    cachedWsUrl = `${httpToWs(apiBase)}/api/dashboard/ws`;
    return cachedWsUrl;
  }

  const wsEnv = (process.env.NEXT_PUBLIC_DASHBOARD_WS_URL || process.env.NEXT_PUBLIC_WS_URL || "").replace(/\/$/, "");
  if (wsEnv) {
    cachedWsUrl = wsEnv.includes("/api/dashboard/ws") ? wsEnv : `${httpToWs(wsEnv)}/api/dashboard/ws`;
    return cachedWsUrl;
  }

  if (typeof window !== "undefined") {
    const { hostname } = window.location;
    if (hostname === "localhost" || hostname === "127.0.0.1") {
      cachedWsUrl = "ws://localhost:8002/api/dashboard/ws";
      return cachedWsUrl;
    }
  }

  try {
    const cfg = (await fetch(apiUrl("/api/dashboard/ws-config"), {
      cache: "no-store",
      headers: { Accept: "application/json" },
    }).then((r) => (r.ok ? r.json() : null))) as WsConfig | null;
    if (cfg?.enabled && cfg.url) {
      cachedWsUrl = cfg.url;
      return cachedWsUrl;
    }
  } catch {
    // proxy / backend unavailable
  }

  cachedWsUrl = null;
  return null;
}

export type DashboardWsConnection = {
  close: () => void;
  isConnected: () => boolean;
};

/**
 * Connect to dashboard push WebSocket. Reconnects with backoff.
 * Returns null when no WS URL is available (caller should fall back to HTTP poll).
 */
export async function connectDashboardWs(
  onUpdate: (event: DashboardWsEvent) => void,
): Promise<DashboardWsConnection | null> {
  const url = await resolveDashboardWsUrl();
  if (!url || typeof WebSocket === "undefined") return null;

  let ws: WebSocket | null = null;
  let closed = false;
  let connected = false;
  let retry = 0;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let pingTimer: ReturnType<typeof setInterval> | null = null;

  const clearTimers = () => {
    if (retryTimer) clearTimeout(retryTimer);
    retryTimer = null;
    if (pingTimer) clearInterval(pingTimer);
    pingTimer = null;
  };

  const scheduleReconnect = () => {
    if (closed) return;
    const delay = Math.min(30000, 1000 * 2 ** retry);
    retry += 1;
    retryTimer = setTimeout(() => connect(), delay);
  };

  const connect = () => {
    if (closed) return;
    try {
      ws = new WebSocket(url);
    } catch {
      scheduleReconnect();
      return;
    }

    ws.onopen = () => {
      connected = true;
      retry = 0;
      pingTimer = setInterval(() => {
        if (ws?.readyState === WebSocket.OPEN) ws.send("ping");
      }, 45000);
    };

    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(String(ev.data)) as DashboardWsEvent;
        if (data.type === "dashboard_updated") onUpdate(data);
      } catch {
        // ignore malformed
      }
    };

    ws.onclose = () => {
      connected = false;
      clearTimers();
      if (!closed) scheduleReconnect();
    };

    ws.onerror = () => {
      connected = false;
      try {
        ws?.close();
      } catch {
        // ignore
      }
    };
  };

  connect();

  return {
    close: () => {
      closed = true;
      clearTimers();
      connected = false;
      try {
        ws?.close();
      } catch {
        // ignore
      }
      ws = null;
    },
    isConnected: () => connected && ws?.readyState === WebSocket.OPEN,
  };
}
