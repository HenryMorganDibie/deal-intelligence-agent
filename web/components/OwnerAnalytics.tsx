"use client";

import { Analytics, type BeforeSend } from "@vercel/analytics/next";

const beforeSend: BeforeSend = (event) => {
  try {
    const path = new URL(event.url, window.location.origin).pathname;
    if (path.startsWith("/admin") || window.localStorage.getItem("di_owner")) return null;
  } catch {
    return event;
  }
  return event;
};

export function OwnerAnalytics() {
  return <Analytics beforeSend={beforeSend} />;
}
