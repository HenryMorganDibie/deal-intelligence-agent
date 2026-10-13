const API_URL = process.env.NEXT_PUBLIC_API_URL?.trim().replace(/\/$/, "") ?? "";

export type AnalyseInput = {
  company: string;
  ticker?: string;
  lookback_days: number;
  compliance: boolean;
};

export type AnalyseResult = { id: string; runs_used: number; daily_limit: number };

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

/** Runs the pipeline server-side; the brief is saved to the caller's history. */
export async function analyse(accessToken: string, input: AnalyseInput): Promise<AnalyseResult> {
  if (!API_URL) throw new ApiError("The analysis API is not configured.", 503);
  let resp: Response;
  try {
    resp = await fetch(`${API_URL}/api/analyse`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify(input),
    });
  } catch {
    throw new ApiError("Could not reach the analysis service. Check your connection and try again.", 0);
  }
  const body = await resp.json().catch(() => null);
  if (!resp.ok) {
    const detail = typeof body?.detail === "string" ? body.detail : "The analysis failed. Try again in a minute.";
    throw new ApiError(detail, resp.status);
  }
  return body as AnalyseResult;
}
