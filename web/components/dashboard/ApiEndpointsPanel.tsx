"use client";

/**
 * Ad-hoc API runner — curated endpoint catalog with click-to-run.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { ExternalLink, Play, Copy, Check, AlertTriangle, Terminal } from "lucide-react";
import { clsx } from "clsx";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

type CatalogEntry = {
  group: string;
  method: string;
  path: string;
  description: string;
  path_params?: Record<string, string>;
  query?: Record<string, string>;
  body?: Record<string, unknown>;
  confirm?: boolean;
  external?: boolean;
};

type RunResult = {
  status: number;
  ms: number;
  preview: string;
  ok: boolean;
};

function resolvePath(template: string, pathParams: Record<string, string>): string {
  let p = template;
  for (const [k, v] of Object.entries(pathParams)) {
    p = p.replace(`{${k}}`, encodeURIComponent(v));
  }
  return p;
}

function buildUrl(entry: CatalogEntry, pathParams: Record<string, string>, query: Record<string, string>): string {
  const path = resolvePath(entry.path, pathParams);
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v !== "" && v != null) qs.set(k, String(v));
  }
  const q = qs.toString();
  return q ? `${path}?${q}` : path;
}

function methodColor(method: string) {
  switch (method) {
    case "GET":
      return "bg-emerald-500/20 text-emerald-300 border-emerald-500/40";
    case "POST":
      return "bg-sky-500/20 text-sky-300 border-sky-500/40";
    case "DELETE":
      return "bg-red-500/20 text-red-300 border-red-500/40";
    default:
      return "bg-slate-500/20 text-slate-300 border-slate-600";
  }
}

function truncateJson(text: string, max = 4000): string {
  if (text.length <= max) return text;
  return text.slice(0, max) + `\n… (${text.length - max} more chars)`;
}

export function ApiEndpointsPanel() {
  const [catalog, setCatalog] = useState<CatalogEntry[]>([]);
  const [groups, setGroups] = useState<string[]>([]);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [groupFilter, setGroupFilter] = useState<string>("All");
  const [search, setSearch] = useState("");
  const [runningId, setRunningId] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, RunResult>>({});
  const [pathEdits, setPathEdits] = useState<Record<string, Record<string, string>>>({});
  const [queryEdits, setQueryEdits] = useState<Record<string, Record<string, string>>>({});
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const fetchCatalog = useCallback(async () => {
    setLoadErr(null);
    const url = API_BASE ? `${API_BASE}/api/dev/endpoints` : "/api/dev/endpoints";
    try {
      const r = await fetch(url);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      setCatalog(Array.isArray(j.endpoints) ? j.endpoints : []);
      setGroups(Array.isArray(j.groups) ? j.groups : []);
    } catch (e) {
      setLoadErr(e instanceof Error ? e.message : "Failed to load catalog");
    }
  }, []);

  useEffect(() => {
    fetchCatalog();
  }, [fetchCatalog]);

  const entryId = (e: CatalogEntry, i: number) => `${e.method}:${e.path}:${i}`;

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return catalog.filter((e, i) => {
      if (groupFilter !== "All" && e.group !== groupFilter) return false;
      if (!q) return true;
      const hay = `${e.method} ${e.path} ${e.description} ${e.group}`.toLowerCase();
      return hay.includes(q);
    });
  }, [catalog, groupFilter, search]);

  const getPathParams = (e: CatalogEntry, id: string) => {
    const defaults = e.path_params ?? {};
    return { ...defaults, ...(pathEdits[id] ?? {}) };
  };

  const getQuery = (e: CatalogEntry, id: string) => {
    const defaults = e.query ?? {};
    return { ...defaults, ...(queryEdits[id] ?? {}) };
  };

  const fullHref = (e: CatalogEntry, id: string) => {
    const rel = buildUrl(e, getPathParams(e, id), getQuery(e, id));
    return API_BASE ? `${API_BASE.replace(/\/$/, "")}${rel}` : rel;
  };

  const runEndpoint = async (e: CatalogEntry, id: string) => {
    if (e.external) {
      window.open(fullHref(e, id), "_blank", "noopener,noreferrer");
      return;
    }
    if (e.confirm && !window.confirm(`Run ${e.method} ${e.path}?\n\n${e.description}`)) return;

    setRunningId(id);
    const href = fullHref(e, id);
    const t0 = performance.now();
    try {
      const init: RequestInit = { method: e.method };
      if (e.method !== "GET" && e.method !== "HEAD" && e.body) {
        init.headers = { "Content-Type": "application/json" };
        init.body = JSON.stringify(e.body);
      } else if (e.method === "POST" && !e.body) {
        init.headers = { "Content-Type": "application/json" };
        init.body = "{}";
      }
      const r = await fetch(href, init);
      const text = await r.text();
      let preview: string;
      try {
        preview = truncateJson(JSON.stringify(JSON.parse(text), null, 2));
      } catch {
        preview = truncateJson(text);
      }
      setResults((prev) => ({
        ...prev,
        [id]: { status: r.status, ms: Math.round(performance.now() - t0), preview, ok: r.ok },
      }));
      setExpandedId(id);
    } catch (err) {
      setResults((prev) => ({
        ...prev,
        [id]: {
          status: 0,
          ms: Math.round(performance.now() - t0),
          preview: err instanceof Error ? err.message : "Request failed",
          ok: false,
        },
      }));
      setExpandedId(id);
    } finally {
      setRunningId(null);
    }
  };

  const copyUrl = async (e: CatalogEntry, id: string) => {
    const url = typeof window !== "undefined" ? `${window.location.origin}${fullHref(e, id)}` : fullHref(e, id);
    try {
      await navigator.clipboard.writeText(url);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 1500);
    } catch {
      /* ignore */
    }
  };

  if (loadErr) {
    return (
      <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-200">
        Could not load API catalog: {loadErr}. Ensure backend is running and includes{" "}
        <code className="text-amber-100">/api/dev/endpoints</code>.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-4 space-y-4">
      <div className="flex items-start gap-2">
        <Terminal className="h-4 w-4 text-slate-400 mt-0.5 shrink-0" />
        <div>
          <p className="text-sm font-semibold text-slate-300">API endpoints (ad-hoc runner)</p>
          <p className="text-xs text-slate-500 mt-0.5">
            {catalog.length} routes · Run executes in-browser · POST/DELETE may change data (confirm shown)
          </p>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 items-center">
        <input
          type="search"
          placeholder="Search path or description…"
          value={search}
          onChange={(ev) => setSearch(ev.target.value)}
          className="flex-1 min-w-[12rem] rounded border border-slate-600 bg-slate-900 px-2.5 py-1.5 text-sm text-slate-200 placeholder:text-slate-500"
        />
        <select
          value={groupFilter}
          onChange={(ev) => setGroupFilter(ev.target.value)}
          className="rounded border border-slate-600 bg-slate-900 px-2 py-1.5 text-sm text-slate-200"
        >
          <option value="All">All groups</option>
          {groups.map((g) => (
            <option key={g} value={g}>
              {g}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-2 max-h-[32rem] overflow-y-auto pr-1">
        {filtered.map((e, i) => {
          const id = entryId(e, i);
          const result = results[id];
          const pathParams = e.path_params ?? {};
          const queryParams = e.query ?? {};
          const hasParams = Object.keys(pathParams).length > 0 || Object.keys(queryParams).length > 0;

          return (
            <div key={id} className="rounded-lg border border-slate-700/80 bg-slate-900/50 overflow-hidden">
              <div className="flex flex-wrap items-start gap-2 p-2.5">
                <span className={clsx("text-[10px] font-bold px-1.5 py-0.5 rounded border shrink-0", methodColor(e.method))}>
                  {e.method}
                </span>
                <div className="flex-1 min-w-0">
                  <code className="text-xs text-emerald-300/90 break-all">{buildUrl(e, getPathParams(e, id), getQuery(e, id))}</code>
                  <p className="text-xs text-slate-500 mt-0.5">{e.description}</p>
                  {e.confirm && (
                    <span className="inline-flex items-center gap-1 text-[10px] text-amber-400 mt-1">
                      <AlertTriangle className="h-3 w-3" /> mutates data
                    </span>
                  )}
                </div>
                <div className="flex gap-1 shrink-0">
                  <button
                    type="button"
                    title="Copy URL"
                    onClick={() => copyUrl(e, id)}
                    className="p-1.5 rounded border border-slate-600 text-slate-400 hover:bg-slate-800"
                  >
                    {copiedId === id ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                  </button>
                  <a
                    href={fullHref(e, id)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-1.5 rounded border border-slate-600 text-slate-400 hover:bg-slate-800"
                    title="Open in new tab"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                  <button
                    type="button"
                    disabled={runningId === id}
                    onClick={() => runEndpoint(e, id)}
                    className="flex items-center gap-1 px-2 py-1 rounded text-xs font-medium bg-emerald-600/80 text-white hover:bg-emerald-500 disabled:opacity-50"
                  >
                    <Play className="h-3 w-3" />
                    {e.external ? "Open" : runningId === id ? "…" : "Run"}
                  </button>
                </div>
              </div>

              {hasParams && (
                <div className="px-2.5 pb-2 flex flex-wrap gap-3 border-t border-slate-800/80 pt-2">
                  {Object.keys(pathParams).map((key) => (
                    <label key={key} className="text-[10px] text-slate-500">
                      {key}
                      <input
                        className="block mt-0.5 w-20 rounded bg-slate-800 border border-slate-600 px-1.5 py-0.5 text-xs text-slate-200 font-mono"
                        value={getPathParams(e, id)[key] ?? ""}
                        onChange={(ev) =>
                          setPathEdits((prev) => ({
                            ...prev,
                            [id]: { ...(prev[id] ?? {}), [key]: ev.target.value },
                          }))
                        }
                      />
                    </label>
                  ))}
                  {Object.entries(getQuery(e, id)).map(([key, val]) => (
                    <label key={key} className="text-[10px] text-slate-500">
                      ?{key}
                      <input
                        className="block mt-0.5 min-w-[5rem] rounded bg-slate-800 border border-slate-600 px-1.5 py-0.5 text-xs text-slate-200 font-mono"
                        value={val}
                        onChange={(ev) =>
                          setQueryEdits((prev) => ({
                            ...prev,
                            [id]: { ...(prev[id] ?? {}), [key]: ev.target.value },
                          }))
                        }
                      />
                    </label>
                  ))}
                </div>
              )}

              {expandedId === id && result && (
                <div className="border-t border-slate-800 bg-slate-950/80 px-2.5 py-2">
                  <div className="flex gap-3 text-[10px] mb-1">
                    <span className={result.ok ? "text-emerald-400" : "text-red-400"}>HTTP {result.status || "ERR"}</span>
                    <span className="text-slate-500">{result.ms} ms</span>
                  </div>
                  <pre className="text-[10px] text-slate-400 overflow-x-auto max-h-48 whitespace-pre-wrap font-mono">{result.preview}</pre>
                </div>
              )}
            </div>
          );
        })}
        {filtered.length === 0 && <p className="text-sm text-slate-500 text-center py-4">No endpoints match filter.</p>}
      </div>
    </div>
  );
}
