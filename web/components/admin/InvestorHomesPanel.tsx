"use client";

import { useEffect, useState } from "react";
import { apiUrl } from "../../lib/api-base";
import { AFRICAN_COUNTRIES } from "../../lib/countries";

type Unplaced = { name_key: string; name: string; deals: number; example?: string | null };
type Home = { name_key: string; name: string; country: string | null; source: "owner" | "article"; evidence?: string | null;
  evidence_url?: string | null; updated_at: string };
type Data = { unplaced: Unplaced[]; set: Home[]; countries: Record<string, string> };

/** Investors whose home country is unknown, most frequent first, with a country picker each; and the countries
 * already set, by the owner or found in articles (those can be confirmed, changed or cleared). */
export function InvestorHomesPanel({ adminKey }: { adminKey: string }) {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [tab, setTab] = useState<"unplaced" | "found" | "set">("unplaced");

  async function load() {
    setError("");
    try {
      const r = await fetch(apiUrl("/api/admin/investor-homes"), {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key: adminKey }), cache: "no-store",
      });
      if (!r.ok) throw new Error(r.status === 401 ? "Wrong key" : "The list is unavailable.");
      setData((await r.json()) as Data);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => { if (adminKey) void load(); }, [adminKey]); // eslint-disable-line react-hooks/exhaustive-deps

  async function save(name: string, country: string, clear = false) {
    setSaving(name);
    setNote("");
    try {
      const r = await fetch(apiUrl("/api/admin/investor-homes/set"), {
        method: "POST", headers: { "Content-Type": "application/json" }, cache: "no-store",
        body: JSON.stringify({ key: adminKey, name, country, clear }),
      });
      const body = (await r.json().catch(() => ({}))) as { detail?: string };
      if (!r.ok) throw new Error(body.detail || "Could not save.");
      setNote(clear ? `${name}: cleared.` : `${name}: ${country === "none" ? "no single country" : label(country)}.`);
      await load();
    } catch (e) {
      setNote((e as Error).message);
    } finally {
      setSaving(null);
    }
  }

  const label = (code: string | null) =>
    !code ? "No single country" : data?.countries[code] ?? AFRICAN_COUNTRIES.find(([c]) => c === code)?.[1] ?? code;

  const picker = (name: string, value = "") => (
    <select defaultValue={value} disabled={saving === name} aria-label={`Home country of ${name}`}
      onChange={(e) => e.target.value && save(name, e.target.value)}
      className="rounded-md border hairline bg-transparent px-2 py-1 text-[0.8125rem]">
      <option value="">Set country…</option>
      <option value="none">No single country (international)</option>
      <optgroup label="Outside Africa">
        {Object.entries(data?.countries ?? {}).map(([code, name]) => <option key={code} value={code}>{name}</option>)}
      </optgroup>
      <optgroup label="In Africa">
        {AFRICAN_COUNTRIES.map(([code, name]) => <option key={code} value={code}>{name}</option>)}
      </optgroup>
    </select>
  );

  if (error) return <p className="text-sm text-risk">{error}</p>;
  if (!data) return <p className="text-sm text-[color:var(--muted)]">Loading investors…</p>;
  const found = data.set.filter((h) => h.source === "article");
  const owned = data.set.filter((h) => h.source === "owner");
  const tabs: [typeof tab, string, number][] = [["unplaced", "Unknown", data.unplaced.length], ["found", "Found in articles", found.length],
    ["set", "Set by you", owned.length]];

  return (
    <div>
      <p className="text-[0.8125rem] leading-relaxed text-[color:var(--muted)]">
        Market briefs filtered by &ldquo;Investors from&rdquo; only count deals whose investor&apos;s home country is known. Set it once
        and it applies to every deal by that investor. Countries found in articles are used straight away; check them here.
      </p>
      <div className="mt-3 flex flex-wrap gap-1.5" role="tablist">
        {tabs.map(([id, name, n]) => (
          <button key={id} type="button" role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
            className={`rounded-full px-3 py-1 text-[0.8125rem] ${tab === id ? "bg-white/10 font-medium" : "text-[color:var(--muted)] hover:text-[color:var(--text)]"}`}>
            {name} <span className="text-[color:var(--dim)]">{n}</span>
          </button>
        ))}
      </div>
      {note && <p role="status" className="mt-3 text-sm text-verified">{note}</p>}

      {tab === "unplaced" && (
        data.unplaced.length === 0 ? <p className="mt-4 text-sm text-[color:var(--muted)]">Every investor in the last year has a known home country.</p> : (
          <ul className="mt-3 divide-y divide-white/[0.06] border-y hairline">
            {data.unplaced.map((u) => (
              <li key={u.name_key} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{u.name} <span className="font-normal text-[color:var(--dim)]">· {u.deals} deal{u.deals === 1 ? "" : "s"}</span></p>
                  {u.example && <p className="truncate text-[0.75rem] text-[color:var(--muted)]">{u.example}</p>}
                </div>
                {picker(u.name)}
              </li>
            ))}
          </ul>
        )
      )}

      {tab !== "unplaced" && (
        (tab === "found" ? found : owned).length === 0 ? (
          <p className="mt-4 text-sm text-[color:var(--muted)]">{tab === "found" ? "Nothing found in articles yet; the reader runs every Monday." : "You have not set any countries yet."}</p>
        ) : (
          <ul className="mt-3 divide-y divide-white/[0.06] border-y hairline">
            {(tab === "found" ? found : owned).map((h) => (
              <li key={h.name_key} className="flex flex-wrap items-start justify-between gap-3 py-2.5">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{h.name} <span className="font-normal text-verified">· {label(h.country)}</span></p>
                  {h.evidence && (
                    <p className="mt-0.5 text-[0.75rem] text-[color:var(--muted)]">
                      &ldquo;{h.evidence}&rdquo;{h.evidence_url && <> <a href={h.evidence_url} target="_blank" rel="noreferrer" className="underline underline-offset-2">source</a></>}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {tab === "found" && (
                    <button type="button" disabled={saving === h.name} onClick={() => save(h.name, h.country ?? "none")}
                      className="rounded-md border hairline px-2 py-1 text-[0.75rem] hover:bg-white/[0.06]">Confirm</button>
                  )}
                  {picker(h.name, "")}
                  <button type="button" disabled={saving === h.name} onClick={() => save(h.name, "", true)}
                    className="rounded-md px-2 py-1 text-[0.75rem] text-[color:var(--muted)] hover:text-risk">Clear</button>
                </div>
              </li>
            ))}
          </ul>
        )
      )}
    </div>
  );
}
