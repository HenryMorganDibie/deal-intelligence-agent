import { cookies } from "next/headers";

const ACCESS_COOKIE = "di_portfolio_access";
const REFRESH_COOKIE = "di_portfolio_refresh";

export type PortfolioUser = { id: string; email?: string | null };
export type PortfolioSession = { accessToken: string; user: PortfolioUser };
type AuthSessionPayload = {
  access_token?: string;
  refresh_token?: string;
  expires_in?: number;
  user?: PortfolioUser;
};

export class PortfolioRestError extends Error {
  constructor(public status: number) {
    super("Portfolio service request failed");
    this.name = "PortfolioRestError";
  }
}

export function portfolioConfig() {
  const url = (process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL || "").replace(/\/+$/, "");
  const key = process.env.SUPABASE_PUBLISHABLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY || process.env.SUPABASE_ANON_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";
  if (!url || !key) throw new Error("Portfolio authentication is not configured");
  return { url, key };
}

function cookieOptions(maxAge: number) {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
    maxAge,
  };
}

export function setPortfolioAuthCookies(session: AuthSessionPayload) {
  if (!session.access_token || !session.refresh_token) return;
  const jar = cookies();
  jar.set(ACCESS_COOKIE, session.access_token, cookieOptions(Math.max(60, session.expires_in || 3600)));
  jar.set(REFRESH_COOKIE, session.refresh_token, cookieOptions(60 * 60 * 24 * 60));
}

export function clearPortfolioAuthCookies() {
  const jar = cookies();
  jar.set(ACCESS_COOKIE, "", cookieOptions(0));
  jar.set(REFRESH_COOKIE, "", cookieOptions(0));
}

async function fetchAuthUser(accessToken: string) {
  const config = portfolioConfig();
  return fetch(config.url + "/auth/v1/user", {
    method: "GET",
    headers: { apikey: config.key, Authorization: "Bearer " + accessToken },
    cache: "no-store",
  });
}

export async function getPortfolioSession(): Promise<PortfolioSession | null> {
  const config = portfolioConfig();
  const jar = cookies();
  const accessToken = jar.get(ACCESS_COOKIE)?.value || "";
  const refreshToken = jar.get(REFRESH_COOKIE)?.value || "";

  if (accessToken) {
    const response = await fetchAuthUser(accessToken);
    if (response.ok) {
      const user = (await response.json()) as PortfolioUser;
      if (user.id) return { accessToken, user };
    } else if (response.status !== 401 && response.status !== 403) {
      throw new Error("Authentication service is temporarily unavailable");
    }
  }

  if (!refreshToken) {
    clearPortfolioAuthCookies();
    return null;
  }

  const refreshed = await fetch(config.url + "/auth/v1/token?grant_type=refresh_token", {
    method: "POST",
    headers: { apikey: config.key, "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
    cache: "no-store",
  });

  if (!refreshed.ok) {
    clearPortfolioAuthCookies();
    return null;
  }

  const session = (await refreshed.json()) as AuthSessionPayload;
  if (!session.access_token || !session.refresh_token) {
    clearPortfolioAuthCookies();
    return null;
  }
  setPortfolioAuthCookies(session);

  let user = session.user;
  if (!user?.id) {
    const response = await fetchAuthUser(session.access_token);
    if (!response.ok) {
      clearPortfolioAuthCookies();
      return null;
    }
    user = (await response.json()) as PortfolioUser;
  }
  return user?.id ? { accessToken: session.access_token, user } : null;
}

export async function portfolioRest<T = unknown>(
  accessToken: string,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const config = portfolioConfig();
  const headers = new Headers(init.headers || {});
  headers.set("apikey", config.key);
  headers.set("Authorization", "Bearer " + accessToken);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

  const response = await fetch(config.url + "/rest/v1/" + path, {
    ...init,
    headers,
    cache: "no-store",
  });
  if (!response.ok) throw new PortfolioRestError(response.status);
  const text = await response.text();
  return (text ? JSON.parse(text) : null) as T;
}

export function portfolioErrorResponse(error: unknown) {
  if (error instanceof PortfolioRestError) {
    if (error.status === 401) return { status: 401, message: "Please sign in again." };
    if (error.status === 403) return { status: 403, message: "You do not have permission to do that." };
    if (error.status === 404) return { status: 404, message: "The requested portfolio resource was not found." };
    if (error.status === 409) return { status: 409, message: "That record conflicts with existing data." };
    if (error.status === 400 || error.status === 422) return { status: 400, message: "The supplied portfolio data is invalid." };
  }
  return { status: 503, message: "The portfolio service is temporarily unavailable." };
}

/**
 * Whether a state-changing request came from this site. Cross-site forms can only send text/plain, form or
 * multipart bodies, so requiring JSON forces a CORS preflight that other origins fail; the Origin check covers
 * browsers that send it. Blocks login CSRF (signing a victim into an attacker's account).
 */
export function isSameSiteJsonRequest(request: Request): boolean {
  const type = (request.headers.get("content-type") || "").split(";", 1)[0].trim().toLowerCase();
  if (type !== "application/json") return false;
  const origin = request.headers.get("origin");
  if (!origin) return true;
  try {
    return new URL(origin).host === new URL(request.url).host || new URL(origin).host === request.headers.get("host");
  } catch {
    return false;
  }
}
