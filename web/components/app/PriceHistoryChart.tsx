"use client";

import { useEffect, useMemo, useState } from "react";
import { get } from "../../lib/market";

type Point = { date: string; close: number | null; close_usd: number | null };
type History = { from: string; to: string; days: number; currency: string; prices: Point[]; note: string };

const RANGES: [string, number | null][] = [["1M", 31], ["6M", 183], ["1Y", 366], ["5Y", 1827], ["Max", null]];
const W = 640;
const H = 180;

function shift(date: string, days: number): string {
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

/** Thin a long series to at most `n` points, keeping the first and last. */
function thin<T>(rows: T[], n = 700): T[] {
  if (rows.length <= n) return rows;
  const step = (rows.length - 1) / (n - 1);
  return Array.from({ length: n }, (_, i) => rows[Math.round(i * step)]);
}

const fmt = (v: number) => v.toLocaleString("en-US", { maximumFractionDigits: v >= 100 ? 0 : 2 });

/** Daily closing price over time for one listed share, from /api/markets/history. Hides itself when the listing has
 * fewer than two stored days. */
export function PriceHistoryChart({ exchange, symbol }: { exchange: string; symbol: string }) {
  const [data, setData] = useState<History | null>(null);
  const [range, setRange] = useState<string>("1Y");
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    setData(null);
    get<History>("/api/markets/history", { exchange, symbol }).then(setData).catch(() => setData(null));
  }, [exchange, symbol]);

  const view = useMemo(() => {
    const all = (data?.prices ?? []).filter((p): p is Point & { close: number } => p.close != null);
    if (all.length < 2) return null;
    const days = RANGES.find(([k]) => k === range)?.[1] ?? null;
    const since = days ? shift(all[all.length - 1].date, days) : all[0].date;
    const rows = thin(all.filter((p) => p.date >= since));
    if (rows.length < 2) return null;
    const lo = Math.min(...rows.map((p) => p.close));
    const hi = Math.max(...rows.map((p) => p.close));
    const span = hi - lo || hi || 1;
    const xy = rows.map((p, i) => [(i / (rows.length - 1)) * W, H - 8 - ((p.close - lo) / span) * (H - 16)] as const);
    return { rows, lo, hi, xy, change: rows[rows.length - 1].close / rows[0].close - 1 };
  }, [data, range]);

  if (!data || !view) return null;
  // A period button appears once the stored history covers most of it.
  const available = RANGES.filter(([, d]) => d === null || d <= 31 || data.from <= shift(data.to, Math.round(d * 0.6)));
  const at = hover != null ? view.rows[hover] : view.rows[view.rows.length - 1];
  const up = view.change >= 0;

  return (
    <section className="panel p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h3 className="eyebrow">Price history</h3>
          <p className="mt-1 text-sm">
            <b>{fmt(at.close as number)} {data.currency}</b>
            <span className="text-[color:var(--muted)]"> on {at.date}</span>
            {hover == null && <span className={up ? "text-verified" : "text-risk"}> · {(view.change * 100).toFixed(1)}% over the period</span>}
          </p>
        </div>
        <div className="flex gap-1" role="group" aria-label="Period">
          {available.map(([k]) => (
            <button key={k} type="button" onClick={() => setRange(k)} aria-pressed={range === k}
              className={`rounded-md px-2 py-1 text-[0.75rem] ${range === k ? "bg-white/10 font-semibold" : "text-[color:var(--muted)] hover:text-[color:var(--text)]"}`}>
              {k}
            </button>
          ))}
        </div>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className={`mt-3 h-44 w-full ${up ? "text-verified" : "text-risk"}`} role="img"
        aria-label={`Daily closing price from ${view.rows[0].date} to ${view.rows[view.rows.length - 1].date}`}
        preserveAspectRatio="none"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const box = e.currentTarget.getBoundingClientRect();
          const i = Math.round(((e.clientX - box.left) / box.width) * (view.rows.length - 1));
          setHover(Math.max(0, Math.min(view.rows.length - 1, i)));
        }}>
        <polyline fill="none" stroke="currentColor" strokeWidth="1.5" vectorEffect="non-scaling-stroke"
          points={view.xy.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ")} />
        {hover != null && (
          <line x1={view.xy[hover][0]} x2={view.xy[hover][0]} y1={0} y2={H} stroke="currentColor" strokeOpacity="0.35"
            vectorEffect="non-scaling-stroke" />
        )}
      </svg>
      <div className="mt-1 flex justify-between text-[0.75rem] text-[color:var(--dim)]">
        <span>{view.rows[0].date}</span>
        <span>Low {fmt(view.lo)} · High {fmt(view.hi)}</span>
        <span>{view.rows[view.rows.length - 1].date}</span>
      </div>
      <p className="mt-2 text-[0.75rem] leading-relaxed text-[color:var(--dim)]">
        Daily closes in {data.currency}, adjusted for splits. Stored history starts {data.from}.
      </p>
    </section>
  );
}
