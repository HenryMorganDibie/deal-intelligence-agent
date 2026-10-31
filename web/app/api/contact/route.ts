import { NextResponse } from "next/server";

export const runtime = "nodejs";

const SEND_BYTE_ENDPOINT = "https://api.sendbyte.africa/v1/emails";
const FROM_EMAIL = "Deal Intelligence <info@deal-intelligence.app>";
const CONTACT_EMAIL = "info@deal-intelligence.app";

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => {
    const entities: Record<string, string> = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return entities[character];
  });
}

function clean(value: unknown, maxLength: number): string {
  return typeof value === "string" ? value.trim().slice(0, maxLength) : "";
}

async function sendEmail(apiKey: string, payload: Record<string, string>) {
  const response = await fetch(SEND_BYTE_ENDPOINT, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
    cache: "no-store",
  });

  if (!response.ok) {
    const details = await response.text();
    console.error("SendByte contact email failed:", response.status, details.slice(0, 500));
    throw new Error("Email delivery failed");
  }
}

export async function POST(request: Request) {
  let body: Record<string, unknown>;

  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "Please submit the form again." }, { status: 400 });
  }

  // Quietly discard honeypot submissions without revealing the check.
  if (clean(body.website, 200)) {
    return NextResponse.json({ ok: true });
  }

  const name = clean(body.name, 100);
  const email = clean(body.email, 254);
  const organisation = clean(body.organisation, 160);
  const enquiryType = clean(body.enquiryType, 80);
  const message = clean(body.message, 5000);

  const validEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  const allowedTypes = new Set([
    "Demonstration",
    "Institutional pilot",
    "Investor or strategic partnership",
    "Data and methodology",
    "Other",
  ]);

  if (!name || !validEmail || !allowedTypes.has(enquiryType) || message.length < 10) {
    return NextResponse.json(
      { error: "Please check your name, email address, enquiry type and message." },
      { status: 400 },
    );
  }

  const apiKey = process.env.SENDBYTE_API_KEY;
  if (!apiKey) {
    console.error("SENDBYTE_API_KEY is not configured.");
    return NextResponse.json(
      { error: "The contact form is temporarily unavailable. Please email info@deal-intelligence.app." },
      { status: 503 },
    );
  }

  const safeName = escapeHtml(name);
  const safeEmail = escapeHtml(email);
  const safeOrganisation = escapeHtml(organisation || "Not provided");
  const safeType = escapeHtml(enquiryType);
  const safeMessage = escapeHtml(message).replace(/\r?\n/g, "<br>");

  try {
    await sendEmail(apiKey, {
      from: FROM_EMAIL,
      to: CONTACT_EMAIL,
      subject: `Website enquiry: ${enquiryType}`,
      html: [
        "<h2>New Deal Intelligence website enquiry</h2>",
        `<p><strong>Name:</strong> ${safeName}</p>`,
        `<p><strong>Email:</strong> ${safeEmail}</p>`,
        `<p><strong>Organisation:</strong> ${safeOrganisation}</p>`,
        `<p><strong>Enquiry:</strong> ${safeType}</p>`,
        `<p><strong>Message:</strong><br>${safeMessage}</p>`,
      ].join(""),
    });
  } catch {
    return NextResponse.json(
      { error: "We couldn't send your enquiry just now. Please try again or email info@deal-intelligence.app." },
      { status: 502 },
    );
  }

  // A confirmation is helpful, but should not make a successfully delivered enquiry fail.
  try {
    await sendEmail(apiKey, {
      from: FROM_EMAIL,
      to: email,
      subject: "We received your message | Deal Intelligence",
      html: [
        `<p>Hi ${safeName},</p>`,
        "<p>Thank you for contacting Deal Intelligence. We've received your message and will follow up by email.</p>",
        "<p>Regards,<br>Deal Intelligence</p>",
      ].join(""),
    });
  } catch {
    console.error("The enquiry was delivered, but its confirmation email could not be sent.");
  }

  return NextResponse.json({ ok: true });
}
