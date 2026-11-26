/**
 * How the web app reaches the Python API.
 *
 * The API's /api/* routes serve this app only: they answer requests carrying the web app's secret and refuse
 * everyone else (customers use the key-authenticated /v1 instead). So:
 *  - in the browser, calls go to this site's own /api/data/* path, and proxy.ts forwards them to the API
 *    with the secret added on the server; the secret never reaches a browser;
 *  - on the server (pages, metadata images), calls go straight to the API with the secret header.
 */

/** The API's public origin, e.g. https://api.deal-intelligence.app. */
export const API_ORIGIN = (process.env.NEXT_PUBLIC_API_URL ?? "").trim().replace(/\/$/, "");

/** Header that tells the API a request comes from this app. */
export const CLIENT_HEADER = "x-deal-intel-client";

const isBrowser = typeof window !== "undefined";

/** Whether the app can reach the API at all. */
export const API_CONFIGURED = Boolean(API_ORIGIN);

/** URL for an API path such as "/api/deals?limit=5". */
export function apiUrl(path: string): string {
  if (isBrowser) return path.startsWith("/api/") ? `/api/data/${path.slice(5)}` : path;
  // With no API address a server-side URL would be relative. Next 14's fetch rejected that at once and every caller
  // falls back; Next 16's waits instead, which stalls the build. Fail the same way, before the fetch.
  if (!API_ORIGIN) throw new TypeError(`The API address (NEXT_PUBLIC_API_URL) is not set; cannot fetch ${path}.`);
  return `${API_ORIGIN}${path}`;
}

/** Headers for a server-side API call (adds the app's secret). In the browser the proxy adds it instead. */
export function apiHeaders(init?: HeadersInit): Headers {
  const headers = new Headers(init);
  const secret = isBrowser ? "" : process.env.DEAL_INTEL_WEB_SECRET || "";
  if (secret) headers.set(CLIENT_HEADER, secret);
  return headers;
}

/** Absolute public URL for routes other services open directly (RSS feeds), never proxied. */
export function publicApiUrl(path: string): string {
  return `${API_ORIGIN}${path}`;
}
