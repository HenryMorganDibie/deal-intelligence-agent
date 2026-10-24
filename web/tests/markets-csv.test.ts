import { test } from "node:test";
import * as assert from "node:assert/strict";
import { csvEscape, parseCsv, stringifyCsv } from "../lib/markets-csv";

test("CSV parser handles BOM, CRLF, blank rows and trailing newline", () => {
  assert.deepEqual(parseCsv("\uFEFFname,ticker\r\nExample,EX\r\n\r\n"), [
    ["name", "ticker"],
    ["Example", "EX"],
  ]);
});

test("CSV parser handles escaped quotes, commas and multiline quoted fields", () => {
  assert.deepEqual(parseCsv('name,notes\n"Example, Inc.","Said ""hello""\nand left"'), [
    ["name", "notes"],
    ["Example, Inc.", 'Said "hello"\nand left'],
  ]);
});

test("CSV parser accepts whitespace after a quoted cell", () => {
  assert.deepEqual(parseCsv('"Example"  ,  EX'), [["Example", "EX"]]);
});

test("CSV parser rejects unclosed quotes and quote characters in unquoted fields", () => {
  assert.throws(() => parseCsv('name,notes\nExample,"unfinished'), /unclosed quoted field/i);
  assert.throws(() => parseCsv('na"me,ticker'), /quote inside an unquoted field/i);
});

test("CSV parser rejects unexpected characters after a closing quote", () => {
  assert.throws(() => parseCsv('"Example"oops,EX'), /after a closing quote/i);
});

test("CSV export escapes cells and round-trips user-entered names and notes", () => {
  const rows = [
    ["name", "notes", "empty"],
    ['Example, Inc.', 'Said "hello"\nthen left', ""],
  ];
  const csv = stringifyCsv(rows);
  assert.equal(csv, 'name,notes,empty\r\n"Example, Inc.","Said ""hello""\nthen left",');
  assert.deepEqual(parseCsv(csv), rows);
  assert.equal(csvEscape(null), "");
});
