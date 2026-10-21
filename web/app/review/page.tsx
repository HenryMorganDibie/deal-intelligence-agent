"use client";

import { useEffect, useMemo, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL?.trim().replace(/\/$/, "") ?? "";

type Headline = { item_id: string; title: string; publisher: string | null; date: string | null };
type Pair = { item_id: string; a: Headline; b: Headline };
type Label = Record<string, unknown>;
type Stored = { kind: "item" | "pair"; item_id: string; label: Label };
type Session = {
  year: number;
  role: "a" | "b" | "adjudicator";
  name: string;
  labels: Stored[];
  annotator_labels: (Stored & { role: "a" | "b" })[] | null;
  items: Headline[];
  pairs: Pair[];
  guidelines_md: string | null;
};

const DEAL_TYPES = ["equity_funding", "debt_financing", "acquisition", "merger", "exit", "fund_raise", "ipo", "joint_venture"];
const STAGES = ["rumoured", "announced", "completed"];
const AMOUNT_KINDS = ["deal_size", "valuation", "market_size", "programme_or_pledge", "none"];
const COUNTRY_BASES = ["named_in_headline", "known_entity", "unclear"];
const CORE_ITEM = ["is_transaction", "in_scope", "deal_type", "target", "amount", "currency", "amount_kind", "country"];
const ROLE_LABEL = { a: "Annotator A", b: "Annotator B", adjudicator: "Adjudicator" } as const;
const words = (s: string) => s.replaceAll("_", " ");

async function call<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${API}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error((data as { detail?: string }).detail ?? "Request failed");
  return data as T;
}

function done(label: Label | undefined, kind: "item" | "pair") {
  return Boolean(label) && label?.[kind === "item" ? "is_transaction" : "same_transaction"] != null;
}

function sameCore(a: Label | undefined, b: Label | undefined, kind: "item" | "pair") {
  const fields = kind === "item" ? CORE_ITEM : ["same_transaction"];
  const norm = (f: string, v: unknown) => (f === "target" && typeof v === "string" ? v.trim().toLowerCase().replace(/\s+/g, " ") : v ?? null);
  return fields.filter((f) => norm(f, a?.[f]) !== norm(f, b?.[f]));
}

