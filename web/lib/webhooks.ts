// Mirrors src/engines/chat_formats.destination: which chat tool a webhook URL belongs to, so the form can say how
// alerts will look there. The server decides the real format; this is only the label.
export type Destination = "slack" | "teams" | "discord" | "google_chat" | "json";

export const DESTINATION_LABEL: Record<Destination, string> = {
  slack: "Slack",
  teams: "Microsoft Teams",
  discord: "Discord",
  google_chat: "Google Chat",
  json: "JSON webhook (Zapier, Make, n8n or your own server)",
};

const TEAMS_HOSTS = [".webhook.office.com", ".logic.azure.com", ".powerplatform.com", ".powerautomate.com"];

export function webhookDestination(raw: string): Destination | null {
  let url: URL;
  try {
    url = new URL(raw.trim());
  } catch {
    return null;
  }
  if (url.protocol !== "https:") return null;
  const host = url.hostname.toLowerCase();
  if (host === "hooks.slack.com") return "slack";
  if (["discord.com", "discordapp.com", "ptb.discord.com", "canary.discord.com"].includes(host) && url.pathname.startsWith("/api/webhooks/")) return "discord";
  if (host === "chat.googleapis.com") return "google_chat";
  if (TEAMS_HOSTS.some((h) => host.endsWith(h))) return "teams";
  return "json";
}
