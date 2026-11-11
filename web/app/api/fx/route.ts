import { NextResponse } from "next/server";
import { loadNairaRate } from "../../../lib/catalog";

export const revalidate = 300;

/** Current naira rate for the billing page's approximate dollar figure. */
export async function GET() {
  return NextResponse.json(await loadNairaRate(), {
    headers: { "Cache-Control": "public, s-maxage=300, stale-while-revalidate=60" } });
}