function Choice({ label, value, options, onChange, allowEmpty = true }: {
  label: string; value: unknown; options: [unknown, string][]; onChange: (v: unknown) => void; allowEmpty?: boolean;
}) {
  return (
    <fieldset className="min-w-0">
      <legend className="mb-1 text-[0.8125rem] text-[color:var(--muted)]">{label}</legend>
      <div className="flex flex-wrap gap-1.5">
        {options.map(([v, text]) => (
          <button key={String(v)} type="button" onClick={() => onChange(value === v && allowEmpty ? null : v)}
            className={`rounded-full border px-3 py-1 text-[0.8125rem] ${value === v ? "border-verified bg-verified/15 text-verified" : "hairline text-[color:var(--muted)] hover:text-[color:var(--text)]"}`}>
            {text}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block min-w-0">
      <span className="mb-1 block text-[0.8125rem] text-[color:var(--muted)]">{label}</span>
      {children}
    </label>
  );
}

function ItemForm({ label, set }: { label: Label; set: (k: string, v: unknown) => void }) {
  const text = (k: string, placeholder = "") => (
    <input value={(label[k] as string) ?? ""} onChange={(e) => set(k, e.target.value || null)} placeholder={placeholder} className="field w-full" />
  );
  const select = (k: string, options: string[]) => (
    <select value={(label[k] as string) ?? ""} onChange={(e) => set(k, e.target.value || null)} className="field w-full">
      <option value="">—</option>
      {options.map((o) => <option key={o} value={o}>{words(o)}</option>)}
    </select>
  );
  const isTx = label.is_transaction === true;
  return (
    <div className="grid gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Choice label="Is this a specific private-market transaction?" value={label.is_transaction} onChange={(v) => set("is_transaction", v)}
          options={[[true, "Yes"], [false, "No"]]} />
        <Choice label="In scope (an African party or an asset in Africa)?" value={label.in_scope} onChange={(v) => set("in_scope", v)}
          options={[[true, "Yes"], [false, "No"]]} />
      </div>
      {(label.is_transaction === false || label.in_scope === false) && (
        <Field label="Reason (required), e.g. sovereign bond, no African party, commentary">{text("scope_reason")}</Field>
      )}
      {isTx && (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Deal type">{select("deal_type", DEAL_TYPES)}</Field>
            <Field label="Stage">{select("stage", STAGES)}</Field>
            <Field label="What the headline's figure is">{select("amount_kind", AMOUNT_KINDS)}</Field>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Target (company raising, acquired or borrowing; name only)">{text("target")}</Field>
            <Field label="Buyer, lead investor or lender">{text("acquirer_or_lead")}</Field>
          </div>
          <Field label="Other parties (comma-separated)">
            <input value={((label.other_parties as string[]) ?? []).join(", ")} className="field w-full"
              onChange={(e) => set("other_parties", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} />
          </Field>
          <div className="grid gap-4 sm:grid-cols-4">
            <Field label="Deal size as stated">
              <input type="number" min={0} value={(label.amount as number) ?? ""} className="field w-full"
                onChange={(e) => set("amount", e.target.value === "" ? null : Number(e.target.value))} placeholder="85000000" />
            </Field>
            <Field label="Currency (ISO)">{text("currency", "USD")}</Field>
            <Field label="Stake acquired %">
              <input type="number" min={0} max={100} value={(label.stake_pct as number) ?? ""} className="field w-full"
                onChange={(e) => set("stake_pct", e.target.value === "" ? null : Number(e.target.value))} />
            </Field>
            <Field label="Language">{text("language", "en")}</Field>
          </div>
          <div className="grid gap-4 sm:grid-cols-4">
            <Field label="Target's country (ISO2)">{text("country", "NG")}</Field>
            <Field label="Country basis">{select("country_basis", COUNTRY_BASES)}</Field>
            <Field label="Asset location (ISO2, asset deals)">{text("asset_location")}</Field>
            <Choice label="Pan-African, no single home market" value={label.africa_wide} onChange={(v) => set("africa_wide", v)} options={[[true, "Yes"]]} />
          </div>
        </>
      )}
      <div className="grid gap-4 sm:grid-cols-[1fr_2fr]">
        <Choice label="Confidence" value={label.confidence} onChange={(v) => set("confidence", v)} options={[["high", "High"], ["low", "Low (I had to guess)"]]} />
        <Field label="Note (what you checked, if anything)">{text("note")}</Field>
      </div>
    </div>
  );
}

function Headline({ h }: { h: Headline }) {
  return (
    <div>
      <p className="text-[1.0625rem] leading-snug">{h.title}</p>
      <p className="mt-1 text-[0.8125rem] text-[color:var(--dim)]">{h.publisher ?? "Unknown publisher"} · {h.date ?? "no date"}</p>
    </div>
  );
}

function Compare({ a, b, kind }: { a?: Label; b?: Label; kind: "item" | "pair" }) {
  const differ = new Set(sameCore(a, b, kind));
  const fields = kind === "item" ? CORE_ITEM : ["same_transaction", "confidence", "note"];
  const show = (v: unknown) => (v == null || v === "" ? "—" : typeof v === "boolean" ? (v ? "yes" : "no") : String(v));
  return (
    <table className="mt-3 w-full text-left text-[0.8125rem]">
      <thead className="text-[color:var(--dim)]"><tr><th className="py-1 font-normal">Field</th><th className="font-normal">A</th><th className="font-normal">B</th></tr></thead>
      <tbody>
        {fields.map((f) => (
          <tr key={f} className={`border-t hairline ${differ.has(f) ? "text-risk" : ""}`}>
            <td className="py-1">{words(f)}</td><td>{show(a?.[f])}</td><td>{show(b?.[f])}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function ReviewPage() {
  const [token, setToken] = useState("");
  const [s, setS] = useState<Session | null>(null);
  const [labels, setLabels] = useState<Record<string, Label>>({});
  const [tab, setTab] = useState<"item" | "pair" | "guide">("item");
  const [current, setCurrent] = useState<string | null>(null);
  const [draft, setDraft] = useState<Label>({});
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const t = new URLSearchParams(window.location.search).get("t") ?? "";
    setToken(t);
    if (!t) { setError("Open this page from your private labelling link."); return; }
    call<Session>("/api/review/session", { token: t })
      .then((session) => {
        setS(session);
        setLabels(Object.fromEntries(session.labels.map((l) => [`${l.kind}:${l.item_id}`, l.label])));
      })
      .catch((e) => setError((e as Error).message));
  }, []);

  const others = useMemo(() => {
    const out: Record<string, { a?: Label; b?: Label }> = {};
    for (const l of s?.annotator_labels ?? []) (out[`${l.kind}:${l.item_id}`] ??= {})[l.role] = l.label;
    return out;
  }, [s]);
  const adjudicator = s?.role === "adjudicator";
  // The adjudicator rules only where both annotators have labelled and disagree on a core judgement.
  const ids = useMemo(() => {
    if (!s) return [] as string[];
    const all = tab === "pair" ? s.pairs.map((p) => p.item_id) : s.items.map((i) => i.item_id);
    if (!adjudicator || tab === "guide") return all;
    const kind = tab as "item" | "pair";
    return all.filter((id) => {
      const o = others[`${kind}:${id}`];
      return o && done(o.a, kind) && done(o.b, kind) && sameCore(o.a, o.b, kind).length > 0;
    });
  }, [s, tab, adjudicator, others]);

  const kind = tab === "pair" ? "pair" : "item";
  const completed = ids.filter((id) => done(labels[`${kind}:${id}`], kind)).length;

  function open(id: string) {
    setCurrent(id);
    const own = labels[`${kind}:${id}`];
    setDraft(own ?? (adjudicator ? { ...(others[`${kind}:${id}`]?.a ?? {}) } : {}));
    setError("");
  }

  useEffect(() => {
    if (!s || tab === "guide") return;
    const next = ids.find((id) => !done(labels[`${kind}:${id}`], kind)) ?? ids[0];
    if (next) open(next); else setCurrent(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s, tab]);

  async function save() {
    if (!current) return;
    setSaving(true);
    setError("");
    try {
      const r = await call<{ label: Label }>("/api/review/label", { token, kind, item_id: current, label: draft });
      const updated = { ...labels, [`${kind}:${current}`]: r.label };
      setLabels(updated);
      const next = ids.find((id) => id !== current && !done(updated[`${kind}:${id}`], kind));
      if (next) open(next);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  if (!s) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-12">
        <meta name="robots" content="noindex" />
        <h1 className="text-2xl font-semibold">Independent review</h1>
        <p className={`mt-3 ${error ? "text-risk" : "text-[color:var(--muted)]"}`}>{error || "Loading your labelling session…"}</p>
      </main>
    );
  }

  const item = s.items.find((i) => i.item_id === current);
  const pair = s.pairs.find((p) => p.item_id === current);
  return (
    <main className="mx-auto max-w-6xl px-4 py-10 text-[0.9375rem]">
      <meta name="robots" content="noindex" />
      <h1 className="text-2xl font-semibold">{s.year} independent review</h1>
      <p className="mt-1 text-[color:var(--muted)]">
        {ROLE_LABEL[s.role]}: {s.name}. {adjudicator
          ? "You see only the items where A and B disagree on a core judgement; your label is final. Where they agree, their label is used."
          : "Label from the headline, publisher and date; you may open the article to confirm a fact and say so in the note. Do not discuss items with the other annotator before adjudication."}
        {" "}Each label saves when you press Save; you can return to any item.
      </p>

      <div className="mt-6 flex flex-wrap gap-2">
        {([["item", `Headlines`], ["pair", `Report pairs`], ["guide", "Labelling guide"]] as const).map(([t, text]) => (
          <button key={t} type="button" onClick={() => setTab(t)}
            className={`rounded-lg border px-4 py-2 ${tab === t ? "border-verified text-verified" : "hairline text-[color:var(--muted)]"}`}>{text}</button>
        ))}
      </div>

      {tab === "guide" ? (
        <pre className="panel mt-6 whitespace-pre-wrap p-5 text-[0.8125rem] leading-relaxed">{s.guidelines_md ?? "The guide is in the review folder: GUIDELINES.md."}</pre>
      ) : (
        <div className="mt-6 grid gap-6 lg:grid-cols-[14rem_1fr]">
          <aside className="panel max-h-[70vh] overflow-y-auto p-3">
            <p className="text-[0.8125rem] text-[color:var(--muted)]">{completed} of {ids.length} labelled</p>
            <div className="mt-2 h-1.5 rounded-full bg-white/[0.06]"><div className="h-1.5 rounded-full bg-verified" style={{ width: `${ids.length ? (completed / ids.length) * 100 : 0}%` }} /></div>
            <ul className="mt-3 grid grid-cols-4 gap-1 lg:grid-cols-3">
              {ids.map((id) => (
                <li key={id}>
                  <button type="button" onClick={() => open(id)}
                    className={`kbd w-full rounded px-1 py-1 text-[0.75rem] ${id === current ? "bg-verified text-black" : done(labels[`${kind}:${id}`], kind) ? "bg-verified/20 text-verified" : "bg-white/[0.04] text-[color:var(--muted)]"}`}>
                    {id}
                  </button>
                </li>
              ))}
            </ul>
            {ids.length === 0 && <p className="mt-3 text-[0.8125rem] text-[color:var(--dim)]">{adjudicator ? "No disagreements to resolve yet." : "Nothing to label."}</p>}
          </aside>

          {current && (item || pair) ? (
            <section className="panel p-5">
              <p className="kbd text-[0.75rem] text-[color:var(--dim)]">{current}</p>
              {item && <div className="mt-2"><Headline h={item} /></div>}
              {pair && (
                <div className="mt-2 grid gap-4 sm:grid-cols-2">
                  <div className="rounded-lg border hairline p-3"><p className="eyebrow">Report A</p><div className="mt-1"><Headline h={pair.a} /></div></div>
                  <div className="rounded-lg border hairline p-3"><p className="eyebrow">Report B</p><div className="mt-1"><Headline h={pair.b} /></div></div>
                </div>
              )}
              {adjudicator && <Compare a={others[`${kind}:${current}`]?.a} b={others[`${kind}:${current}`]?.b} kind={kind} />}
              <div className="mt-5 border-t hairline pt-5">
                {item ? (
                  <ItemForm label={draft} set={(k, v) => setDraft((d) => ({ ...d, [k]: v }))} />
                ) : (
                  <div className="grid gap-4">
                    <Choice label="Do both headlines report the same transaction?" value={draft.same_transaction}
                      onChange={(v) => setDraft((d) => ({ ...d, same_transaction: v }))} options={[[true, "Same transaction"], [false, "Different"]]} />
                    <p className="text-[0.8125rem] text-[color:var(--dim)]">A first close and a later final close of one fund are different transactions; so are two raises by one company months apart.</p>
                    <Choice label="Confidence" value={draft.confidence} onChange={(v) => setDraft((d) => ({ ...d, confidence: v }))} options={[["high", "High"], ["low", "Low"]]} />
                    <Field label="Note"><input value={(draft.note as string) ?? ""} onChange={(e) => setDraft((d) => ({ ...d, note: e.target.value }))} className="field w-full" /></Field>
                  </div>
                )}
              </div>
              {error && <p className="mt-4 text-risk">{error}</p>}
              <div className="mt-5 flex gap-2">
                <button type="button" onClick={save} disabled={saving} className="btn btn-primary">{saving ? "Saving…" : "Save and next"}</button>
              </div>
            </section>
          ) : (
            <section className="panel p-5 text-[color:var(--muted)]">{ids.length ? "Choose an item." : "Nothing here yet."}</section>
          )}
        </div>
      )}
    </main>
  );
}
