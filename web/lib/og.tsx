import type { ReactNode } from "react";
import { API_CONFIGURED, apiHeaders, apiUrl } from "./api-base";

/* Shared pieces for the link-preview cards (1200x630): the brand frame, fonts and a timed API fetch, so each post's
 * card looks like the same publication while showing its own figures. */

export const OG_SIZE = { width: 1200, height: 630 };
export const SITE = process.env.NEXT_PUBLIC_SITE_URL?.trim().replace(/^https?:\/\//, "").replace(/\/$/, "") || "deal-intelligence.app";
export const C = { bg: "#07080a", panel: "#0e1013", line: "rgba(255,255,255,0.10)", text: "#f2efe8", muted: "#9a9a96",
  faint: "#6b6b68", accent: "#6ee7c8", down: "#f59e8b" };

export async function ogJson<T>(path: string, ms = 2500): Promise<T | null> {
  if (!API_CONFIGURED) return null;
  try {
    const r = await fetch(apiUrl(path), { headers: apiHeaders(), next: { revalidate: 3600 }, signal: AbortSignal.timeout(ms) });
    return r.ok ? ((await r.json()) as T) : null;
  } catch {
    return null;
  }
}

async function font(family: string, weight: number): Promise<ArrayBuffer | null> {
  try {
    const css = await (await fetch(`https://fonts.googleapis.com/css2?family=${family}:wght@${weight}`, { signal: AbortSignal.timeout(1500) })).text();
    const src = css.match(/src: url\((.+?)\) format\('(opentype|truetype)'\)/)?.[1];
    return src ? await (await fetch(src, { signal: AbortSignal.timeout(1500) })).arrayBuffer() : null;
  } catch {
    return null;
  }
}

export async function ogFonts() {
  const [display, body] = await Promise.all([font("Inter+Tight", 600), font("Inter", 400)]);
  return [
    ...(display ? [{ name: "Display", data: display, weight: 600 as const, style: "normal" as const }] : []),
    ...(body ? [{ name: "Body", data: body, weight: 400 as const, style: "normal" as const }] : []),
  ];
}

export function dayLabel(day: string | undefined): string | null {
  if (!day || !/^\d{4}-\d{2}-\d{2}$/.test(day)) return null;
  const d = new Date(`${day}T00:00:00Z`);
  return isNaN(d.getTime()) ? null : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

/** The card: brand and a topic pill on top, a title, the post's own body, and the page address at the foot. */
export function Frame({ pill, title, body, foot }: { pill: string; title: string; body: ReactNode; foot: string }) {
  return (
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", background: C.bg, color: C.text,
      fontFamily: "Body", padding: "50px 64px", backgroundImage: "radial-gradient(circle at 85% -10%, rgba(110,231,200,0.18), transparent 55%)" }}>
      <div style={{ display: "flex", alignItems: "center" }}>
        <div style={{ width: 40, height: 40, borderRadius: 10, border: `1px solid ${C.line}`, background: C.panel, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M2 13h4l2.5-6 4 11 3-8 1.5 3H22" stroke={C.accent} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <div style={{ display: "flex", marginLeft: 14, fontFamily: "Display", fontSize: 26, fontWeight: 600 }}>Deal Intelligence</div>
        <div style={{ display: "flex", marginLeft: "auto", fontSize: 20, padding: "8px 18px", borderRadius: 999,
          border: "1px solid rgba(110,231,200,0.45)", color: C.accent, letterSpacing: 1 }}>{pill.toUpperCase()}</div>
      </div>
      <div style={{ display: "flex", marginTop: 30, fontFamily: "Display", fontSize: 50, fontWeight: 600, letterSpacing: -1.5, lineHeight: 1.05 }}>{title}</div>
      <div style={{ display: "flex", flexDirection: "column", marginTop: 22, flexGrow: 1 }}>{body}</div>
      <div style={{ display: "flex", fontSize: 20, color: C.faint }}>{foot}</div>
    </div>
  );
}

/** A list row: a name on the left, a figure on the right, optionally coloured by direction. */
export function Row({ name, note, value, tone, max = 30 }: { name: string; note?: string; value: string; tone?: "up" | "down" | "plain"; max?: number }) {
  name = name.length > max ? `${name.slice(0, max - 1).trimEnd()}…` : name;
  const color = tone === "up" ? C.accent : tone === "down" ? C.down : C.text;
  return (
    <div style={{ display: "flex", alignItems: "center", padding: "12px 0", borderBottom: `1px solid ${C.line}` }}>
      <div style={{ display: "flex", flexDirection: "column", flexGrow: 1 }}>
        <div style={{ display: "flex", fontFamily: "Display", fontSize: 30, fontWeight: 600 }}>{name}</div>
        {note ? <div style={{ display: "flex", fontSize: 19, color: C.muted, marginTop: 2 }}>{note}</div> : null}
      </div>
      <div style={{ display: "flex", fontFamily: "Display", fontSize: 34, fontWeight: 600, color }}>{value}</div>
    </div>
  );
}
