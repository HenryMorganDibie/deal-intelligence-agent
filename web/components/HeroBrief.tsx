"use client";

import { useEffect, useState } from "react";
import { SIGNAL_TYPE, label, moveRange, shortDate, type ShowcaseBrief } from "../lib/pulse";

/**
 * Hero product visual: a brief assembling itself, step by step. With a showcase brief
 * (the pipeline run daily on a fixed company list) every figure comes from that run;
 * without one, the figures below are from a run on Intel on 13 Oct 2026.
 */
const FALLBACK_STEPS = [
  { label: "Collect", detail: "4 SEC filings · 70 news items" },
  { label: "Rule engine", detail: "2 candidates · 10 off-target skipped" },
  { label: "Attribute", detail: "1 story about another company dropped" },
  { label: "Score", detail: "alpha + evidence quality" },
  { label: "Brief", detail: "human review required" },
];

const FALLBACK_SIGNALS = [
  {
    type: "Insider activity",
    sev: "HIGH",
    move: "-3.0% to +1.0%",
    text: "Form 4: open-market purchase of 105,263 shares ($10.0M) by the CEO",
    source: "SEC EDGAR · Form 4",
  },
  {
    type: "Earnings surprise",
    sev: "CRITICAL",
    move: "-2.2% to +0.9%",
    text: "Intel forecast crushes estimates as AI boom boosts chip demand",
    source: "Reuters · 0.95 credibility",
  },
];

type View = {
  date: string;
  command: string;
  steps: { label: string; detail: string }[];
  signals: {
    type: string;
    sev: string;
    move: string | null;
    text: string;
    source: string;
  }[];
  dropped: string | null;
  href: string | null;
};

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

function view(b: ShowcaseBrief | null | undefined): View {
  if (!b || !b.signal_count) {
    return {
      date: "13 Oct 2026",
      command: "python main.py analyse --company Intel --ticker INTC",
      steps: FALLBACK_STEPS,
      signals: FALLBACK_SIGNALS,
      dropped: null, // Static fallback headlines have no live source/date validation.
      href: null,
    };
  }
  const filings = b.filings ? `${plural(b.filings, "filing")} · ` : "";
  return {
    date: shortDate(b.created_at),
    command: `python main.py analyse --company "${b.company}"${b.ticker ? ` --ticker ${b.ticker}` : ""}`,
    steps: [
      { label: "Collect", detail: `${filings}${plural(b.news, "news item")}` },
      {
        label: "Rule engine",
        detail: `${plural(b.candidates, "candidate")}${b.off_target != null ? ` · ${b.off_target} off-target skipped` : ""}`,
      },
      {
        label: "Attribute",
        detail: b.unattributed
          ? `${plural(b.unattributed, "story", "stories")} about another company dropped`
          : "every story names the company",
      },
      { label: "Score", detail: "alpha + evidence quality" },
      {
        label: "Brief",
        detail: b.requires_human_review ? "human review required" : "no review flag",
      },
    ],
    signals: b.signals.map((s) => ({
      type: label(SIGNAL_TYPE, s.signal_type),
      sev: (s.severity ?? "").toUpperCase(),
      move: moveRange(s.move_low, s.move_high),
      text: s.evidence,
      source: s.source,
    })),
    dropped: b.unattributed_title,
    href: `/app/briefs/${b.id}`,
  };
}

export function HeroBrief({ brief = null }: { brief?: ShowcaseBrief | null }) {
  const { date, command, steps: STEPS, signals: SIGNALS, dropped, href } = view(brief);
  const total = STEPS.length;
  const [step, setStep] = useState(total + 1);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    setStep(0);
    let i = 0;
    const id = window.setInterval(() => {
      i += 1;
      setStep(i);
      if (i > total) window.clearInterval(id);
    }, 650);
    return () => window.clearInterval(id);
  }, [total]);

  const done = step > STEPS.length;

  return (
    <div className="panel relative overflow-hidden text-left">
      <div className="scan" aria-hidden />
      <div className="flex items-center justify-between border-b hairline px-4 py-3">
        <div className="flex items-center gap-2" aria-hidden>
          <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
          <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
          <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
        </div>
        <span className="tag">
          <span aria-hidden className="pulse-dot h-1 w-1 rounded-full bg-verified" />
          Live run · {date}
        </span>
      </div>

      <div className="px-4 pb-5 pt-4 sm:px-5">
        <p className={`kbd text-[0.8125rem] text-[color:var(--muted)] ${done ? "" : "caret"}`}>
          <span className="text-verified">$</span> {command}
        </p>

        <ol className="mt-4 space-y-1.5" aria-label="Pipeline progress">
          {STEPS.map((s, i) => {
            const state = step > i ? "done" : step === i ? "active" : "idle";
            return (
              <li
                key={s.label}
                className={`flex items-center gap-3 kbd text-[0.75rem] transition-opacity duration-300 ${
                  state === "idle" ? "opacity-25" : "opacity-100"
                }`}
              >
                <span
                  aria-hidden
                  className={`grid h-4 w-4 place-items-center rounded-full border ${
                    state === "done" ? "border-verified/60 text-verified" : "border-white/15 text-white/40"
                  }`}
                >
                  {state === "done" && (
                    <svg viewBox="0 0 12 12" className="h-2.5 w-2.5" fill="none">
                      <path
                        d="M2.5 6.2l2.2 2.2 4.8-4.9"
                        stroke="currentColor"
                        strokeWidth="1.6"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  )}
                </span>
                <span className="w-24 shrink-0 text-[color:var(--text)]">{s.label}</span>
                <span className="truncate text-[color:var(--muted)]">{s.detail}</span>
              </li>
            );
          })}
        </ol>

        <div className={`mt-5 space-y-2.5 transition-opacity duration-500 ${done ? "opacity-100" : "opacity-0"}`}>
          {SIGNALS.map((s) => (
            <div key={s.type + s.text} className="rounded-[10px] border hairline bg-white/[0.02] p-3">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="kbd text-[0.6875rem] uppercase tracking-[0.12em] text-verified">{s.type}</span>
                <span className="kbd text-[0.6875rem] text-[color:var(--muted)]">{s.sev}</span>
                {s.move && (
                  <span
                    className="kbd ml-auto text-[0.75rem] text-[color:var(--muted)]"
                    title="Measured market-adjusted 10-day move after similar flags (interquartile range)"
                  >
                    {s.move}
                  </span>
                )}
              </div>
              <p className="mt-1.5 text-[0.8125rem] leading-snug text-[color:var(--text)]">{s.text}</p>
              <p className="kbd mt-1 text-[0.6875rem] text-[color:var(--dim)]">{s.source}</p>
            </div>
          ))}
          {dropped && (
            <div className="rounded-[10px] border border-dashed border-white/10 p-3">
              <div className="flex items-center gap-3">
                <span className="kbd text-[0.6875rem] uppercase tracking-[0.12em] text-risk">Not attributed</span>
                <span className="kbd text-[0.6875rem] text-[color:var(--dim)]">about another company</span>
              </div>
              <p className="mt-1.5 text-[0.8125rem] leading-snug text-[color:var(--dim)] line-through decoration-white/20">
                {dropped}
              </p>
            </div>
          )}
          {href && (
            <a href={href} className="kbd block pt-1 text-right text-[0.75rem] text-verified hover:underline">
              Open the full brief →
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
