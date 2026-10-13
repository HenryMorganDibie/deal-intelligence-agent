"use client";

import { useEffect, useState } from "react";

/**
 * Hero product visual: a brief assembling itself, step by step. The figures
 * are from a real run against live SEC and news data (Intel, 13 Oct 2026).
 */
const STEPS = [
  { label: "Collect", detail: "4 SEC filings · 70 news items" },
  { label: "Rule engine", detail: "2 candidates · 10 off-target skipped" },
  { label: "Attribute", detail: "1 story about another company dropped" },
  { label: "Score", detail: "alpha + evidence quality" },
  { label: "Brief", detail: "human review required" },
];

const SIGNALS = [
  {
    type: "Insider activity",
    sev: "HIGH",
    move: "↑ 3–12%",
    text: "Form 4: open-market purchase of 105,263 shares ($10.0M) by the CEO",
    source: "SEC EDGAR · Form 4",
  },
  {
    type: "Earnings surprise",
    sev: "CRITICAL",
    move: "↑",
    text: "Intel forecast crushes estimates as AI boom boosts chip demand",
    source: "Reuters · 0.95 credibility",
  },
];

export function HeroBrief() {
  const [step, setStep] = useState(STEPS.length + 1);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    setStep(0);
    let i = 0;
    const id = window.setInterval(() => {
      i += 1;
      setStep(i);
      if (i > STEPS.length) window.clearInterval(id);
    }, 650);
    return () => window.clearInterval(id);
  }, []);

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
          Live run · 13 Oct 2026
        </span>
      </div>

      <div className="px-4 pb-5 pt-4 sm:px-5">
        <p className={`kbd text-[0.8125rem] text-[color:var(--muted)] ${done ? "" : "caret"}`}>
          <span className="text-verified">$</span> python main.py analyse --company Intel --ticker INTC
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
                      <path d="M2.5 6.2l2.2 2.2 4.8-4.9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
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
            <div key={s.type} className="rounded-[10px] border hairline bg-white/[0.02] p-3">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="kbd text-[0.6875rem] uppercase tracking-[0.12em] text-verified">{s.type}</span>
                <span className="kbd text-[0.6875rem] text-[color:var(--muted)]">{s.sev}</span>
                <span className="kbd ml-auto text-[0.75rem] text-verified">{s.move}</span>
              </div>
              <p className="mt-1.5 text-[0.8125rem] leading-snug text-[color:var(--text)]">{s.text}</p>
              <p className="kbd mt-1 text-[0.6875rem] text-[color:var(--dim)]">{s.source}</p>
            </div>
          ))}
          <div className="rounded-[10px] border border-dashed border-white/10 p-3">
            <div className="flex items-center gap-3">
              <span className="kbd text-[0.6875rem] uppercase tracking-[0.12em] text-risk">Not attributed</span>
              <span className="kbd text-[0.6875rem] text-[color:var(--dim)]">about another company</span>
            </div>
            <p className="mt-1.5 text-[0.8125rem] leading-snug text-[color:var(--dim)] line-through decoration-white/20">
              SoftBank Group Q1 profit beats expectations on Intel windfall
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
