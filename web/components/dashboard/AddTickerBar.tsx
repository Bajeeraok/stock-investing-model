"use client";

import { useState } from "react";
import { Plus, Upload } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

export function AddTickerBar({ onAdded }: { onAdded?: () => void }) {
  const [ticker, setTicker] = useState("");
  const [journalNote, setJournalNote] = useState("");
  const [showJournal, setShowJournal] = useState(false);
  const [thesisOverride, setThesisOverride] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadName, setUploadName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [cooldownMsg, setCooldownMsg] = useState<string | null>(null);

  const addTicker = async () => {
    const t = ticker.trim().toUpperCase();
    if (!t) return;
    setError(null);
    setCooldownMsg(null);
    try {
      const url = API_BASE ? `${API_BASE}/api/tickers` : "/api/tickers";
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker: t,
          journal_note: journalNote.trim() || undefined,
          thesis_override: thesisOverride,
        }),
      });
      const json = await res.json();
      if (res.status === 409 && json.detail) {
        const detail = typeof json.detail === "object" ? json.detail : { message: String(json.detail) };
        setCooldownMsg(detail.message || "On trim cooldown — log a thesis update to re-add.");
        setShowJournal(true);
        return;
      }
      if (json.ok) {
        setTicker("");
        setJournalNote("");
        setThesisOverride(false);
        setShowJournal(false);
        onAdded?.();
      } else {
        setError(json.message || json.detail || "Could not add");
      }
    } catch {
      setError("Failed to add ticker");
    }
  };

  const uploadPortfolio = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      const url = API_BASE ? `${API_BASE}/api/portfolio/upload` : "/api/portfolio/upload";
      const form = new FormData();
      form.append("file", file);
      form.append("portfolio_name", uploadName || "Uploaded");
      const res = await fetch(url, { method: "POST", body: form });
      const json = await res.json();
      if (json.ok) {
        setUploadName("");
        e.target.value = "";
        onAdded?.();
      } else {
        setError(json.detail || json.message || "Upload failed");
      }
    } catch {
      setError("Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-3 py-2 px-4 rounded-lg bg-slate-800/50 border border-slate-700">
        <span className="text-sm text-slate-400">Add ticker:</span>
        <input
          type="text"
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          onKeyDown={(e) => e.key === "Enter" && addTicker()}
          placeholder="e.g. AAPL"
          className="px-3 py-1.5 rounded bg-slate-900 border border-slate-600 text-slate-200 text-sm w-24 font-mono uppercase"
          maxLength={10}
        />
        <button
          type="button"
          onClick={() => {
            if (!showJournal && !journalNote) setShowJournal(true);
            else void addTicker();
          }}
          disabled={!ticker.trim()}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium disabled:opacity-50"
        >
          <Plus className="h-4 w-4" />
          Add
        </button>
        <span className="text-slate-600">|</span>
        <span className="text-sm text-slate-400">Upload portfolio:</span>
        <input
          type="text"
          value={uploadName}
          onChange={(e) => setUploadName(e.target.value)}
          placeholder="Portfolio name"
          className="px-3 py-1.5 rounded bg-slate-900 border border-slate-600 text-slate-200 text-sm w-32"
        />
        <label className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-slate-700 hover:bg-slate-600 text-slate-200 text-sm cursor-pointer">
          <Upload className="h-4 w-4" />
          {uploading ? "Uploading..." : "Excel"}
          <input type="file" accept=".xlsx,.xls" onChange={uploadPortfolio} disabled={uploading} className="hidden" />
        </label>
      </div>
      {(showJournal || journalNote) && (
        <div className="px-4 py-3 rounded-lg border border-slate-700 bg-slate-900/60 space-y-2">
          <label className="block text-xs text-slate-400">One-line journal (optional — why add now?)</label>
          <input
            type="text"
            value={journalNote}
            onChange={(e) => setJournalNote(e.target.value)}
            placeholder="e.g. Pullback to MA50; thesis intact"
            className="w-full px-3 py-2 rounded bg-slate-950 border border-slate-600 text-slate-200 text-sm"
            maxLength={500}
          />
          {cooldownMsg && (
            <label className="flex items-start gap-2 text-xs text-amber-200/90 cursor-pointer">
              <input
                type="checkbox"
                checked={thesisOverride}
                onChange={(e) => setThesisOverride(e.target.checked)}
                className="mt-0.5"
              />
              <span>
                {cooldownMsg} Check here if your thesis changed and you still want to re-add.
              </span>
            </label>
          )}
          <button
            type="button"
            onClick={() => void addTicker()}
            disabled={!ticker.trim() || (Boolean(cooldownMsg) && !thesisOverride)}
            className="text-sm px-3 py-1.5 rounded bg-emerald-600/90 hover:bg-emerald-500 text-white disabled:opacity-50"
          >
            Confirm add
          </button>
        </div>
      )}
      {error && <p className="text-red-400 text-sm px-4">{error}</p>}
    </div>
  );
}
