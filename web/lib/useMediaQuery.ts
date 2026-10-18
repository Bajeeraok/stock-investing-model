"use client";

import { useEffect, useState } from "react";

/** SSR-safe matchMedia hook — returns `false` until mounted, then tracks the query. */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia(query);
    const sync = () => setMatches(mql.matches);
    sync();
    mql.addEventListener("change", sync);
    return () => mql.removeEventListener("change", sync);
  }, [query]);
  return matches;
}

/**
 * How ticker detail presents at the current width:
 *   page   (<768px)     full-screen page, bottom nav stays visible
 *   drawer (768–1279px) right-side drawer over the list
 *   pane   (≥1280px)    right pane of a list + detail split view
 */
export type TickerDetailLayout = "page" | "drawer" | "pane";

export function useTickerDetailLayout(): TickerDetailLayout {
  const isMobile = useMediaQuery("(max-width: 767px)");
  const isWide = useMediaQuery("(min-width: 1280px)");
  if (isMobile) return "page";
  if (isWide) return "pane";
  return "drawer";
}
