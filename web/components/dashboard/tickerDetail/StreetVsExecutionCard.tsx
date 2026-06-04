"use client";

export function StreetVsExecutionCard({ text }: { text: string | null | undefined }) {
  if (!text?.trim()) return null;

  return (
    <div className="rounded-2xl border border-amber-700/30 bg-amber-900/10 p-4">
      <p className="text-[10px] font-mono uppercase tracking-widest text-amber-400/90 mb-2">
        Street vs execution
      </p>
      <p className="text-xs text-slate-300 leading-relaxed">{text.trim()}</p>
    </div>
  );
}
