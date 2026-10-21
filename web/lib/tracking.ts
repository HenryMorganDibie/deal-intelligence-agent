const API_URL = process.env.NEXT_PUBLIC_API_URL?.trim().replace(/\/$/, "") ?? "";

export type ProductAction =
  | "deals_loaded"
  | "investors_loaded"
  | "events_loaded"
  | "risk_data_loaded"
  | "company_data_loaded"
  | "watchlists_used"
  | "brief_opened"
  | "performance_data_loaded"
  | "deal_search_submitted"
  | "deal_opened"
  | "research_submitted"
  | "market_brief_opened";

export function browserVisitorId(): string | null {
  if (typeof window === "undefined") return null;
  try {
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

function visitorId(): string | null {
  try {
    if (typeof window === "undefined" || localStorage.getItem("di_owner")) return null;
    return browserVisitorId();
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

export function trackProductAction(
  action: ProductAction,
  targetId?: string,
  context?: Record<string, string | number | boolean | null | undefined>,
) {
  const id = visitorId();
  if (!id) return;
  const payload: Record<string, string> = { v: id, a: action };
  if (targetId) payload.t = targetId.slice(0, 160);
  if (context) {
    const safeContext = Object.fromEntries(
      Object.entries(context)
        .filter(([key, value]) => /^[a-z_]{1,32}$/.test(key) && value !== undefined && value !== null)
        .map(([key, value]) => [key, typeof value === "string" ? value.slice(0, 80) : value]),
    );
    payload.c = JSON.stringify(safeContext).slice(0, 900);
  }
  send(payload);
}
