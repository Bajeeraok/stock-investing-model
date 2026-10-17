"use client";

import { clsx } from "clsx";
import { Rows3, LayoutGrid } from "lucide-react";
import { createContext, useContext, useState, useEffect, type ReactNode } from "react";

type Density = "compact" | "comfort";

const LS_KEY = "thrive_levels_density";

function readLS(): Density {
  if (typeof window === "undefined") return "comfort";
  try {
    const v = window.localStorage.getItem(LS_KEY);
    return v === "compact" || v === "comfort" ? v : "comfort";
  } catch {
    return "comfort";
  }
}

function writeLS(d: Density) {
  try { window.localStorage.setItem(LS_KEY, d); } catch { /* ignore */ }
}

const DensityCtx = createContext<{ density: Density; toggle: () => void }>({
  density: "comfort",
  toggle: () => {},
});

export function DensityProvider({ children }: { children: ReactNode }) {
  const [density, setDensity] = useState<Density>("comfort");

  // Hydrate from localStorage after mount (avoids SSR mismatch)
  useEffect(() => {
    setDensity(readLS());
  }, []);

  const toggle = () =>
    setDensity(prev => {
      const next = prev === "comfort" ? "compact" : "comfort";
      writeLS(next);
      return next;
    });

  return <DensityCtx.Provider value={{ density, toggle }}>{children}</DensityCtx.Provider>;
}

export function useDensity() {
  return useContext(DensityCtx);
}

export function DensityToggle({ className }: { className?: string }) {
  const { density, toggle } = useDensity();
  return (
    <button
      type="button"
      onClick={toggle}
      title={density === "comfort" ? "Switch to Compact" : "Switch to Comfort"}
      className={clsx(
        "flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-[10px] font-semibold uppercase tracking-wider transition-all",
        density === "comfort"
          ? "border-td-line text-td-muted hover:border-td-line hover:text-td-text"
          : "border-td-accent/40 bg-td-accent/10 text-td-accent hover:border-td-accent/60",
        className,
      )}
    >
      {density === "comfort" ? (
        <><Rows3 className="h-3 w-3" /><span>Compact</span></>
      ) : (
        <><LayoutGrid className="h-3 w-3" /><span>Comfort</span></>
      )}
    </button>
  );
}

/** Convenience: show/hide decorative or spacious elements based on density */
export function Comfort({ children, className }: { children: ReactNode; className?: string }) {
  const { density } = useDensity();
  if (density === "compact") return null;
  return <div className={className}>{children}</div>;
}
