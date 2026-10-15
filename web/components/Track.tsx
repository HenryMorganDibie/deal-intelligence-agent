"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

/** Counts a page view for the owner's usage page: an anonymous id kept in this browser, the path, nothing
 * else. Browsers that opened /admin are the owner's and are never counted. */
export function Track() {
  const path = usePathname();
  useEffect(() => {
    const api = process.env.NEXT_PUBLIC_API_URL?.trim().replace(/\/$/, "");
    if (!api || !path || path.startsWith("/admin")) return;
    try {
      if (localStorage.getItem("di_owner")) return;
      let v = localStorage.getItem("di_v");
      if (!v) {
        v = (crypto.randomUUID?.() ?? `${Date.now()}${Math.random()}`).replace(/[^a-z0-9]/gi, "").toLowerCase().slice(0, 32);
        localStorage.setItem("di_v", v);
      }
      navigator.sendBeacon?.(`${api}/api/track`, new Blob([JSON.stringify({ v, p: path })], { type: "text/plain" }));
    } catch {
      /* storage blocked: not counted */
    }
  }, [path]);
  return null;
}
