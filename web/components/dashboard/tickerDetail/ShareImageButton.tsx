"use client";

import { useState, type RefObject } from "react";
import { ImageDown } from "lucide-react";

/** Saves the referenced element as a PNG; on phones opens the share sheet (WhatsApp etc.). */
export function ShareImageButton({ target, fileName }: { target: RefObject<HTMLElement>; fileName: string }) {
  const [busy, setBusy] = useState(false);

  const handle = async () => {
    const node = target.current;
    if (!node || busy) return;
    setBusy(true);
    try {
      const { toBlob } = await import("html-to-image");
      const bg = getComputedStyle(document.documentElement).getPropertyValue("--td-bg").trim();
      const blob = await toBlob(node, {
        pixelRatio: 2,
        backgroundColor: bg ? `rgb(${bg})` : "#0b0f14",
        filter: (el) => !(el instanceof HTMLElement && el.dataset.noCapture === "1"),
      });
      if (!blob) return;
      const file = new File([blob], `${fileName}.png`, { type: "image/png" });
      if (navigator.canShare?.({ files: [file] })) {
        await navigator.share({ files: [file], title: fileName }).catch(() => undefined);
      } else {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = file.name;
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 1000);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      type="button"
      onClick={handle}
      disabled={busy}
      data-no-capture="1"
      className="inline-flex items-center gap-1 rounded-md border border-td-line px-2 py-0.5 text-[12px] text-td-muted hover:text-td-text disabled:opacity-50"
      title="Save this card as an image"
    >
      <ImageDown className="h-3.5 w-3.5" aria-hidden />
      {busy ? "Saving…" : "Share image"}
    </button>
  );
}
