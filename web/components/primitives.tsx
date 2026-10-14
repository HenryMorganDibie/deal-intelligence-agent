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

export function LogoMark({ className = "h-6 w-6" }: { className?: string }) {
  return (
    <svg aria-hidden viewBox="0 0 24 24" className={className} fill="none">
      <rect x="1.5" y="1.5" width="21" height="21" rx="6" stroke="rgba(255,255,255,0.18)" />
      <path d="M6 15.5h4.5l2-6 2.5 9 2-4H19" stroke="#6ee7c8" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
