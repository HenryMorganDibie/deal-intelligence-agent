/** Only paths inside this site's app or account pages; anything else (other hosts, //, schemes) goes to /app. */
export function safeNext(value: string | null | undefined): string {
  if (!value || !/^\/(app|account)(\/|$|\?)/.test(value) || value.startsWith("//") || value.includes("\\")) return "/app";
  return value;
}
