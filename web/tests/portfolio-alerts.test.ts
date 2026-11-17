import { test } from "node:test";
import * as assert from "node:assert/strict";
import { alertsDiff, parseAlertsLink, uniqueNames } from "../lib/portfolio-alerts";

test("new holdings are added and sold ones removed, ignoring case and blanks", () => {
  const d = alertsDiff(["Dangote Cement", "gtco", "Zenith Bank", " "], ["Dangote Cement", "GTCO", "MTN Nigeria"]);
  assert.deepEqual(d, { add: ["Zenith Bank"], remove: ["MTN Nigeria"] });
});

test("nothing to do when the watchlist already follows every holding", () => {
  assert.deepEqual(alertsDiff(["A Co", "B Co", "a co"], ["b co", "A Co"]), { add: [], remove: [] });
});

test("duplicate holdings count once, in portfolio order", () => {
  assert.deepEqual(uniqueNames(["B Co", "A Co", "b co", ""]), ["B Co", "A Co"]);
});

test("a stored link is accepted only when well formed", () => {
  const id = "0b9f1c4e-3a1d-4c7e-9d2a-6f1e2d3c4b5a";
  assert.deepEqual(parseAlertsLink(JSON.stringify({ watchlistId: id, synced: ["A"] })), { watchlistId: id, synced: ["A"] });
  assert.equal(parseAlertsLink("not json"), null);
  assert.equal(parseAlertsLink(JSON.stringify({ watchlistId: "x", synced: [] })), null);
  assert.equal(parseAlertsLink(JSON.stringify({ watchlistId: id, synced: [1] })), null);
});
