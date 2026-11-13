import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import { PublicPage } from "../../components/PublicPage";
import { Container } from "../../components/primitives";
import { CONTACT_EMAIL, PUBLIC_API_BASE } from "../../lib/site";

export const metadata: Metadata = {
  title: "API and integrations | Deal Intelligence",
  description: "REST API for African deals, corporate events, investors, countries and market prices, plus watchlist alerts in Slack, Microsoft Teams, Discord and Google Chat.",
};

const PLANS: [string, string, string][] = [
  ["Free", "30 requests a month", "2 keys"],
  ["Pro", "3,000 requests a month", "5 keys"],
  ["Team", "15,000 requests a month", "10 keys"],
  ["Institutional", "100,000 requests a month", "25 keys"],
];

const ENDPOINTS: [string, string, string][] = [
  ["/usage", "This month's allowance and use. Not counted.", ""],
  ["/deals", "Search deals, newest and most relevant first.", "q, country, type, sector, investor, since, until, min_usd, limit (≤100), offset"],
  ["/deals/{id}", "One deal with its sources, verification, parties and comparable deals.", ""],
  ["/events", "Corporate events (M&A, credit, distress, leadership, regulatory and more).", "country, type, since, q, limit (≤200), offset"],
  ["/investors", "Investors ranked on the deals that match the filters.", "role, kind, sector, country, stage, type, since, until, min_usd, max_usd, lead_only, limit, offset"],
  ["/investors/{name}", "An investor's profile, portfolio and fund lifecycle.", ""],
  ["/countries", "Deal and event activity and risk for all 54 African countries.", ""],
  ["/countries/{code}", "One country in detail (ISO code, e.g. NG, KE, ZA).", ""],
  ["/markets/overview", "Exchanges, movers, most traded and currency moves.", ""],
  ["/markets/screener", "Listed shares across African exchanges, filtered and sorted.", "exchange, sector, min_mcap_usd, q, sort, include_stale, limit (≤200), offset"],
  ["/markets/search", "Find a listing by company name or ticker.", "q (required), limit (≤25)"],
  ["/markets/quote", "Latest price for one listing.", "exchange, symbol (both required)"],
];

// Nigeria's 2027 general election. [method, path, what, params]
const ELECTION_ENDPOINTS: [string, string, string, string][] = [
  ["GET", "/elections/news", "Election coverage from Nigerian outlets, one record per story with every outlet's report, tagged by candidate, party, state, LGA, topic, race and any incident.", "candidate, party, state, lga, topic, race, q, since, limit (≤200), offset"],
  ["GET", "/elections/summary", "Coverage counts per candidate, party, state, LGA, topic, race and incident type.", "days (≤90)"],
  ["GET", "/elections/incidents", "Incidents reported in the news (violence, thuggery, abduction, arson, ballot snatching, vote buying, intimidation, BVAS or IReV failures, logistics, arrests, hate speech) with severity and location.", "state, lga, type, severity (low, medium, high: the minimum), since, limit (≤200), offset"],
  ["GET", "/elections/areas", "INEC's delimitation one level at a time: the states; a state's LGAs; an LGA's wards, with polling-unit counts.", "state (code or name), lga (code)"],
  ["GET", "/elections/polling-units", "Polling units in a ward, or matching a name.", "state, lga, ward (codes), or q (3+ letters); limit (≤500), offset"],
  ["GET", "/elections/polling-units/{code}", "One polling unit by INEC code, e.g. 24/11/01/001.", ""],
];

