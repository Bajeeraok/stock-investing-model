"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Bell, BellOff, Loader2 } from "lucide-react";

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

/** VAPID key as a dedicated `ArrayBuffer` for `subscribe()` typings. */
function urlBase64ToApplicationServerKey(base64String: string): ArrayBuffer {
  const u8 = urlBase64ToUint8Array(base64String);
  const out = new ArrayBuffer(u8.byteLength);
  new Uint8Array(out).set(u8);
  return out;
}

export default function BrowserPushPanel() {
  const [supported, setSupported] = useState<boolean | null>(null);
  const [enabledOnServer, setEnabledOnServer] = useState(false);
  const [publicKey, setPublicKey] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [subscribed, setSubscribed] = useState(false);

  useEffect(() => {
    const ok = typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window;
    setSupported(ok);
    if (!ok) return;
    fetch("/api/push/public-config", { cache: "no-store" })
      .then((r) => r.json())
      .then((j: { enabled?: boolean; publicKey?: string | null }) => {
        setEnabledOnServer(!!j.enabled);
        setPublicKey(j.publicKey ?? null);
      })
      .catch(() => setEnabledOnServer(false));
  }, []);

  useEffect(() => {
    if (!supported) return;
    navigator.serviceWorker.getRegistration("/").then(async (reg) => {
      if (!reg) {
        setSubscribed(false);
        return;
      }
      const sub = await reg.pushManager.getSubscription();
      setSubscribed(!!sub);
    });
  }, [supported]);

  const registerAndSubscribe = useCallback(async () => {
    if (!supported || !publicKey) return;
    setBusy(true);
    setStatus("");
    try {
      const reg = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
      await navigator.serviceWorker.ready;
      const perm = await Notification.requestPermission();
      if (perm !== "granted") {
        setStatus("Notifications blocked — enable in browser site settings.");
        setBusy(false);
        return;
      }
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToApplicationServerKey(publicKey),
      });
      const res = await fetch("/api/push/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subscription: sub.toJSON() }),
      });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(t || `HTTP ${res.status}`);
      }
      setSubscribed(true);
      setStatus("Subscribed — you can receive pushes when the server sends them (e.g. test from ops).");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Subscribe failed");
    } finally {
      setBusy(false);
    }
  }, [publicKey, supported]);

  const unsubscribe = useCallback(async () => {
    setBusy(true);
    setStatus("");
    try {
      const reg = await navigator.serviceWorker.getRegistration("/");
      const sub = await reg?.pushManager.getSubscription();
      if (sub) {
        const ep = sub.endpoint;
        await fetch("/api/push/unsubscribe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ endpoint: ep }),
        });
        await sub.unsubscribe();
      }
      setSubscribed(false);
      setStatus("Unsubscribed.");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Unsubscribe failed");
    } finally {
      setBusy(false);
    }
  }, []);

  if (supported === false) {
    return (
      <div className="rounded-lg border border-slate-700 bg-slate-800/40 p-4 text-sm text-slate-400">
        Web Push is not supported in this browser.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800/40 p-4 space-y-3">
      <div className="flex items-start gap-2">
        <Bell className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
        <div>
          <p className="text-sm font-medium text-slate-200">Browser push (Stage 2)</p>
          <p className="text-xs text-slate-500 mt-1 leading-relaxed">
            Subscribe this device for background notifications. Requires{" "}
            <code className="text-slate-400">VAPID_PUBLIC_KEY</code> / <code className="text-slate-400">VAPID_PRIVATE_KEY</code>{" "}
            on the API (see <code className="text-slate-400">backend/env.example</code>). Email/Telegram digests remain unchanged.
          </p>
        </div>
      </div>

      {!enabledOnServer && (
        <p className="text-xs text-amber-400/90">
          Server has no VAPID public key — set env vars and redeploy to enable subscribe.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={!enabledOnServer || busy || subscribed}
          onClick={registerAndSubscribe}
          className="inline-flex items-center gap-2 rounded-lg bg-emerald-600/80 hover:bg-emerald-500 disabled:opacity-40 disabled:pointer-events-none px-3 py-2 text-xs font-semibold text-white"
        >
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Bell className="w-4 h-4" />}
          Enable on this device
        </button>
        <button
          type="button"
          disabled={busy || !subscribed}
          onClick={unsubscribe}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-xs font-medium text-slate-300 hover:bg-slate-700/80 disabled:opacity-40"
        >
          <BellOff className="w-4 h-4" />
          Disable
        </button>
      </div>

      {status && <p className="text-xs text-slate-400">{status}</p>}
      <p className="text-[10px] text-slate-600">
        Ops test (optional): POST <code className="text-slate-500">/api/push/test</code> with header{" "}
        <code className="text-slate-500">X-Push-Admin-Secret</code> when <code className="text-slate-500">WEB_PUSH_ADMIN_SECRET</code> is set.
      </p>
    </div>
  );
}
