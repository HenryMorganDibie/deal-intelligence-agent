"use client";

import { useState, type FormEvent } from "react";
import { ApiError } from "../../lib/api";
import { post } from "../../lib/market";

type ResultType = "brief" | "research" | "country_report" | "sector_report";
type Category = "incorrect_signal" | "wrong_company" | "missed_event" | "unsupported_claim" | "outdated_data" | "other";

const CATEGORIES: { value: Category; label: string }[] = [
  { value: "incorrect_signal", label: "Incorrect signal or finding" },
  { value: "wrong_company", label: "Wrong company or attribution" },
  { value: "missed_event", label: "Important event missing" },
  { value: "unsupported_claim", label: "Claim not supported by its sources" },
  { value: "outdated_data", label: "Outdated data" },
  { value: "other", label: "Other issue" },
];

export function ResultFeedback({ resultType, resultId }: { resultType: ResultType; resultId: string }) {
  const [category, setCategory] = useState<Category>("incorrect_signal");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await post("/api/feedback", { result_type: resultType, result_id: resultId, category, note });
      setMessage("Thanks. Your report is saved for review and is not automatically treated as a verified correction.");
      setNote("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit feedback. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  function changeCategory(value: string) {
    const matched = CATEGORIES.find((item) => item.value === value);
    if (matched) setCategory(matched.value);
  }

  return (
    <details className="mt-8 border-t hairline pt-5">
      <summary className="cursor-pointer text-sm font-medium">Report a problem with this result</summary>
      <form onSubmit={submit} className="mt-3 grid gap-3 sm:grid-cols-[1fr_1.5fr_auto] sm:items-start">
        <label className="grid gap-1 text-[0.8125rem] text-[color:var(--muted)]">
          What seems wrong?
          <select value={category} onChange={(e) => changeCategory(e.target.value)} className="field">
            {CATEGORIES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </label>
        <label className="grid gap-1 text-[0.8125rem] text-[color:var(--muted)]">
          Optional note
          <input
            value={note}
            onChange={(e) => setNote(e.target.value.slice(0, 1000))}
            maxLength={1000}
            className="field"
            placeholder="Point us to the specific claim or source"
          />
          <span>Do not include confidential or personal information.</span>
        </label>
        <button type="submit" disabled={busy} className="btn btn-ghost sm:mt-5">
          {busy ? "Sending..." : "Send"}
        </button>
      </form>
      {message && <p role="status" className="mt-2 text-sm text-verified">{message}</p>}
      {error && <p role="alert" className="mt-2 text-sm text-risk">{error}</p>}
    </details>
  );
}
