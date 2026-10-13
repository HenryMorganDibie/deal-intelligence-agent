import type { CSSProperties, ReactNode } from "react";

/** Horizontal page container shared by every section. */
export function Container({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`mx-auto w-full max-w-page px-4 sm:px-6 lg:px-8 ${className}`}>{children}</div>;
}

/** A page section: separated by a hairline and a consistent vertical rhythm. */
export function Section({
  id,
  labelledBy,
  children,
  className = "",
  bordered = true,
}: {
  id?: string;
  labelledBy?: string;
  children: ReactNode;
  className?: string;
  bordered?: boolean;
}) {
  return (
    <section
      id={id}
      aria-labelledby={labelledBy}
      className={`relative py-24 sm:py-32 ${bordered ? "border-t hairline" : ""} ${className}`}
    >
      {children}
    </section>
  );
}

/** Mono section index + label, e.g. "02 / The problem". */
export function Eyebrow({ index, children, className = "" }: { index?: string; children: ReactNode; className?: string }) {
  return (
    <p className={`eyebrow flex items-center gap-3 ${className}`}>
      {index && <span className="text-[color:var(--dim)]">{index}</span>}
      {index && <span aria-hidden className="h-px w-6 bg-white/15" />}
      <span>{children}</span>
    </p>
  );
}

/** Marks content for the scroll-reveal observer. */
export function Reveal({
  children,
  delay = 0,
  className = "",
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  return (
    // min-w-0: as a grid/flex child, never let long or truncated content widen the track.
    <div data-reveal className={`min-w-0 ${className}`} style={{ "--reveal-delay": `${delay}ms` } as CSSProperties}>
      {children}
    </div>
  );
}

/** Small dashed label, e.g. "Live run" or "Illustrative". */
export function Tag({ children, dot = "bg-white/40" }: { children: ReactNode; dot?: string }) {
  return (
    <span className="tag">
      <span aria-hidden className={`h-1 w-1 rounded-full ${dot}`} />
      {children}
    </span>
  );
}

/** Section heading block: eyebrow, h2 and an optional lede. */
export function Heading({
  index,
  eyebrow,
  id,
  title,
  lede,
  className = "",
}: {
  index: string;
  eyebrow: string;
  id: string;
  title: ReactNode;
  lede?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`max-w-3xl ${className}`}>
      <Reveal>
        <Eyebrow index={index}>{eyebrow}</Eyebrow>
      </Reveal>
      <Reveal delay={60}>
        <h2 id={id} className="h2 mt-5">
          {title}
        </h2>
      </Reveal>
      {lede && (
        <Reveal delay={120}>
          <p className="lede mt-6 max-w-2xl">{lede}</p>
        </Reveal>
      )}
    </div>
  );
}

export function ArrowRight({ className = "" }: { className?: string }) {
  return (
    <svg aria-hidden viewBox="0 0 16 16" className={`arrow h-4 w-4 ${className}`} fill="none">
      <path d="M3 8h10m0 0L9 4m4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function GitHubMark({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg aria-hidden viewBox="0 0 16 16" className={className} fill="currentColor">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}

/** Logo mark: a ledger line crossing a verified tick. */
export function LogoMark({ className = "h-6 w-6" }: { className?: string }) {
  return (
    <svg aria-hidden viewBox="0 0 24 24" className={className} fill="none">
      <rect x="1.5" y="1.5" width="21" height="21" rx="6" stroke="rgba(255,255,255,0.18)" />
      <path d="M6 15.5h4.5l2-6 2.5 9 2-4H19" stroke="#6ee7c8" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
