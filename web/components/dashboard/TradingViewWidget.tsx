"use client";

import { useEffect, useRef, useId } from "react";

declare global {
  interface Window {
    TradingView?: {
      widget: (opts: Record<string, unknown>) => void;
    };
  }
}

const SCRIPT_ID = "tradingview-widget-script";

function loadTradingViewScript(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (window.TradingView) return Promise.resolve();
  const existing = document.getElementById(SCRIPT_ID);
  if (existing) {
    return new Promise((resolve) => {
      existing.addEventListener("load", () => resolve(), { once: true });
      if (window.TradingView) resolve();
    });
  }
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.id = SCRIPT_ID;
    script.src = "https://s3.tradingview.com/tv.js";
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("TradingView script failed"));
    document.head.appendChild(script);
  });
}

/** Phase E1 — embed TradingView chart on ticker Today tab (free widget). */
export function TradingViewWidget({ ticker, height = 360 }: { ticker: string; height?: number }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const uid = useId().replace(/:/g, "");
  const containerId = `tv_${ticker}_${uid}`;

  useEffect(() => {
    let cancelled = false;
    const sym = ticker.toUpperCase().replace(/[^A-Z0-9.]/g, "");

    loadTradingViewScript()
      .then(() => {
        if (cancelled || !containerRef.current || !window.TradingView) return;
        containerRef.current.innerHTML = "";
        window.TradingView.widget({
          autosize: true,
          symbol: sym,
          interval: "D",
          timezone: "America/New_York",
          theme: "dark",
          style: "1",
          locale: "en",
          toolbar_bg: "#0f172a",
          enable_publishing: false,
          hide_top_toolbar: false,
          hide_legend: false,
          container_id: containerId,
          studies: ["MASimple@tv-basicstudies"],
        });
      })
      .catch(() => {
        /* silent — optional widget */
      });

    return () => {
      cancelled = true;
    };
  }, [ticker, containerId]);

  return (
    <div className="rounded-lg border border-slate-600/80 bg-slate-900/50 overflow-hidden">
      <p className="text-[10px] uppercase tracking-wider text-slate-500 px-3 pt-2">
        Chart · TradingView (delayed)
      </p>
      <div id={containerId} ref={containerRef} style={{ height }} className="w-full" />
    </div>
  );
}
