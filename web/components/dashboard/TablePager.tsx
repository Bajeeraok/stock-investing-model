"use client";

import { clsx } from "clsx";

interface TablePagerProps {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  className?: string;
}

export function TablePager({ page, pageSize, total, onPageChange, className }: TablePagerProps) {
  if (total <= pageSize) return null;

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(page, totalPages - 1);
  const start = safePage * pageSize + 1;
  const end = Math.min(total, (safePage + 1) * pageSize);

  return (
    <div className={clsx("flex flex-wrap items-center justify-between gap-2 mt-3 text-xs text-slate-400", className)}>
      <span className="tabular-nums">
        Rows {start}–{end} of {total}
      </span>
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          disabled={safePage <= 0}
          onClick={() => onPageChange(safePage - 1)}
          className="px-2.5 py-1.5 rounded border border-slate-600 bg-slate-900 text-slate-300 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-800 min-h-[36px] touch-manipulation"
        >
          Prev
        </button>
        <span className="px-1 tabular-nums text-slate-500">
          {safePage + 1} / {totalPages}
        </span>
        <button
          type="button"
          disabled={safePage >= totalPages - 1}
          onClick={() => onPageChange(safePage + 1)}
          className="px-2.5 py-1.5 rounded border border-slate-600 bg-slate-900 text-slate-300 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-800 min-h-[36px] touch-manipulation"
        >
          Next
        </button>
      </div>
    </div>
  );
}

export function paginateRows<T>(rows: T[], page: number, pageSize: number): T[] {
  const start = page * pageSize;
  return rows.slice(start, start + pageSize);
}
