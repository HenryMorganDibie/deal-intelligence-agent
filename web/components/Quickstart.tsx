"use client";

import { useState } from "react";
import { Container, Heading, Reveal, Section } from "./primitives";

const TABS = [
  {
    id: "install",
    label: "Install",
    lines: [
      "git clone https://github.com/HenryMorganDibie/deal-intelligence-agent",
      "cd deal-intelligence-agent",
      "pip install -r requirements.txt",
      "export ANTHROPIC_API_KEY=sk-ant-...   # optional",
    ],
  },
  {
    id: "us",
    label: "US company",
    lines: ['python main.py analyse --company "Intel" --ticker INTC'],
  },
  {
    id: "africa",
    label: "African company",
    lines: [
      'python main.py analyse --company "GTBank" --ticker GTCO.LG     # NGX disclosures',
      'python main.py analyse --company "Naspers" --ticker NPN.JO     # JSE SENS',
    ],
  },
  {
    id: "export",
    label: "Export",
    lines: [
      'python main.py analyse --company "Boeing" --ticker BA \\',
      "  --compliance --output markdown --out-file brief.md",
    ],
  },
];

export function Quickstart() {
  const [tab, setTab] = useState(TABS[0].id);
  const [copied, setCopied] = useState(false);
  const active = TABS.find((t) => t.id === tab) ?? TABS[0];

  const copy = async () => {
    const text = active.lines.map((l) => l.replace(/\s+#.*$/, "")).join("\n");
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };

  return (
    <Section id="quickstart" labelledBy="quickstart-title">
      <Container className="grid gap-12 lg:grid-cols-[0.85fr_1.15fr] lg:items-start">
        <Heading
          index="10"
          eyebrow="Quickstart"
          id="quickstart-title"
          title="Your first brief in about a minute."
          lede={
            <>
              Python, no database to set up. Runs with Claude by default, or Llama through Groq with{" "}
              <code className="kbd text-[color:var(--text)]">--provider groq</code>. Without either key you still get the
              deterministic brief.
            </>
          }
        />

        <Reveal delay={100} className="min-w-0">
          <div className="panel overflow-hidden">
            <div className="flex items-center gap-1 overflow-x-auto border-b hairline px-2 py-2" role="tablist" aria-label="Quickstart">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  aria-selected={t.id === tab}
                  onClick={() => {
                    setTab(t.id);
                    setCopied(false);
                  }}
                  className={`shrink-0 rounded-full px-3 py-1.5 text-[0.8125rem] transition-colors ${
                    t.id === tab ? "bg-white/[0.07] text-[color:var(--text)]" : "text-[color:var(--muted)] hover:text-[color:var(--text)]"
                  }`}
                >
                  {t.label}
                </button>
              ))}
              <button
                type="button"
                onClick={copy}
                className="ml-auto shrink-0 rounded-full border hairline px-3 py-1.5 text-[0.75rem] text-[color:var(--muted)] transition-colors hover:text-[color:var(--text)]"
                aria-live="polite"
              >
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
            <pre className="overflow-x-auto p-5 text-[0.8125rem] leading-7" role="tabpanel">
              <code className="kbd">
                {active.lines.map((line, i) => {
                  const [cmd, comment] = line.split(/\s{2,}#\s/);
                  return (
                    <span key={i} className="block whitespace-pre">
                      <span className="select-none text-verified">$ </span>
                      <span className="text-[color:var(--text)]">{cmd}</span>
                      {comment && <span className="text-[color:var(--dim)]">{`   # ${comment}`}</span>}
                    </span>
                  );
                })}
              </code>
            </pre>
          </div>
        </Reveal>
      </Container>
    </Section>
  );
}
