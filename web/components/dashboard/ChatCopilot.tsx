"use client";

import { useState, useRef, useEffect } from "react";
import { MessageCircle, X, Send, Loader2 } from "lucide-react";
import type { DashboardData } from "@/app/page";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002";

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: string[];
}

interface Props {
  /** Current dashboard data - passed as context for fresher answers */
  data: DashboardData | null;
}

export function ChatCopilot({ data }: Props) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async () => {
    const q = input.trim();
    if (!q || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: q }]);
    setLoading(true);
    try {
      const context = data
        ? {
            signals: data.signals,
            portfolio: data.portfolio,
            what_changed: data.what_changed,
            opportunities: data.opportunities,
            config: data.config,
          }
        : undefined;
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, context }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: json.answer || "No response.",
          sources: json.sources,
        },
      ]);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to get answer";
      setMessages((m) => [...m, { role: "assistant", content: `Error: ${msg}` }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <>
      {/* Floating button */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-600 text-white shadow-lg hover:bg-emerald-500 transition"
        title="Ask about your model"
      >
        <MessageCircle className="h-6 w-6" />
      </button>

      {/* Panel */}
      {open && (
        <div className="fixed bottom-24 right-6 z-50 w-[420px] max-w-[calc(100vw-3rem)] rounded-xl border border-slate-700 bg-slate-900 shadow-2xl flex flex-col overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700 bg-slate-800/80">
            <h3 className="font-semibold text-slate-100">Model Copilot</h3>
            <button
              onClick={() => setOpen(false)}
              className="p-1 text-slate-400 hover:text-slate-200 rounded"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto min-h-[200px] max-h-[360px] p-4 space-y-3">
            {messages.length === 0 && (
              <p className="text-slate-400 text-sm">
                Ask about your signals, portfolio, or what changed. Example: &quot;Why is MSFT showing BUY?&quot;
              </p>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                className={m.role === "user" ? "text-right" : "text-left"}
              >
                <div
                  className={
                    m.role === "user"
                      ? "inline-block px-3 py-2 rounded-lg bg-emerald-600/80 text-slate-100 text-sm max-w-[90%]"
                      : "inline-block px-3 py-2 rounded-lg bg-slate-700 text-slate-200 text-sm max-w-[90%]"
                  }
                >
                  {m.content}
                  {m.sources && m.sources.length > 0 && (
                    <p className="mt-1 text-xs text-slate-500">
                      Based on: {m.sources.join(", ")}
                    </p>
                  )}
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex items-center gap-2 text-slate-400 text-sm">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Thinking...</span>
              </div>
            )}
            <div ref={scrollRef} />
          </div>

          <div className="p-3 border-t border-slate-700">
            <div className="flex gap-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about your model..."
                className="flex-1 px-3 py-2 rounded-lg bg-slate-800 border border-slate-600 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 text-sm"
                disabled={loading}
              />
              <button
                onClick={send}
                disabled={loading || !input.trim()}
                className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white"
              >
                <Send className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
