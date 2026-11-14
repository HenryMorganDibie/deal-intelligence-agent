/** A return path after sign-in: a page on this site only; anything else goes to the home page. */
export function safeNext(value: string | null | undefined): string {
  // A page on this site: a path, never another origin ("//host"), a backslash trick or an API route.
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\") || /^\/api(\/|$|\?)/.test(value)) return "/";
  return value;
}
