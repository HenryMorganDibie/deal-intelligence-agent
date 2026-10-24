const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const Module = require("node:module");
const test = require("node:test");
const ts = require("typescript");

const sourcePath = path.resolve(__dirname, "../lib/markets-valuation.ts");
const source = fs.readFileSync(sourcePath, "utf8");
const compiled = ts.transpile(source, {
  module: ts.ModuleKind.CommonJS,
  target: ts.ScriptTarget.ES2020,
});
const loaded = new Module(sourcePath, module);
loaded.filename = sourcePath;
loaded.paths = Module._nodeModulePaths(path.dirname(sourcePath));
loaded._compile(compiled, sourcePath);

const {
  calculateDcfPerShare,
  calculateDdmPerShare,
  validHttpUrl,
  validPastDate,
} = loaded.exports;

test("DCF returns a finite per-share estimate for valid positive operating cash flow", () => {
  const value = calculateDcfPerShare(100, 8, 12, 3, 50, 20, 10);
  assert.equal(typeof value, "number");
  assert.ok(Number.isFinite(value));
  assert.ok(value > 0);
});

test("DCF is directionally sensitive to growth and discount-rate assumptions", () => {
  const lowerGrowth = calculateDcfPerShare(100, 4, 12, 3, 50, 20, 10);
  const higherGrowth = calculateDcfPerShare(100, 10, 12, 3, 50, 20, 10);
  const lowerDiscount = calculateDcfPerShare(100, 8, 10, 3, 50, 20, 10);
  const higherDiscount = calculateDcfPerShare(100, 8, 14, 3, 50, 20, 10);
  assert.ok(lowerGrowth != null && higherGrowth != null && higherGrowth > lowerGrowth);
  assert.ok(lowerDiscount != null && higherDiscount != null && lowerDiscount > higherDiscount);
});

test("DCF refuses unsupported numeric inputs and terminal growth at or above discount rate", () => {
  assert.equal(calculateDcfPerShare(0, 8, 12, 3, 50, 20, 10), null);
  assert.equal(calculateDcfPerShare(100, 8, 12, 12, 50, 20, 10), null);
  assert.equal(calculateDcfPerShare(100, 8, 12, 3, -1, 20, 10), null);
  assert.equal(calculateDcfPerShare(100, 8, 12, 3, 50, 20, 0), null);
});

test("DDM returns a finite estimate and responds to growth and discount-rate changes", () => {
  const base = calculateDdmPerShare(2, 5, 10, 3);
  const higherGrowth = calculateDdmPerShare(2, 7, 10, 3);
  const higherDiscount = calculateDdmPerShare(2, 5, 12, 3);
  assert.equal(typeof base, "number");
  assert.ok(Number.isFinite(base));
  assert.ok(higherGrowth != null && base != null && higherGrowth > base);
  assert.ok(higherDiscount != null && base != null && higherDiscount < base);
});

test("DDM refuses absent dividends and invalid terminal assumptions", () => {
  assert.equal(calculateDdmPerShare(0, 5, 10, 3), null);
  assert.equal(calculateDdmPerShare(2, 5, 10, 10), null);
  assert.equal(calculateDdmPerShare(2, 5, 0, 3), null);
});

test("source URL validation only accepts HTTP and HTTPS URLs", () => {
  assert.equal(validHttpUrl("https://example.com/filing"), true);
  assert.equal(validHttpUrl("http://example.com/quote"), true);
  assert.equal(validHttpUrl("javascript:alert(1)"), false);
  assert.equal(validHttpUrl("not a URL"), false);
});

test("date validation rejects malformed, impossible and future dates", () => {
  const future = new Date(Date.now() + 10 * 86400000).toISOString().slice(0, 10);
  assert.equal(validPastDate("2000-01-01"), true);
  assert.equal(validPastDate("2026-02-31"), false);
  assert.equal(validPastDate("01/02/2025"), false);
  assert.equal(validPastDate(future), false);
});
