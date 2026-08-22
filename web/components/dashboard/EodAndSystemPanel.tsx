"use client";

/**
 * EOD snapshots list, Redis status, and upload.
 * File list loads live from GET /api/eod/snapshots so Force refresh / dashboard
 * cache cannot leave this panel stuck on an old max date (e.g. Aug 2).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Database, RefreshCw, CheckCircle, XCircle, AlertCircle } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

export interface EodSnapshotItem {
  date: string;
  size_bytes: number;
  run_date?: string | null;
  tickers_count?: number;
  universe?: string | null;
  source?: string | null;
}

export interface RedisStatus {
  configured: boolean;
  connected: boolean;
  source?: string | null;
  scheme?: string | null;
  error?: string | null;
}

interface EodAndSystemPanelProps {
  /** Fallback while live fetch loads (may be stale from dashboard cache). */
  eodSnapshots: EodSnapshotItem[];
  redisStatus: RedisStatus | undefined;
  dataRoot?: string | null;
  onRefresh?: () => void;
}

function formatBytes(n: number): string {
  if (!n) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function formatRunDateEt(runDate: string | null | undefined): string {
  if (!runDate) return "";
  const d = new Date(runDate);
  if (Number.isNaN(d.getTime())) return String(runDate).slice(0, 19);
  return (
    d.toLocaleString("en-US", {
      timeZone: "America/New_York",
      dateStyle: "short",
      timeStyle: "short",
    }) + " EST"
  );
}

function preferNewerList(a: EodSnapshotItem[], b: EodSnapshotItem[]): EodSnapshotItem[] {
  const aMax = a[0]?.date ?? "";
  const bMax = b[0]?.date ?? "";
  if (bMax > aMax) return b;
  if (aMax > bMax) return a;
  return b.length >= a.length ? b : a;
}

export function EodAndSystemPanel({
  eodSnapshots,
  redisStatus,
  dataRoot,
  onRefresh,
}: EodAndSystemPanelProps) {
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const [snapshotDateOverride, setSnapshotDateOverride] = useState("");
  const [liveSnapshots, setLiveSnapshots] = useState<EodSnapshotItem[] | null>(null);
  const [liveError, setLiveError] = useState<string | null>(null);
  const [liveLoading, setLiveLoading] = useState(false);
  const [liveLatest, setLiveLatest] = useState<string | null>(null);
  const [liveDataRoot, setLiveDataRoot] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchLiveList = useCallback(async () => {
    setLiveLoading(true);
    setLiveError(null);
    try {
      const url = API_BASE ? `${API_BASE}/api/eod/snapshots` : "/api/eod/snapshots";
      const res = await fetch(url, { cache: "no-store", headers: { Accept: "application/json" } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const snaps = Array.isArray(data?.snapshots) ? (data.snapshots as EodSnapshotItem[]) : [];
      setLiveSnapshots(snaps);
      setLiveLatest(typeof data?.latest_date === "string" ? data.latest_date : snaps[0]?.date ?? null);
      if (typeof data?.data_root === "string") setLiveDataRoot(data.data_root);
    } catch (err) {
      setLiveError(err instanceof Error ? err.message : "Failed to load EOD list");
    } finally {
      setLiveLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchLiveList();
  }, [fetchLiveList]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadError(null);
    setUploadSuccess(null);
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      if (snapshotDateOverride.trim()) {
        formData.append("snapshot_date", snapshotDateOverride.trim());
      }
      const url = API_BASE ? `${API_BASE}/api/eod/upload` : "/api/eod/upload";
      const res = await fetch(url, { method: "POST", body: formData });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(
          typeof data.detail === "string" ? data.detail : `HTTP ${res.status}`
        );
      }
      setUploadSuccess(
        `Saved as ${data.snapshot_date}.json (${data.tickers_count ?? 0} tickers).`
      );
      await fetchLiveList();
      onRefresh?.();
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const redis = redisStatus ?? { configured: false, connected: false };
  const displaySnapshots = liveSnapshots
    ? preferNewerList(eodSnapshots ?? [], liveSnapshots)
    : eodSnapshots ?? [];
  const rootLabel = liveDataRoot || dataRoot;

  return (
    <div className="rounded-lg border border-slate-600 bg-slate-800/30 p-4 space-y-4">
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-slate-400 shrink-0" />
          <span className="text-sm font-semibold text-slate-300">EOD snapshots &amp; system</span>
        </div>
        <button
          type="button"
          onClick={() => void fetchLiveList()}
          disabled={liveLoading}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded border border-slate-600 text-slate-400 hover:bg-slate-800 text-xs disabled:opacity-50"
        >
          <RefreshCw className={`h-3 w-3 ${liveLoading ? "animate-spin" : ""}`} />
          Refresh list
        </button>
      </div>

      {liveLatest && (
        <p className="text-xs text-emerald-400/90">
          Live latest: <span className="font-mono">{liveLatest}</span>
          {displaySnapshots.length ? ` · ${displaySnapshots.length} files` : ""}
        </p>
      )}
      {liveError && (
        <p className="text-xs text-amber-400">
          Live list failed ({liveError}) — showing dashboard cache
          {eodSnapshots?.[0]?.date ? ` (top: ${eodSnapshots[0].date})` : ""}.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <span className="text-xs text-slate-500 uppercase tracking-wider">Redis</span>
        {!redis.configured ? (
          <span className="inline-flex items-center gap-1.5 text-xs text-slate-500">
            <AlertCircle className="h-3.5 w-3.5" />
            Not configured (set REDIS_URL / REDIS_PRIVATE_URL)
          </span>
        ) : redis.connected ? (
          <span className="inline-flex items-center gap-1.5 text-xs text-emerald-400">
            <CheckCircle className="h-3.5 w-3.5" />
            Connected{redis.source ? ` (${redis.source})` : ""}
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 text-xs text-amber-400">
            <XCircle className="h-3.5 w-3.5" />
            <span title={redis.error ?? undefined}>
              Not connected
              {redis.source ? ` (${redis.source}${redis.scheme ? `, ${redis.scheme}` : ""})` : ""}
            </span>
          </span>
        )}
      </div>
      {!redis.connected && redis.error && (
        <p className="text-xs text-slate-500 -mt-2">
          <span className="text-slate-400">Redis error:</span> {redis.error}
        </p>
      )}

      <div>
        <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
          EOD snapshot files ({displaySnapshots.length})
        </p>
        <p className="text-xs text-slate-500 mb-2">
          Files under{" "}
          <code className="bg-slate-800 px-1 rounded">
            {rootLabel ? `${rootLabel.replace(/\/$/, "")}/eod/` : "DATA_ROOT/eod/"}
          </code>
          <span className="text-slate-400"> — live from /api/eod/snapshots</span>
        </p>
        {displaySnapshots.length === 0 ? (
          <p className="text-sm text-slate-500">
            {liveLoading ? "Loading EOD list…" : "No EOD snapshots yet. Run EOD or upload below."}
          </p>
        ) : (
          <ul className="text-sm space-y-1 max-h-48 overflow-y-auto">
            {displaySnapshots.map((s) => {
              const thin = (s.tickers_count ?? 0) > 0 && (s.tickers_count ?? 0) < 75;
              return (
                <li
                  key={s.date}
                  className="flex items-center justify-between gap-2 py-0.5 text-slate-300"
                >
                  <span className="font-mono flex items-center gap-2">
                    {s.date}.json
                    {(s.tickers_count ?? 0) > 0 && (
                      <span
                        className={`text-xs font-sans ${thin ? "text-amber-400" : "text-slate-500"}`}
                      >
                        {s.tickers_count} tickers{thin ? " (dashboard-only)" : ""}
                      </span>
                    )}
                  </span>
                  <span className="text-slate-500 text-xs">
                    {formatBytes(s.size_bytes ?? 0)}
                    {s.run_date ? ` · ${formatRunDateEt(s.run_date)}` : ""}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="border-t border-slate-700 pt-3">
        <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
          Upload EOD snapshot
        </p>
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label className="block text-xs text-slate-500 mb-1">File (JSON)</label>
            <input
              ref={fileInputRef}
              type="file"
              accept=".json"
              className="block w-full text-sm text-slate-400 file:mr-2 file:py-1.5 file:px-3 file:rounded file:border-0 file:bg-slate-700 file:text-slate-200 file:text-sm"
              onChange={handleUpload}
              disabled={uploading}
            />
          </div>
          <div className="min-w-[10rem]">
            <label className="block text-xs text-slate-500 mb-1">Date override (YYYY-MM-DD)</label>
            <input
              type="text"
              placeholder="Optional"
              className="w-full rounded border border-slate-600 bg-slate-800 px-2 py-1.5 text-sm text-slate-200 placeholder:text-slate-500"
              value={snapshotDateOverride}
              onChange={(e) => setSnapshotDateOverride(e.target.value)}
            />
          </div>
        </div>
        {uploading && <p className="text-xs text-slate-500 mt-1">Uploading…</p>}
        {uploadError && (
          <p className="text-xs text-amber-400 mt-1 flex items-center gap-1">
            <AlertCircle className="h-3 w-3 shrink-0" /> {uploadError}
          </p>
        )}
        {uploadSuccess && (
          <p className="text-xs text-emerald-400 mt-1 flex items-center gap-1">
            <CheckCircle className="h-3 w-3 shrink-0" /> {uploadSuccess}
          </p>
        )}
      </div>
    </div>
  );
}
