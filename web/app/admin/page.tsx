"use client";

import { useEffect, useState } from "react";

type Row = { views: number; visitors: number; users: number };
type Stats = {
  since: string;
  totals: Row & { returning_users: number };
  days: (Row & { day: string })[];
  pages: { path: string; views: number; visitors: number }[];
};

const API = process.env.NEXT_PUBLIC_API_URL?.trim().replace(/\/$/, "") ?? "";

/** Owner-only usage page. Opening it marks this browser as the owner's, so its visits are not counted. */
export default function Admin() {
  const [key, setKey] = useState("");
  const [days, setDays] = useState(30);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState("");

  async function load(k: string, d: number) {
    setError("");
    try {
      const r = await fetch(`${API}/api/admin/stats`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: k, days: d }),
      });
      if (!r.ok) throw new Error(r.status === 401 ? "Wrong key" : "Stats unavailable");
      setStats(await r.json());
      localStorage.setItem("di_admin", k);
    } catch (e) {
      setStats(null);
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    try {
      localStorage.setItem("di_owner", "1");
      const k = localStorage.getItem("di_admin");
      if (k) {
        setKey(k);
        load(k, days);
      }
    } catch {
      /* storage blocked */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const t = stats?.totals;
  return (
    <main className="mx-auto max-w-3xl px-4 py-12 text-[0.9375rem]">
      <meta name="robots" content="noindex" />
      <h1 className="text-2xl font-semibold">Usage</h1>
      <p className="mt-1 text-[color:var(--muted)]">Only you can see this. This browser is excluded from the counts.</p>

      <form
        className="mt-6 flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          load(key, days);
        }}
      >
        <input
          type="password"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          placeholder="Admin key"
          className="min-w-0 flex-1 rounded-lg border hairline bg-transparent px-3 py-2"
        />
        <select
          value={days}
          onChange={(e) => {
            const d = Number(e.target.value);
            setDays(d);
            if (key) load(key, d);
          }}
          className="rounded-lg border hairline bg-transparent px-3 py-2"
        >
          {[1, 7, 30, 90, 365].map((d) => (
            <option key={d} value={d}>{d === 1 ? "Today" : `Last ${d} days`}</option>
          ))}
        </select>
        <button className="rounded-lg bg-white/90 px-4 py-2 font-medium text-black">Show</button>
      </form>
      {error && <p className="mt-3 text-risk">{error}</p>}

      {t && stats && (
        <>
          <div className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              [t.visitors, "unique browsers"],
              [t.users, "browsers that used the product"],
              [t.returning_users, "browsers that came back"],
              [t.views, "page views"],
            ].map(([n, label]) => (
              <div key={label as string} className="panel p-4">
                <div className="text-2xl font-semibold">{(n as number).toLocaleString("en-US")}</div>
                <div className="mt-1 text-[0.8125rem] text-[color:var(--muted)]">{label}</div>
              </div>
            ))}
          </div>
          <p className="mt-2 text-[0.8125rem] text-[color:var(--muted)]">
            Since {stats.since}. These are unique browser IDs, not verified people; the same person may count more than once across browsers or devices. &ldquo;Used the product&rdquo; means the browser opened a page under /app.
          </p>

          <h2 className="mt-8 font-semibold">By day</h2>
          <table className="mt-2 w-full text-left">
            <thead className="text-[color:var(--muted)]">
              <tr><th className="py-1 font-normal">Day</th><th className="font-normal">Unique browsers</th><th className="font-normal">Used product</th><th className="font-normal">Views</th></tr>
            </thead>
            <tbody>
              {stats.days.map((d) => (
                <tr key={d.day} className="border-t hairline"><td className="py-1.5 kbd">{d.day}</td><td>{d.visitors}</td><td>{d.users}</td><td>{d.views}</td></tr>
              ))}
            </tbody>
          </table>

          <h2 className="mt-8 font-semibold">Top pages</h2>
          <table className="mt-2 w-full text-left">
            <tbody>
              {stats.pages.map((p) => (
                <tr key={p.path} className="border-t hairline"><td className="py-1.5 kbd">{p.path}</td><td>{p.visitors} browsers</td><td>{p.views} views</td></tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </main>
  );
}