const RESULTS_ENDPOINTS: [string, string, string, string][] = [
  ["POST", "/elections/results/sheets", "Submit a polling-unit result sheet (Form EC8A) as a base64 image (JPEG, PNG or WebP, ≤3 MB) or an https link. It is read, checked and stored as provisional (every check passed) or needs_review.", "JSON: election, pu_code, image_base64 + content_type, or image_url"],
  ["GET", "/elections/results/sheets", "Your submitted sheets, newest first; status=needs_review is the review queue.", "election, state, lga, ward, status, limit (≤200), offset"],
  ["POST", "/elections/results/sheets/{id}/review", "Verify, reject or return a sheet to review, with corrections. A sheet that fails its checks cannot be verified.", "JSON: status, corrections {figures, votes}"],
  ["GET", "/elections/results", "Votes by party for the country, a state, an LGA or a ward, broken down one level below, with coverage and turnout.", "election, state, lga, ward, verified_only"],
  ["GET", "/elections/accreditation", "Registered and accredited voters, turnout and sheet coverage at the same levels.", "election, state, lga, ward, verified_only"],
  ["POST", "/elections/alerts", "Push incidents (or coverage) to Slack, Teams, Discord, Google Chat or a JSON webhook as they are collected. Each story is sent once; up to 10 alerts per account.", "JSON: name, webhook_url, filters {kind: incidents | news, min_severity, states, lgas, incident_types, candidates, parties, topics}"],
  ["GET", "/elections/alerts", "Your election alerts and how many stories each has sent.", ""],
  ["POST", "/elections/alerts/{id}/test", "Send a clearly marked sample to the alert's webhook.", ""],
  ["DELETE", "/elections/alerts/{id}", "Remove an alert.", ""],
];

function EndpointList({ rows, ink }: { rows: [string, string, string, string][]; ink: string }) {
  return (
    <div className="divide-y divide-white/[0.07] border-y hairline">
      {rows.map(([method, path, what, params]) => (
        <div key={method + path} className="grid gap-1 py-3 sm:grid-cols-[17rem_1fr] sm:gap-4">
          <span className={`kbd break-all text-[0.8125rem] ${ink}`}>{method === "GET" ? "" : `${method} `}/v1{path}</span>
          <div>
            <p>{what}</p>
            {params && <p className="kbd mt-1 text-[0.75rem] text-[color:var(--dim)]">{params}</p>}
          </div>
        </div>
      ))}
    </div>
  );
}

const ERRORS: [string, string, string][] = [
  ["400", "bad_request", "A parameter is malformed, such as a polling-unit code or an image."],
  ["401", "missing_key / invalid_key", "No key, a mistyped key, or a revoked key."],
  ["403", "plan_required", "The endpoint is part of a higher plan (election results and accreditation: Institutional)."],
  ["404", "not_found", "The deal, investor or listing does not exist."],
  ["422", "invalid_request", "A parameter is out of range or missing."],
  ["429", "quota_exceeded", "The month's allowance is used. Retry-After says when it resets."],
  ["503", "unavailable", "A temporary problem on our side. Retry after the Retry-After seconds."],
];

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className="border-t hairline py-10" aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`} className="h3 text-[1.375rem]">{title}</h2>
      <div className="mt-4 space-y-4 text-[0.9375rem] leading-relaxed text-[color:var(--muted)]">{children}</div>
    </section>
  );
}

function Code({ children }: { children: string }) {
  return <pre className="kbd overflow-x-auto rounded-lg border hairline bg-white/[0.02] p-4 text-[0.8125rem] leading-relaxed text-[color:var(--text)]">{children}</pre>;
}

const ink = "text-[color:var(--text)]";

export default function DevelopersPage() {
  return (
    <PublicPage>
      <Container className="max-w-4xl pb-20 pt-28">
        <p className="eyebrow">API and integrations</p>
        <h1 className="h2 mt-3">Deal Intelligence in your own tools.</h1>
        <p className="lede mt-5 max-w-3xl">
          A REST API for African deals, corporate events, investors, countries and market prices, and watchlist alerts
          delivered to Slack, Microsoft Teams, Discord, Google Chat or any webhook. Create a key on the{" "}
          <Link href="/app/api" className="underline">API keys page</Link> once you have an account.
        </p>
        <p className="mt-6 max-w-3xl rounded-xl border border-verified/30 bg-verified/[0.06] px-4 py-3 text-[0.875rem] leading-relaxed" role="note">
          <span className="font-medium text-[color:var(--text)]">Start free with 30 requests a month.</span>{" "}
          <span className="text-[color:var(--muted)]">Pro (3,000) and Team (15,000) are priced in naira on the{" "}
            <Link href="/pricing" className="underline">pricing page</Link>; subscribe now and keep the founding price while you stay subscribed.</span>
        </p>
        <nav aria-label="On this page" className="mt-8 flex flex-wrap gap-2 text-sm">
          {[["#start", "Quick start"], ["#plans", "Plans"], ["#endpoints", "Endpoints"], ["#elections", "Elections"], ["#errors", "Errors"], ["#chat", "Slack, Teams and chat"], ["#webhooks", "Webhook payload"]].map(([href, label]) => (
            <a key={href} href={href} className="rounded-full border hairline px-3 py-1.5 text-[color:var(--muted)] hover:text-[color:var(--text)]">{label}</a>
          ))}
        </nav>

        <Section id="start" title="Quick start">
          <p>Send your key in the <span className={`kbd ${ink}`}>Authorization</span> header (or <span className={`kbd ${ink}`}>X-API-Key</span>). Every response is JSON.</p>
          <Code>{`curl "${PUBLIC_API_BASE}/deals?country=KE&type=equity_funding&limit=5" \\
  -H "Authorization: Bearer di_live_..."`}</Code>
          <Code>{`import requests

