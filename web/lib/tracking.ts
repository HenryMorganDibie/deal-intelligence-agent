const API_URL = process.env.NEXT_PUBLIC_API_URL?.trim().replace(/\/$/, "") ?? "";

export type ProductAction =
  | "deals_loaded"
  | "investors_loaded"
  | "events_loaded"
  | "risk_data_loaded"
  | "company_data_loaded"
  | "watchlists_used"
  | "brief_opened"
  | "performance_data_loaded";

function visitorId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    if (localStorage.getItem("di_owner")) return null;
    let id = localStorage.getItem("di_v");
    if (!id) {
      id = (crypto.randomUUID?.() ?? `${Date.now()}${Math.random()}`)
        .replace(/[^a-z0-9]/gi, "")
        .toLowerCase()
        .slice(0, 32);
      localStorage.setItem("di_v", id);
    }
    return id;
  } catch {
    return null;
  }
}

function send(payload: Record<string, string>) {
  if (!API_URL) return;
  const body = new Blob([JSON.stringify(payload)], { type: "text/plain" });
  if (navigator.sendBeacon?.(`${API_URL}/api/track`, body)) return;
  void fetch(`${API_URL}/api/track`, { method: "POST", body, keepalive: true })
    .catch((error: unknown) => console.warn("Could not send anonymous usage tracking.", error));
}

export function trackPageView(path: string) {
  const id = visitorId();
  if (id) send({ v: id, p: path });
}

export function trackProductAction(action: ProductAction) {
  const id = visitorId();
  if (id) send({ v: id, a: action });
}
