import type { FieldAccuracy, FieldCheck, Verification as V } from "../../lib/market";
import { usd } from "./ui";

const STATUS: Record<FieldCheck["status"], { label: string; cls: string; help: string }> = {
  corroborated: { label: "Corroborated", cls: "border-verified/50 text-verified", help: "Stated by two or more independent stories." },
  reported: { label: "Single source", cls: "border-white/25 text-[color:var(--text)]", help: "Stated by one story, or copies of one story." },
  derived: { label: "Derived", cls: "border-white/15 text-[color:var(--muted)]", help: "Computed from reported values." },
  classified: { label: "Classified", cls: "border-white/15 text-[color:var(--muted)]", help: "Assigned by keyword rules, not stated by a source." },
  uncertain: { label: "Uncertain", cls: "border-risk/60 text-risk", help: "Sources disagree, or the extraction is known to be weak here." },
  "not disclosed": { label: "Not disclosed", cls: "border-dashed border-white/15 text-[color:var(--dim)]", help: "No source states it." },
};

// Which measured field accuracy applies to each displayed field.
const ACCURACY_KEY: Record<string, string> = {
  Target: "target",
  "Buyer, lead investor or lender": "buyer, lead investor or lender",
  "Amount (as reported)": "amount and currency (when disclosed)",
  Stake: "stake %",
  Stage: "stage (announced / completed / rumoured)",
  "Deal type": "deal_type",
  Country: "country",
};

function show(f: FieldCheck): string {
  if (f.value === null || f.value === undefined || f.value === "") return "n/a";
  if (typeof f.value === "number" && /USD|valuation/i.test(f.field)) return usd(f.value);
  return String(f.value).replace(/_/g, " ");
}

export function VerificationPanel({ v, accuracy }: { v: V; accuracy: FieldAccuracy }) {
  const tierCls =
    v.tier === "single source" ? "border-risk/40 bg-risk/[0.05] text-risk" : "border-verified/40 bg-verified/[0.06] text-verified";
  return (
    <section aria-labelledby="verification-title" className="mt-10">
      <h2 id="verification-title" className="eyebrow">Verification</h2>
      <div className={`mt-3 rounded-[10px] border px-4 py-3 text-[0.875rem] ${tierCls}`}>
        <span className="font-medium">{v.tier_label}.</span>{" "}
        <span className="text-[color:var(--muted)]">
          {v.sources} source{v.sources === 1 ? "" : "s"}
          {v.syndicated_copies > 0 ? `, of which ${v.syndicated_copies} repeat another story and are not counted as independent` : ""}.
        </span>
      </div>

      <dl className="mt-4 grid gap-3 text-[0.8125rem] sm:grid-cols-3">
        <div className="panel p-3">
          <dt className="eyebrow">First reported</dt>
          <dd className="mt-1">{v.dates.first_reported ?? "n/a"}</dd>
        </div>
        <div className="panel p-3">
          <dt className="eyebrow">Announced or rumoured</dt>
          <dd className="mt-1">{v.dates.announced_or_rumoured ?? "not reported separately"}</dd>
        </div>
        <div className="panel p-3">
          <dt className="eyebrow">Completion reported</dt>
          <dd className="mt-1">{v.dates.completed_reported ?? "not reported"}</dd>
        </div>
      </dl>
      <p className="mt-2 text-[0.75rem] text-[color:var(--dim)]">{v.dates.note}</p>

      <div className="mt-5 overflow-x-auto">
        <table className="w-full min-w-[40rem] text-left text-[0.8125rem]">
          <thead>
            <tr className="text-[color:var(--dim)]">
              <th className="border-b hairline py-2 pr-4 font-normal">Field</th>
              <th className="border-b hairline py-2 pr-4 font-normal">Value</th>
              <th className="border-b hairline py-2 pr-4 font-normal">Status</th>
              <th className="border-b hairline py-2 pr-4 font-normal">Why</th>
              <th className="border-b hairline py-2 font-normal" title="Share of records where this field was right on the held-out evaluation set">
                Field accuracy (held-out)
              </th>
            </tr>
          </thead>
          <tbody>
            {v.fields.map((f) => {
              const st = STATUS[f.status];
              const acc = accuracy?.fields?.[ACCURACY_KEY[f.field] ?? ""];
              return (
                <tr key={f.field}>
                  <td className="border-b hairline py-2.5 pr-4 align-top">{f.field}</td>
                  <td className="border-b hairline py-2.5 pr-4 align-top">{show(f)}</td>
                  <td className="border-b hairline py-2.5 pr-4 align-top">
                    <span title={st.help} className={`inline-flex whitespace-nowrap rounded-full border px-2 py-0.5 text-[0.6875rem] ${st.cls}`}>
                      {st.label}
                    </span>
                  </td>
                  <td className="border-b hairline py-2.5 pr-4 align-top text-[color:var(--muted)]">{f.basis}</td>
                  <td className="border-b hairline py-2.5 align-top kbd text-[0.75rem] text-[color:var(--muted)]">
                    {acc ? `${Math.round(acc.value * 100)}% (${Math.round(acc.low * 100)}-${Math.round(acc.high * 100)}, n=${acc.n})` : ""}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {accuracy?.fully_correct_record && (
        <p className="mt-2 text-[0.75rem] text-[color:var(--dim)]">
          On the held-out evaluation set, {Math.round(accuracy.fully_correct_record.value * 100)}% of records had every field
          right (n={accuracy.fully_correct_record.n}). Field accuracy is for this kind of field in general, not for this record.{" "}
          <a href="/app/evaluation#data-quality" className="text-verified hover:underline">How this is measured</a>
        </p>
      )}

      <h2 className="eyebrow mt-10">Sources, grouped into independent stories ({v.independent_stories})</h2>
      <ol className="mt-3 space-y-3 text-[0.8125rem]">
        {v.story_groups.map((g, i) => (
          <li key={i} className="panel p-3">
            <p className="kbd text-[0.6875rem] uppercase tracking-[0.12em] text-[color:var(--dim)]">
              Story {i + 1}
              {g.length > 1 ? ` · ${g.length} copies` : ""}
            </p>
            <ul className="mt-1.5 space-y-1">
              {g.map((s, j) => (
                <li key={j}>
                  {s.url ? (
                    <a href={s.url} target="_blank" rel="noreferrer" className="hover:underline">
                      {s.title || s.publisher || "Source"}
                    </a>
                  ) : (
                    s.title || s.publisher
                  )}{" "}
                  <span className="text-[color:var(--dim)]">
                    {s.publisher} · {s.date}
                  </span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
    </section>
  );
}
