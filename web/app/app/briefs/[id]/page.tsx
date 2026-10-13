"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { BriefView } from "../../../../components/app/BriefView";
import { Container } from "../../../../components/primitives";
import type { Brief } from "../../../../lib/brief";
import { supabase } from "../../../../lib/supabase";

type Row = { id: string; company: string; brief: Brief; markdown: string | null };

function download(name: string, type: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  URL.revokeObjectURL(url);
}

export default function BriefPage({ params }: { params: { id: string } }) {
  const router = useRouter();
  const [row, setRow] = useState<Row | null | undefined>(undefined);

  useEffect(() => {
    supabase()
      .from("briefs")
      .select("id, company, brief, markdown")
      .eq("id", params.id)
      .maybeSingle()
      .then(({ data }) => setRow((data as Row | null) ?? null));
  }, [params.id]);

  const slug = row?.company.toLowerCase().replace(/[^a-z0-9]+/g, "-") ?? "brief";

  return (
    <Container className="max-w-4xl py-10 lg:py-14">
      <div className="mb-8 flex flex-wrap items-center justify-between gap-3">
        <Link href="/app" className="text-sm text-[color:var(--muted)] hover:text-[color:var(--text)]">
          ← All briefs
        </Link>
        {row && (
          <div className="flex flex-wrap gap-2">
            {row.markdown && (
              <button
                type="button"
                className="btn btn-ghost h-8 px-3 text-[0.8125rem]"
                onClick={() => download(`${slug}-brief.md`, "text/markdown", row.markdown!)}
              >
                Markdown
              </button>
            )}
            <button
              type="button"
              className="btn btn-ghost h-8 px-3 text-[0.8125rem]"
              onClick={() => download(`${slug}-brief.json`, "application/json", JSON.stringify(row.brief, null, 2))}
            >
              JSON
            </button>
            <button
              type="button"
              className="btn btn-ghost h-8 px-3 text-[0.8125rem] hover:text-risk"
              onClick={async () => {
                if (!window.confirm("Delete this brief? This cannot be undone.")) return;
                await supabase().from("briefs").delete().eq("id", row.id);
                router.replace("/app");
              }}
            >
              Delete
            </button>
          </div>
        )}
      </div>

      {row === undefined ? (
        <p className="kbd text-[color:var(--muted)]">Loading...</p>
      ) : row === null ? (
        <div>
          <h1 className="h3 text-xl">Brief not found</h1>
          <p className="mt-2 text-sm text-[color:var(--muted)]">It may have been deleted, or it belongs to another account.</p>
        </div>
      ) : (
        <BriefView brief={row.brief} />
      )}
    </Container>
  );
}