r = requests.get("${PUBLIC_API_BASE}/events",
                 params={"country": "NG", "type": "m_and_a_activity", "limit": 20},
                 headers={"Authorization": "Bearer di_live_..."})
r.raise_for_status()
print(r.headers["X-RateLimit-Remaining"], "requests left this month")
for e in r.json()["events"]:
    print(e["day"], e["headline"])`}</Code>
          <p>Keys belong on servers and in your tools&apos; secret settings. Never put a key in a web page, a public repository or a chat message: anyone with it can use your allowance. Revoke a leaked key on the API keys page and create a new one.</p>
        </Section>

        <Section id="plans" title="Plans and limits">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-[color:var(--dim)]"><tr><th className="py-2 pr-4 font-normal">Plan</th><th className="py-2 pr-4 font-normal">Allowance</th><th className="py-2 font-normal">Keys</th></tr></thead>
              <tbody>{PLANS.map(([p, a, k]) => <tr key={p} className="border-t hairline"><td className={`py-2 pr-4 ${ink}`}>{p}</td><td className="py-2 pr-4">{a}</td><td className="py-2">{k}</td></tr>)}</tbody>
            </table>
          </div>
          <p>Every request made with a key counts, whatever its result, except <span className={`kbd ${ink}`}>/v1/usage</span>. Usage is per account and shared by all its keys. The allowance resets on the 1st of each month (UTC). Each response carries <span className={`kbd ${ink}`}>X-RateLimit-Limit</span>, <span className={`kbd ${ink}`}>X-RateLimit-Remaining</span> and <span className={`kbd ${ink}`}>X-RateLimit-Reset</span> (Unix time). Bursts above 120 requests a minute from one address are slowed down.</p>
          <p>
            Need more than 30 requests a month? Upgrade to Pro or Team on the{" "}
            <Link href="/pricing" className="underline">pricing page</Link>. For Institutional volumes, write to{" "}
            <a href={`mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent("Institutional API access")}`} className="underline">{CONTACT_EMAIL}</a>.
          </p>
        </Section>

        <Section id="endpoints" title="Endpoints">
          <p>All endpoints are <span className={`kbd ${ink}`}>GET</span> (except the election endpoints marked POST or DELETE) under <span className={`kbd ${ink}`}>{PUBLIC_API_BASE}</span>. Dates are <span className="kbd">YYYY-MM-DD</span>; countries take ISO codes or names; list endpoints page with <span className="kbd">limit</span> and <span className="kbd">offset</span>.</p>
          <p>Deal <span className="kbd">type</span>: acquisition, merger, equity_funding, debt_financing, fund_raise, exit, ipo, joint_venture. Event <span className="kbd">type</span>: m_and_a_activity, credit_risk, distressed_asset, earnings_surprise, leadership_change, regulatory_action, debt_restructuring, insider_activity.</p>
          <div className="divide-y divide-white/[0.07] border-y hairline">
            {ENDPOINTS.map(([path, what, params]) => (
              <div key={path} className="grid gap-1 py-3 sm:grid-cols-[13rem_1fr] sm:gap-4">
                <span className={`kbd text-[0.8125rem] ${ink}`}>/v1{path}</span>
                <div>
                  <p>{what}</p>
                  {params && <p className="kbd mt-1 text-[0.75rem] text-[color:var(--dim)]">{params}</p>}
                </div>
              </div>
            ))}
          </div>
        </Section>

        <Section id="elections" title="Nigeria 2027 elections">
          <p>Election intelligence for the presidential and National Assembly elections on 16 January 2027 and the governorship and state assembly elections on 6 February 2027. Coverage is collected hourly from Nigerian publishers&apos; own feeds and tagged by rules, so every tag traces to the words that produced it. Candidates are the 18 presidential tickets on INEC&apos;s final list; polling units follow INEC&apos;s delimitation (37 states, 774 LGAs, 8,809 wards, 176,623 polling units).</p>
          <p className={ink}>Every plan</p>
          <EndpointList rows={ELECTION_ENDPOINTS} ink={ink} />
          <p className={ink}>Results, accreditation and alerts (Institutional)</p>
          <p>Elections: <span className="kbd">presidential-2027</span>, <span className="kbd">senate-2027</span>, <span className="kbd">reps-2027</span>, <span className="kbd">governorship-2027</span>, <span className="kbd">state-assembly-2027</span>. Each sheet is checked: party votes against valid votes, valid plus rejected against votes cast, votes cast against accredited and registered voters, ballots reconciled, figures against words, and the code against INEC&apos;s list. Totals count one sheet per polling unit, verified first, else the latest provisional one. Sheets, reviews and totals belong to your account alone: no other account can see them, and they never count in anyone else&apos;s figures. Images are not stored.</p>
          <EndpointList rows={RESULTS_ENDPOINTS} ink={ink} />
        </Section>

        <Section id="errors" title="Errors">
          <p>Errors share one shape: <span className={`kbd ${ink}`}>{`{"error": {"code": "...", "message": "...", "docs": "..."}}`}</span></p>
          <div className="divide-y divide-white/[0.07] border-y hairline">
            {ERRORS.map(([status, code, meaning]) => (
              <div key={status} className="grid gap-1 py-3 sm:grid-cols-[4rem_14rem_1fr] sm:gap-4">
                <span className={`kbd ${ink}`}>{status}</span><span className="kbd text-[0.8125rem]">{code}</span><span>{meaning}</span>
              </div>
            ))}
          </div>
        </Section>

        <Section id="chat" title="Alerts in Slack, Teams, Discord and Google Chat">
          <p>Create a watchlist on the <Link href="/app/watchlists" className="underline">Alerts</Link> page and paste the channel&apos;s webhook URL. The format is chosen from the URL, and <span className={ink}>Send test message</span> shows what alerts will look like before you save. Alerts arrive daily after each update, or as a Friday digest. Chat delivery does not use your API allowance.</p>
          <ol className="list-decimal space-y-3 pl-5">
            <li><span className={ink}>Slack:</span> at api.slack.com/apps create an app, turn on <em>Incoming Webhooks</em>, choose <em>Add New Webhook to Workspace</em>, pick the channel and copy the URL (starts with https://hooks.slack.com/).</li>
            <li><span className={ink}>Microsoft Teams:</span> in the channel open <em>Workflows</em> and choose the template <em>Post to a channel when a webhook request is received</em>. Finish the steps and copy the URL it gives you.</li>
            <li><span className={ink}>Discord:</span> Channel settings, <em>Integrations</em>, <em>Webhooks</em>, <em>New Webhook</em>, then <em>Copy Webhook URL</em>.</li>
            <li><span className={ink}>Google Chat:</span> in the space open <em>Apps and integrations</em>, <em>Webhooks</em>, add one and copy its URL.</li>
            <li><span className={ink}>Zapier, Make, n8n or your own server:</span> use any HTTPS webhook URL. It receives the JSON payload below, so you can route alerts to email, a CRM, a spreadsheet or anywhere else.</li>
          </ol>
          <p>Treat a webhook URL like a password: anyone with it can post into that channel.</p>
        </Section>

        <Section id="webhooks" title="Webhook payload">
          <p>Webhooks that are not a chat tool receive this JSON as a POST. The <span className="kbd">Idempotency-Key</span> header is the same on retries of the same batch, so you can ignore repeats.</p>
          <Code>{`{
  "watchlist": {"id": "...", "name": "Nigerian fintech", "url": "https://deal-intelligence.app/app/watchlists/..."},
  "generated_at": "2026-11-09T06:30:00+00:00",
  "alerts": [
    {"kind": "deal", "id": "...", "day": "2026-11-08", "title": "...",
     "deal_type": "equity_funding", "amount_usd": 12000000,
     "url": "https://...", "publisher": "TechCabal",
     "why": ["company: Moniepoint"], "change_type": "new"}
  ]
}`}</Code>
        </Section>
      </Container>
    </PublicPage>
  );
}
