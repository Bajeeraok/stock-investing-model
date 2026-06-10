"use client";

import { clsx } from "clsx";
import { Rows3, LayoutGrid } from "lucide-react";
import { createContext, useContext, useState, type ReactNode } from "react";

type Density = "compact" | "comfort";

const DensityCtx = createContext<{ density: Density; toggle: () => void }>({
  density: "comfort",
  toggle: () => {},
});

export function DensityProvider({ children }: { children: ReactNode }) {
  const [density, setDensity] = useState<Density>("comfort");
  const toggle = () => setDensity(d => (d === "comfort" ? "compact" : "comfort"));
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
          ? "border-slate-600 text-slate-400 hover:border-slate-500 hover:text-slate-300"
          : "border-teal-500/40 bg-teal-500/10 text-teal-300 hover:border-teal-400/60",
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
