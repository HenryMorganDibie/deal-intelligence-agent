"use client";

import { useEffect, useState } from "react";
import { apiUrl } from "../lib/api-base";

type Announcement = { on?: boolean; text?: string; link?: string | null; tone?: "info" | "warning" };

/** The owner's announcement, set in admin, shown at the foot of every page until the reader dismisses it. */
export function SiteBanner() {
  const [a, setA] = useState<Announcement | null>(null);
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    let live = true;
    fetch(apiUrl("/api/site-settings"))
      .then((r) => (r.ok ? r.json() : null))
      .then((data: { announcement?: Announcement } | null) => {
        if (!live || !data?.announcement?.on || !data.announcement.text) return;
        try {
          if (window.localStorage.getItem("di-banner-dismissed") === data.announcement.text) return;
        } catch {
          // Storage can be blocked; the banner then shows each visit.
        }
        setA(data.announcement);
      })
      .catch(() => undefined);
    return () => { live = false; };
  }, []);

  if (!a || hidden) return null;
  const warning = a.tone === "warning";
  return (
    <div role="status" className="fixed inset-x-0 bottom-0 z-40 flex justify-center px-4 pb-4">
      <div className={`flex max-w-3xl items-start gap-3 rounded-xl border px-4 py-3 text-sm shadow-2xl backdrop-blur ${
        warning ? "border-risk/40 bg-[color:var(--bg)]/95" : "hairline bg-[color:var(--bg)]/95"}`}>
        <p className="leading-relaxed">
          {a.text}
          {a.link && <> <a href={a.link} className="font-medium underline underline-offset-2">Learn more</a></>}
        </p>
        <button type="button" aria-label="Dismiss announcement" className="shrink-0 text-[color:var(--muted)] hover:text-[color:var(--text)]"
          onClick={() => {
            setHidden(true);
            try { window.localStorage.setItem("di-banner-dismissed", a.text ?? ""); } catch { /* not stored */ }
          }}>
          ✕
        </button>
      </div>
    </div>
  );
}
