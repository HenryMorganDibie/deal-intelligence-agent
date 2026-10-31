"use client";

import { useState, type FormEvent } from "react";

const ENQUIRY_TYPES = [
  { value: "Demonstration", label: "Product demonstration" },
  { value: "Institutional pilot", label: "Institutional pilot" },
  { value: "Investor or strategic partnership", label: "Investor or strategic partnership" },
  { value: "Data and methodology", label: "Data and methodology" },
  { value: "Other", label: "Something else" },
];

type SubmissionState = "idle" | "sending" | "success" | "error";

export function ContactForm() {
  const [status, setStatus] = useState<SubmissionState>("idle");
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("sending");
    setError("");

    const form = event.currentTarget;
    const formData = new FormData(form);
    const payload = {
      name: String(formData.get("name") ?? ""),
      email: String(formData.get("email") ?? ""),
      organisation: String(formData.get("organisation") ?? ""),
      enquiryType: String(formData.get("enquiryType") ?? ""),
      message: String(formData.get("message") ?? ""),
      website: String(formData.get("website") ?? ""),
    };

    try {
      const response = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = (await response.json()) as { error?: string };

      if (!response.ok) {
        throw new Error(result.error || "We couldn't send your enquiry. Please try again.");
      }

      form.reset();
      setStatus("success");
    } catch (submissionError) {
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "We couldn't send your enquiry. Please try again.",
      );
      setStatus("error");
    }
  }

  const fieldClass =
    "mt-2 w-full rounded-lg border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-white outline-none transition placeholder:text-[color:var(--dim)] focus:border-[color:var(--verified)]";

  return (
    <form onSubmit={handleSubmit} className="panel mt-8 space-y-5 p-6 sm:p-8">
      <div className="grid gap-5 sm:grid-cols-2">
        <label className="block text-sm text-[color:var(--muted)]" htmlFor="contact-name">
          Name
          <input
            id="contact-name"
            name="name"
            autoComplete="name"
            required
            maxLength={100}
            className={fieldClass}
            placeholder="Your name"
          />
        </label>
        <label className="block text-sm text-[color:var(--muted)]" htmlFor="contact-email">
          Work email
          <input
            id="contact-email"
            name="email"
            type="email"
            autoComplete="email"
            required
            maxLength={254}
            className={fieldClass}
            placeholder="you@company.com"
          />
        </label>
      </div>

      <label className="block text-sm text-[color:var(--muted)]" htmlFor="contact-organisation">
        Organisation <span className="text-[color:var(--dim)]">(optional)</span>
        <input
          id="contact-organisation"
          name="organisation"
          autoComplete="organization"
          maxLength={160}
          className={fieldClass}
          placeholder="Company or investment firm"
        />
      </label>

      <label className="block text-sm text-[color:var(--muted)]" htmlFor="contact-enquiry">
        What would you like to discuss?
        <select id="contact-enquiry" name="enquiryType" required defaultValue="Demonstration" className={fieldClass}>
          {ENQUIRY_TYPES.map((item) => (
            <option key={item.value} value={item.value} className="bg-slate-900">
              {item.label}
            </option>
          ))}
        </select>
      </label>

      <label className="block text-sm text-[color:var(--muted)]" htmlFor="contact-message">
        Message
        <textarea
          id="contact-message"
          name="message"
          required
          minLength={10}
          maxLength={5000}
          rows={6}
          className={fieldClass}
          placeholder="Tell us about your coverage needs, research workflow, or what you'd like to explore."
        />
      </label>

      <div className="absolute -left-[10000px] top-auto h-px w-px overflow-hidden" aria-hidden="true">
        <label htmlFor="contact-website">Leave this field empty</label>
        <input id="contact-website" name="website" type="text" tabIndex={-1} autoComplete="off" />
      </div>

      {status === "success" ? (
        <p role="status" className="rounded-lg border border-emerald-400/20 bg-emerald-400/[0.06] p-4 text-sm text-emerald-200">
          Thanks for getting in touch. Your enquiry has been received. We&apos;ll follow up by email.
        </p>
      ) : null}
      {status === "error" ? (
        <p role="alert" className="rounded-lg border border-red-400/20 bg-red-400/[0.06] p-4 text-sm text-red-200">
          {error}
        </p>
      ) : null}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs leading-relaxed text-[color:var(--dim)]">
          Your details are used only to respond to this enquiry.
        </p>
        <button type="submit" disabled={status === "sending"} className="btn btn-primary disabled:cursor-wait disabled:opacity-60">
          {status === "sending" ? "Sending…" : "Send enquiry"}
        </button>
      </div>
    </form>
  );
}
