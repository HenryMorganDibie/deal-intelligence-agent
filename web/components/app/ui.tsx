import Link from "next/link";
import type { ReactNode } from "react";
import type { Deal } from "../../lib/market";

export function usd(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v) || v === 0) return "Undisclosed";
  const a = Math.abs(v);
  const [div, unit] = a >= 1e9 ? [1e9, "bn"] : a >= 1e6 ? [1e6, "m"] : a >= 1e3 ? [1e3, "k"] : [1, ""];
  const n = v / div;
  return `$${n >= 100 || unit === "" ? n.toFixed(0) : n.toFixed(1).replace(/\.0$/, "")}${unit}`;
}

export function num(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "n/a";
  return v.toLocaleString("en-US", { maximumFractionDigits: digits });
}

export function words(s: string | null | undefined): string {
  if (!s) return "";
  const t = s.replace(/_/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}

export function PageHeader({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  return (
    <header className="mb-8">
      <p className="eyebrow">{eyebrow}</p>
      <h1 className="h2 mt-3 text-[1.875rem] sm:text-[2.25rem]">{title}</h1>
      {children && <div className="mt-3 max-w-3xl text-[0.9375rem] leading-relaxed text-[color:var(--muted)]">{children}</div>}
    </header>
  );
}

export function Loading({ label = "Loading..." }: { label?: string }) {
  return (
    <p className="py-6 text-sm text-[color:var(--dim)]" role="status">
      {label}
    </p>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <p className="py-4 text-sm text-risk" role="alert">
      {message}
    </p>
  );
}

const TIER_STYLE: Record<string, string> = {
  low: "text-verified border-[rgba(110,231,200,0.35)]",
  moderate: "text-[#cfe9a8] border-[rgba(207,233,168,0.35)]",
  elevated: "text-[#f5d58a] border-[rgba(245,213,138,0.35)]",
  high: "text-risk border-[rgba(255,143,112,0.4)]",
  severe: "text-[#ff6b6b] border-[rgba(255,107,107,0.5)]",
  A: "text-verified border-[rgba(110,231,200,0.35)]",
  B: "text-[#f5d58a] border-[rgba(245,213,138,0.35)]",
  C: "text-[color:var(--muted)] border-[color:var(--line)]",
  verified: "text-verified border-[rgba(110,231,200,0.35)]",
  inconsistent: "text-risk border-[rgba(255,143,112,0.4)]",
  unchecked: "text-[color:var(--muted)] border-[color:var(--line)]",
};

export function Pill({ value, title }: { value: string | null | undefined; title?: string }) {
  if (!value) return <span className="text-[color:var(--dim)]">n/a</span>;
  return (
    <span
      title={title}
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[0.75rem] ${TIER_STYLE[value] ?? "text-[color:var(--muted)] border-[color:var(--line)]"}`}
    >
      {words(value)}
    </span>
  );
}

export function Stat({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="panel p-4">
      <p className="text-[0.75rem] text-[color:var(--dim)]">{label}</p>
      <p className="mt-1 text-[1.375rem] font-medium tracking-tight">{value}</p>
      {note && <p className="mt-1 text-[0.75rem] text-[color:var(--muted)]">{note}</p>}
    </div>
  );
}

export function Table({ head, children, minWidth = "40rem" }: { head: ReactNode[]; children: ReactNode; minWidth?: string }) {
  return (
    <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
      <table className="w-full border-collapse text-left text-[0.8125rem]" style={{ minWidth }}>
        <thead>
          <tr className="border-b hairline text-[0.75rem] text-[color:var(--dim)]">
            {head.map((h, i) => (
              <th key={i} className="whitespace-nowrap py-2 pr-4 font-normal">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function Td({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <td className={`border-b hairline py-2.5 pr-4 align-top ${className}`}>{children}</td>;
}

export function DealRows({ deals, showWhy = false }: { deals: Deal[]; showWhy?: boolean }) {
  return (
    <Table head={["Date", "Type", "Target", "Buyer / lead / lender", "Amount", "Country", showWhy ? "Similarity" : "Stage"]}>
      {deals.map((d) => (
        <tr key={d.id}>
          <Td className="whitespace-nowrap kbd text-[0.75rem] text-[color:var(--muted)]">{d.announced ?? ""}</Td>
          <Td className="whitespace-nowrap">{words(d.deal_type)}</Td>
          <Td>
            <Link href={`/app/deals/${d.id}`} className="underline-offset-2 hover:underline">
              {d.target ?? "Unnamed"}
            </Link>
            <span className="mt-0.5 block text-[0.75rem] text-[color:var(--dim)]">{d.headline}</span>
          </Td>
          <Td>{d.buyer ?? (d.investors?.[0] || "")}</Td>
          <Td className="whitespace-nowrap">{usd(d.amount_usd)}</Td>
          <Td>{d.country ?? "Pan-African"}</Td>
          <Td className="whitespace-nowrap text-[color:var(--muted)]">
            {showWhy ? `${d.similarity} (${(d.why ?? []).join(", ")})` : words(d.stage)}
          </Td>
        </tr>
      ))}
    </Table>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[0.8125rem] text-[color:var(--muted)]">{label}</span>
      {children}
    </label>
  );
}
