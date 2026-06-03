"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { clsx } from "clsx";

export type SwipeRevealAction = {
  id: string;
  label: string;
  onClick: () => void;
  tone?: "emerald" | "sky" | "amber";
};

const TONE_CLASS: Record<NonNullable<SwipeRevealAction["tone"]>, string> = {
  emerald: "bg-emerald-600 hover:bg-emerald-500 text-white",
  sky: "bg-sky-600 hover:bg-sky-500 text-white",
  amber: "bg-amber-600 hover:bg-amber-500 text-white",
};

const ACTION_WIDTH = 76;
const SNAP_THRESHOLD = 48;

export function SwipeableSignalCard({
  children,
  actions,
  cardKey,
  activeSwipeKey,
  onSwipeKeyChange,
  className,
}: {
  children: React.ReactNode;
  actions: SwipeRevealAction[];
  /** Unique id — only one card stays open at a time when managed by parent. */
  cardKey: string;
  activeSwipeKey?: string | null;
  onSwipeKeyChange?: (key: string | null) => void;
  className?: string;
}) {
  const revealWidth = Math.max(actions.length * ACTION_WIDTH, ACTION_WIDTH);
  const [offset, setOffset] = useState(0);
  const [dragging, setDragging] = useState(false);
  const startX = useRef(0);
  const startOffset = useRef(0);
  const tracking = useRef(false);
  const offsetRef = useRef(0);

  const isOpen = activeSwipeKey === cardKey;

  useEffect(() => {
    offsetRef.current = offset;
  }, [offset]);

  useEffect(() => {
    if (!isOpen && !dragging) setOffset(0);
  }, [isOpen, dragging]);

  useEffect(() => {
    if (isOpen && !dragging) setOffset(-revealWidth);
  }, [isOpen, dragging, revealWidth]);

  const close = useCallback(() => {
    onSwipeKeyChange?.(null);
    setOffset(0);
  }, [onSwipeKeyChange]);

  const open = useCallback(() => {
    onSwipeKeyChange?.(cardKey);
    setOffset(-revealWidth);
  }, [cardKey, onSwipeKeyChange, revealWidth]);

  const onTouchStart = (e: React.TouchEvent) => {
    if (actions.length === 0) return;
    startX.current = e.touches[0].clientX;
    startOffset.current = isOpen ? -revealWidth : offset;
    tracking.current = true;
    setDragging(true);
  };

  const onTouchMove = (e: React.TouchEvent) => {
    if (!tracking.current) return;
    const dx = e.touches[0].clientX - startX.current;
    const next = Math.min(0, Math.max(-revealWidth, startOffset.current + dx));
    setOffset(next);
    if (Math.abs(dx) > 8) e.preventDefault();
  };

  const onTouchEnd = () => {
    if (!tracking.current) return;
    tracking.current = false;
    setDragging(false);
    if (offsetRef.current <= -SNAP_THRESHOLD) open();
    else close();
  };

  const runAction = (action: SwipeRevealAction) => {
    action.onClick();
    close();
  };

  return (
    <div className={clsx("relative overflow-hidden touch-pan-y", className)}>
      <div
        className="absolute inset-y-0 right-0 flex"
        aria-hidden={!isOpen && offset === 0}
      >
        {actions.map((action) => (
          <button
            key={action.id}
            type="button"
            onClick={() => runAction(action)}
            className={clsx(
              "flex flex-col items-center justify-center px-3 text-xs font-semibold uppercase tracking-wide min-w-[76px] touch-manipulation",
              TONE_CLASS[action.tone ?? "emerald"],
            )}
          >
            {action.label}
          </button>
        ))}
      </div>

      <div
        className={clsx(
          "relative",
          className,
          !dragging && "transition-transform duration-200 ease-out",
        )}
        style={{ transform: `translateX(${offset}px)` }}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        onTouchCancel={onTouchEnd}
      >
        {children}
      </div>
    </div>
  );
}
