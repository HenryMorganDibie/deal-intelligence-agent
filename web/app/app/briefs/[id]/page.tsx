"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { BriefView } from "../../../../components/app/BriefView";
import { Container } from "../../../../components/primitives";
import { ApiError, getBrief, type StoredBrief } from "../../../../lib/api";
import { addToHistory, readHistory, removeFromHistory } from "../../../../lib/history";

function download(name: string, type: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  URL.revokeObjectURL(url);
}

export default function BriefPage({ params }: { params: { id: string } }) {
  const [row, setRow] = useState<StoredBrief | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [inList, setInList] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    getBrief(params.id)
      .then((b) => {
        setRow(b);
        setInList(readHistory().some((h) => h.id === b.id));
      })
      .catch((err) => {
        setRow(null);
        setError(err instanceof ApiError && err.status !== 404 ? err.message : null);
      });
  }, [params.id]);

  const slug = row?.company.toLowerCase().replace(/[^a-z0-9]+/g, "-") ?? "brief";
  const btn = "btn btn-ghost h-8 px-3 text-[0.8125rem]";

  return (
    <Container className="max-w-4xl py-10 lg:py-14">
      <div className="mb-8 flex flex-wrap items-center justify-between gap-3">
        <Link href="/app" className="text-sm text-[color:var(--muted)] hover:text-[color:var(--text)]">
          ← All briefs
        </Link>
        {row && (
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className={btn}
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(window.location.href);
                  setCopied(true);
                  window.setTimeout(() => setCopied(false), 1600);
                } catch {
                  setCopied(false);
                }
              }}
            >
              {copied ? "Link copied" : "Share link"}
            </button>
            {row.markdown && (
              <button type="button" className={btn} onClick={() => download(`${slug}-brief.md`, "text/markdown", row.markdown!)}>
                Markdown
              </button>
            )}
            <button
              type="button"
              className={btn}
              onClick={() => download(`${slug}-brief.json`, "application/json", JSON.stringify(row.brief, null, 2))}
            >
              JSON
            </button>
            <button
              type="button"
              className={btn}
              onClick={() => {
                if (inList) {
                  removeFromHistory(row.id);
                } else {
                  addToHistory({
                    id: row.id,
                    company: row.company,
                    ticker: row.ticker,
                    severity: row.brief.overall_severity,
                    signal_count: row.brief.detected_signals?.length ?? 0,
                    created_at: row.created_at,
                  });
                }
                setInList(!inList);
              }}
            >
              {inList ? "Remove from my list" : "Save to my list"}
            </button>
          </div>
        )}
      </div>

      {row === undefined ? (
        <p className="kbd text-[color:var(--muted)]">Loading...</p>
      ) : row === null ? (
        <div>
          <h1 className="h3 text-xl">{error ? "Could not load this brief" : "Brief not found"}</h1>
          <p className="mt-2 text-sm text-[color:var(--muted)]">{error ?? "Check the link and try again."}</p>
        </div>
      ) : (
        <BriefView brief={row.brief} resultId={row.id} />
      )}
    </Container>
  );
}
