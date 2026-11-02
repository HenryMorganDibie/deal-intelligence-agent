import { test } from "node:test";
import * as assert from "node:assert/strict";
import { displayNameProblem, passwordProblems, passwordStrength, usernameProblem } from "../lib/password-policy";
import { safeNext } from "../lib/safe-next";

test("a strong password passes every rule", () => {
  assert.deepEqual(passwordProblems("Kettle-Harbour-91!", { email: "ada@example.com", username: "ada_l" }), []);
  assert.ok(passwordStrength("Kettle-Harbour-91!").score >= 3);
});

test("each password rule is enforced", () => {
  const ctx = { email: "henry@example.com", username: "deal_watcher" };
  assert.ok(passwordProblems("Short1!", ctx).some((p) => p.includes("12 characters")));
  assert.ok(passwordProblems("alllowercase123!", ctx).some((p) => p.includes("capital")));
  assert.ok(passwordProblems("ALLUPPERCASE123!", ctx).some((p) => p.includes("lowercase")));
  assert.ok(passwordProblems("NoNumbersHere!!", ctx).some((p) => p.includes("number")));
  assert.ok(passwordProblems("NoSymbolsHere123", ctx).some((p) => p.includes("symbol")));
  assert.ok(passwordProblems("Aaaaa-Harbour-91!", ctx).some((p) => p.includes("repeated")));
  assert.ok(passwordProblems("Henry-Harbour-91!", ctx).some((p) => p.includes("username or email")));
  assert.ok(passwordProblems("My-Deal_Watcher-9!", ctx).some((p) => p.includes("username or email")));
  assert.ok(passwordProblems("Password-Harbour-1!", ctx).some((p) => p.includes("common")));
  assert.deepEqual(passwordProblems("x".repeat(129)), ["Use at most 128 characters."]);
});

test("username and nickname rules", () => {
  assert.equal(usernameProblem("deal_watcher7"), null);
  assert.equal(usernameProblem("Deal_Watcher7"), null);          // normalised to lowercase
  assert.ok(usernameProblem("ab"));
  assert.ok(usernameProblem("_leading"));
  assert.ok(usernameProblem("trailing_"));
  assert.ok(usernameProblem("has space"));
  assert.ok(usernameProblem("a".repeat(21)));
  assert.equal(displayNameProblem("Ada Lovelace"), null);
  assert.ok(displayNameProblem("   "));
  assert.ok(displayNameProblem("<script>"));
});

test("return paths stay inside the app", () => {
  assert.equal(safeNext("/app/markets?x=1"), "/app/markets?x=1");
  assert.equal(safeNext("/account/security"), "/account/security");
  for (const bad of ["https://evil.example", "//evil.example", "/\\evil.example", "/apple", "javascript:alert(1)", "", null]) {
    assert.equal(safeNext(bad), "/app", String(bad));
  }
});
