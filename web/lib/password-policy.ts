// Password and username rules, shared by the sign-up form (live checklist) and the server (enforcement).

export const USERNAME_RE = /^[a-z0-9][a-z0-9_]{1,18}[a-z0-9]$/;
export const PASSWORD_MIN = 12;
export const PASSWORD_MAX = 128;

// The most common passwords and patterns; the server also checks the full breached-password corpus.
const COMMON = [
  "password", "passw0rd", "123456", "12345678", "123456789", "qwerty", "qwertyuiop", "abc123", "letmein", "welcome",
  "iloveyou", "admin", "monkey", "dragon", "football", "baseball", "sunshine", "princess", "trustno1", "master",
  "superman", "starwars", "whatever", "freedom", "shadow", "michael", "jennifer", "nigeria", "lagos", "kenya",
  "nairobi", "africa", "dealintelligence",
];

export type PasswordContext = { email?: string; username?: string };
export type PasswordCheck = { id: string; label: string; ok: boolean };

function personalParts(ctx: PasswordContext): string[] {
  const local = (ctx.email || "").split("@")[0]?.toLowerCase() ?? "";
  return [local, (ctx.username || "").toLowerCase()].filter((p) => p.length >= 3);
}

export function passwordChecks(password: string, ctx: PasswordContext = {}): PasswordCheck[] {
  const lower = password.toLowerCase();
  const squashed = lower.replace(/[^a-z0-9]/g, "");
  return [
    { id: "length", label: `At least ${PASSWORD_MIN} characters`, ok: password.length >= PASSWORD_MIN && password.length <= PASSWORD_MAX },
    { id: "lower", label: "A lowercase letter", ok: /[a-z]/.test(password) },
    { id: "upper", label: "A capital letter", ok: /[A-Z]/.test(password) },
    { id: "digit", label: "A number", ok: /\d/.test(password) },
    { id: "symbol", label: "A symbol, such as ! ? # or %", ok: /[^A-Za-z0-9]/.test(password) },
    { id: "repeat", label: "No character repeated 4 times in a row", ok: !/(.)\1{3,}/.test(password) },
    { id: "personal", label: "Does not contain your username or email", ok: !personalParts(ctx).some((p) => lower.includes(p)) },
    { id: "common", label: "Not a common password", ok: !COMMON.some((c) => squashed.includes(c)) },
  ];
}

/** The rules a password breaks, as user-facing sentences; empty when it passes. */
export function passwordProblems(password: string, ctx: PasswordContext = {}): string[] {
  if (password.length > PASSWORD_MAX) return [`Use at most ${PASSWORD_MAX} characters.`];
  return passwordChecks(password, ctx).filter((c) => !c.ok).map((c) => c.label);
}

/** 0 (very weak) to 4 (very strong): the rules passed, then length beyond the minimum and character variety. */
export function passwordStrength(password: string, ctx: PasswordContext = {}): { score: 0 | 1 | 2 | 3 | 4; label: string } {
  if (!password) return { score: 0, label: "" };
  const checks = passwordChecks(password, ctx);
  const failed = checks.filter((c) => !c.ok).length;
  const variety = ["lower", "upper", "digit", "symbol"].filter((id) => checks.find((c) => c.id === id)?.ok).length;
  let score: 0 | 1 | 2 | 3 | 4;
  if (failed >= 3) score = 0;
  else if (failed > 0) score = 1;
  else if (password.length >= 20 && variety === 4) score = 4;
  else if (password.length >= 16) score = 3;
  else score = 2;
  return { score, label: ["Very weak", "Weak", "Good", "Strong", "Very strong"][score] };
}

export function normaliseUsername(value: string): string {
  return value.trim().toLowerCase();
}

export function usernameProblem(value: string): string | null {
  const u = normaliseUsername(value);
  if (u.length < 3 || u.length > 20) return "Use 3 to 20 characters.";
  if (!USERNAME_RE.test(u)) return "Use letters, numbers and underscores, starting and ending with a letter or number.";
  return null;
}

export function displayNameProblem(value: string): string | null {
  const n = value.trim();
  if (n.length < 1 || n.length > 40) return "Use 1 to 40 characters.";
  if (/[<>]/.test(n)) return "Angle brackets are not allowed.";
  return null;
}
