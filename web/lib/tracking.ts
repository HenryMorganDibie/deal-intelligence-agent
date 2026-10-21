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
  | "market_brief_opened"
  | "deal_impression";

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

// Crawlers, link previews and automated browsers run the page script too; they are not visitors.
const BOT_AGENT = /bot|crawl|spider|slurp|preview|headless|lighthouse|pagespeed|facebookexternalhit|embedly|whatsapp|curl|python|axios|playwright|puppeteer/i;

function isAutomated(): boolean {
  try {
    return Boolean(navigator.webdriver) || BOT_AGENT.test(navigator.userAgent || "");
  } catch {
    return false;
  }
}

function visitorId(): string | null {
  try {
    if (typeof window === "undefined" || localStorage.getItem("di_owner") || isAutomated()) return null;
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

/** Where this session landed from, sent once per browser session: the referring site's host (never the
 * full URL) and any utm_source, utm_medium and utm_campaign tags on the landing address. */
function landingSource(): Record<string, string> {
  try {
    if (sessionStorage.getItem("di_src")) return {};
    sessionStorage.setItem("di_src", "1");
    const source: Record<string, string> = {};
    if (document.referrer) {
      const host = new URL(document.referrer).hostname.toLowerCase();
      if (host && host !== window.location.hostname) source.r = host;
    }
    const params = new URLSearchParams(window.location.search);
    for (const [param, key] of [["utm_source", "us"], ["utm_medium", "um"], ["utm_campaign", "uc"]]) {
      const value = params.get(param);
      if (value) source[key] = value.slice(0, 60);
    }
    return source;
  } catch {
    return {};
  }
}

export function trackPageView(path: string) {
  const id = visitorId();
  if (id) send({ v: id, p: path, ...landingSource() });
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
  if (action === "deal_search_submitted" || action === "deal_opened" || action === "research_submitted" || action === "market_brief_opened" || action === "deal_impression") {
    payload.e = typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (ch) => {
          const n = Math.random() * 16 | 0;
          return (ch === "x" ? n : (n & 3 | 8)).toString(16);
        });
  }
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
