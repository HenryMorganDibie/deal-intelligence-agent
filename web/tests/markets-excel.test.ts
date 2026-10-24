import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as XLSX from "@stackline/xlsx";
import { createPortfolioWorkbook, parsePortfolioWorkbook } from "../lib/markets-excel";

const headers = ["name", "ticker", "country", "sector", "asset_type", "currency", "quantity", "cost_per_unit", "current_price", "fx_to_base", "price_as_of", "fx_as_of"];

test("Excel workbook export/import round-trips text, numeric values, blanks and ISO dates", () => {
  const rows = [
    headers,
    ["Bank, Limited", "BNK", "Nigeria", "Banking", "Stock", "NGN", 12.5, 100, 125, 1, "2026-10-20", ""],
    ["Quoted \"Name\"", "", "Kenya", "", "ETF", "KES", 2, 40, "", 0.0075, "", "2026-10-21"],
  ];
  const workbook = createPortfolioWorkbook(rows);
  assert.ok(workbook.byteLength > 100);
  assert.deepEqual(parsePortfolioWorkbook(workbook), rows.map((row) => row.map((cell) => String(cell ?? ""))));
});

test("Excel parser rejects formula cells rather than trusting cached values", () => {
  const workbook = XLSX.utils.book_new();
  const worksheet = XLSX.utils.aoa_to_sheet([headers, ["Example", "EX", "Nigeria", "Banking", "Stock", "NGN", 10, 100, 110, 1, "", ""]]);
  worksheet["G2"] = { t: "n", f: "5+5", v: 10 };
  XLSX.utils.book_append_sheet(workbook, worksheet, "Portfolio");
  const bytes = XLSX.write(workbook, { bookType: "xlsx", type: "array" }) as Uint8Array;
  assert.throws(() => parsePortfolioWorkbook(bytes), /formulas are not accepted/i);
});

test("Excel parser rejects empty, oversized and invalid workbooks", () => {
  assert.throws(() => parsePortfolioWorkbook(new Uint8Array()), /empty/i);
  assert.throws(() => parsePortfolioWorkbook(new Uint8Array(5 * 1024 * 1024 + 1)), /5 MB or smaller/i);
  assert.throws(() => parsePortfolioWorkbook(new Uint8Array([1, 2, 3, 4])), /valid .xlsx/i);
});

test("Excel parser rejects workbooks with more than 5,000 holding rows", () => {
  const rows: (string | number)[][] = [headers];
  for (let index = 0; index < 5001; index += 1) rows.push(["Example", "EX", "Nigeria", "Banking", "Stock", "NGN", 1, 100, 110, 1, "", ""]);
  const workbook = createPortfolioWorkbook(rows);
  assert.throws(() => parsePortfolioWorkbook(workbook), /at most 5000 holding rows/i);
});
