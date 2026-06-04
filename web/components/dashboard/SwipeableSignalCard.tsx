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
  surfaceClassName,
  disabled = false,
}: {
  children: React.ReactNode;
  actions: SwipeRevealAction[];
  /** Unique id — only one card stays open at a time when managed by parent. */
  cardKey: string;
  activeSwipeKey?: string | null;
  onSwipeKeyChange?: (key: string | null) => void;
  className?: string;
  /** Background/styling for the sliding foreground panel (must be opaque). */
  surfaceClassName?: string;
  /** When true, swipe is off and panel stays flush (e.g. gate detail expanded). */
  disabled?: boolean;
}) {
  const revealWidth = Math.max(actions.length * ACTION_WIDTH, ACTION_WIDTH);
  const [offset, setOffset] = useState(0);
  const [dragging, setDragging] = useState(false);
  const startX = useRef(0);
  const startOffset = useRef(0);
  const tracking = useRef(false);
  const offsetRef = useRef(0);

  const isOpen = !disabled && activeSwipeKey === cardKey;
  const revealActions = !disabled && Math.abs(offset) > 6;

  useEffect(() => {
    offsetRef.current = offset;
  }, [offset]);

  useEffect(() => {
    if (disabled) {
      setOffset(0);
      setDragging(false);
      tracking.current = false;
      if (activeSwipeKey === cardKey) onSwipeKeyChange?.(null);
      return;
    }
    if (!isOpen && !dragging) setOffset(0);
  }, [disabled, isOpen, dragging, activeSwipeKey, cardKey, onSwipeKeyChange]);

  useEffect(() => {
    if (isOpen && !dragging) setOffset(-revealWidth);
  }, [isOpen, dragging, revealWidth]);

  const close = useCallback(() => {
    onSwipeKeyChange?.(null);
    setOffset(0);
  }, [onSwipeKeyChange]);

  const open = useCallback(() => {
    if (disabled) return;
    onSwipeKeyChange?.(cardKey);
    setOffset(-revealWidth);
  }, [cardKey, disabled, onSwipeKeyChange, revealWidth]);

  const onTouchStart = (e: React.TouchEvent) => {
    if (disabled || actions.length === 0) return;
    startX.current = e.touches[0].clientX;
    startOffset.current = isOpen ? -revealWidth : offset;
    tracking.current = true;
    setDragging(true);
  };

  const onTouchMove = (e: React.TouchEvent) => {
    if (disabled || !tracking.current) return;
    const dx = e.touches[0].clientX - startX.current;
    const next = Math.min(0, Math.max(-revealWidth, startOffset.current + dx));
    setOffset(next);
    if (Math.abs(dx) > 8) e.preventDefault();
  };

  const onTouchEnd = () => {
    if (disabled || !tracking.current) return;
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
        className={clsx(
          "absolute inset-y-0 right-0 z-0 flex transition-opacity duration-150",
          revealActions ? "opacity-100" : "opacity-0 pointer-events-none",
        )}
        aria-hidden={!revealActions}
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
          "relative z-10 bg-slate-900",
          surfaceClassName,
          !dragging && !disabled && "transition-transform duration-200 ease-out",
        )}
        style={{ transform: disabled ? undefined : `translateX(${offset}px)` }}
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
