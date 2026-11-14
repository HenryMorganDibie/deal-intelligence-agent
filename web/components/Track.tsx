"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { recordedPath, trackPageView } from "../lib/tracking";

/** Counts page views and excludes browsers marked as the owner's. */
export function Track() {
  const path = usePathname();
  useEffect(() => {
    if (!path || path.startsWith("/admin") || path.startsWith("/review")) return;
    trackPageView(recordedPath(path));
  }, [path]);
  return null;
}
