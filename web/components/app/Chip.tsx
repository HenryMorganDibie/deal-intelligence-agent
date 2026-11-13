import type { ReactNode } from "react";

/** A toggle chip: a filter you switch on or off, shown filled when on. */
export function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-[0.8125rem] transition-colors ${
        on
          ? "border-[color:var(--verified,#6ee7c8)] bg-white/[0.08] text-[color:var(--text)]"
          : "hairline text-[color:var(--muted)] hover:text-[color:var(--text)]"
      }`}
    >
      {children}
    </button>
  );
}

/** A two-or-more option switch, for small choices such as daily or weekly. */
export function Segmented<T extends string>({ value, options, onChange, label }: {
  value: T; options: [T, string][]; onChange: (v: T) => void; label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-full border hairline p-0.5">
      {options.map(([v, text]) => (
        <button key={v} type="button" role="radio" aria-checked={value === v} onClick={() => onChange(v)}
                className={`rounded-full px-3.5 py-1 text-[0.8125rem] transition-colors ${
                  value === v ? "bg-white/[0.09] text-[color:var(--text)]" : "text-[color:var(--muted)] hover:text-[color:var(--text)]"}`}>
          {text}
        </button>
      ))}
    </div>
  );
}
