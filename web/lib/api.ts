import type { Brief, Severity } from "./brief";

const API_URL = process.env.NEXT_PUBLIC_API_URL?.trim().replace(/\/$/, "") ?? "";

export type AnalyseInput = {
  company: string;
  ticker?: string;
  lookback_days: number;
  compliance: boolean;
};

export type AnalyseResult = {
  id: string;
  company: string;
  ticker: string | null;
  severity: Severity | null;
  signal_count: number;
};

export type StoredBrief = {
  id: string;
  company: string;
  ticker: string | null;
  brief: Brief;
  markdown: string | null;
  created_at: string;
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_URL) throw new ApiError("The analysis API is not configured.", 503);
  let resp: Response;
  try {
    resp = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError("Could not reach the analysis service. Check your connection and try again.", 0);
  }
  const body = await resp.json().catch(() => null);
  if (!resp.ok) {
    const detail = typeof body?.detail === "string" ? body.detail : "Something went wrong. Try again in a minute.";
    throw new ApiError(detail, resp.status);
  }
  return body as T;
}

/** Runs the pipeline server-side and stores the brief; returns its id. */
export function analyse(input: AnalyseInput): Promise<AnalyseResult> {
  return call("/api/analyse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

/** Fetches a stored brief by id. Ids are random, so a brief URL is a share link. */
export function getBrief(id: string): Promise<StoredBrief> {
  return call(`/api/briefs/${encodeURIComponent(id)}`);
}
