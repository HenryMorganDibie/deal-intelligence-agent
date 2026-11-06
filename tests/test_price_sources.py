from datetime import date, datetime, timezone

import httpx

from src.engines import markets
from src.engines import price_sources as ps

BRVM = """Dernière mise à jour : Vendredi, 6 novembre, 2026 - 14:15 <table><thead><tr><th>Symbole</th></tr></thead>
<tbody> <tr><td>SNTS</td><td>SONATEL SENEGAL</td><td class="text-right">525 554</td><td class="text-right">4 200</td>
<td class="text-right">4 095</td><td class="text-right">4 175</td><td class="text-right"><span class="text-good">3,09</span>
<span class="icone-seance good"></span></td> </tr>""".replace("\n<td", "<td").replace("</td>\n", "</td>")
SIKA = """<tr> <td class="allf"><a href="/marches/cotation_SNTS.sn">SONATEL</a></td> <td>4&#xA0;095</td> <td>4&#xA0;175</td>
 <td>4&#xA0;095</td> <td>525&#xA0;554</td> <td> 2&#xA0;194&#xA0;187&#xA0;950 </td> <td><b>4&#xA0;175</b></td>
 <td class="quote_up2">3.09%</td> </tr><tr> <td class="allf"><a href="/marches/cotation_BRVMAG">BRVM - AGRICULTURE</a></td>"""
DSE = ('<span>"2026-11-06"</span><span>2026-11-06</span><span class="x font-bold text-white">CRDB</span>'
       '<span class="t tabular-nums">2,820</span><span class="inline-flex"><span class="inline-block" '
       'aria-hidden="true"></span>0.00<!-- -->%</span>')
MSE = """<caption class="text-center">Stats as at 06 November 2026 16:25 <i>hrs</i></caption>
<div class="ticker__item"> <span>NBM</span> <span class="pricedata changedown">8,849.88</span> </div>"""
RSE = """<tr> <td><img src="x" /> <span class="security-name">Bank of Kigali Group PLC</span> BOK</td> <td>701</td> <td>700</td>
<td><img src="y" /><span class="table-change-text">0.14 (0.14%)</span> </td> <td>300</td> <td>210,300</td> </tr>"""


def test_numbers_in_french_and_english_formats():
    assert ps._num("4 175") == 4175 and ps._num("0,15") == 0.15 and ps._num("8,849.88") == 8849.88
    assert ps._num("4&#xA0;175") == 4175 and ps._num("-") is None and ps._num("1 234,5") == 1234.5


def test_brvm_official_page():
    q = ps.parse_brvm_official(BRVM)["SNTS"]
    assert q == {"price": 4175.0, "date": "2026-11-06", "name": "SONATEL SENEGAL", "volume": 525554.0,
                 "prev": 4200.0, "chg_1d": 0.0309}
    assert ps.parse_brvm_official(BRVM.replace("mise à jour", "x")) == {}        # never priced without a date


def test_sikafinance_skips_indices():
    rows = ps.parse_sikafinance(SIKA, "2026-11-05")
    assert list(rows) == ["SNTS"] and rows["SNTS"]["price"] == 4175 and rows["SNTS"]["volume"] == 525554


def test_gse_takes_the_latest_day_and_cleans_codes():
    rows = ps.parse_gse_rows([
        ["2", "05/11/2026", "MTNGH", "4", "2", "3.50", "3.5", "3.6", "3.60", "0.1", "", "", "1,000", "3,600"],
        ["3", "05/11/2026", "**ALW**", "1", "0", "0.10", "0.1", "0.1", "0.10", "0", "", "", "0", "0"],
        ["1", "04/11/2026", "MTNGH", "4", "2", "3.40", "3.4", "3.5", "3.50", "0.1", "", "", "900", "3,150"]])
    assert set(rows) == {"MTNGH", "ALW"} and rows["MTNGH"]["price"] == 3.6 and rows["MTNGH"]["date"] == "2026-11-05"
    assert abs(rows["MTNGH"]["chg_1d"] - (3.6 / 3.5 - 1)) < 1e-6


def test_dse_mse_and_rse():
    assert ps.parse_dse(DSE, date(2026, 11, 6))["CRDB"] == {"price": 2820.0, "date": "2026-11-06", "chg_1d": 0.0}
    assert ps.parse_mse(MSE) == {"NBM": {"price": 8849.88, "date": "2026-11-06"}}
    bk = ps.parse_rse(RSE, "2026-11-06")["BOK"]
    assert bk["price"] == 701 and bk["prev"] == 700 and bk["value"] == 210300


def test_latest_session_skips_weekends_and_an_open_session():
    friday = date(2026, 11, 6)
    assert ps.latest_session(friday, datetime(2026, 11, 6, 17, tzinfo=timezone.utc)) == "2026-11-06"
    assert ps.latest_session(friday, datetime(2026, 11, 6, 9, tzinfo=timezone.utc)) == "2026-11-05"
    assert ps.latest_session(date(2026, 11, 9), datetime(2026, 11, 9, 9, tzinfo=timezone.utc)) == "2026-11-06"


PREV = [{"symbol": "BK", "name": "Bank of Kigali", "price": 700.0, "date": "2026-10-28", "mcap": 7_000.0, "ytd": 0.1},
        {"symbol": "MTNR", "name": "MTN Rwanda", "price": 200.0, "date": "2026-10-28", "shares": 10.0},
        {"symbol": "IMR", "name": "I&M", "price": 120.0, "date": "2026-10-28"}]


def test_reprice_uses_aliases_rescales_and_marks_the_source():
    rows, verdict = ps.reprice(PREV, {"BOK": {"price": 770.0, "date": "2026-11-06"},
                                      "MTNR": {"price": 210.0, "date": "2026-11-06"}}, "RSE official", {"BOK": "BK"})
    by = {r["symbol"]: r for r in rows}
    assert verdict == "ok" and by["BK"]["price"] == 770 and by["BK"]["source"] == "RSE official"
    assert by["BK"]["mcap"] == 7700.0 and abs(by["BK"]["ytd"] - (1.1 * 1.1 - 1)) < 1e-9
    assert by["MTNR"]["mcap"] == 2100.0
    assert by["IMR"]["date"] == "2026-10-28" and "source" not in by["IMR"]          # not priced: stays stale


def test_reprice_rejects_too_little_coverage_or_disagreeing_prices():
    assert ps.reprice(PREV, {"BK": {"price": 701.0, "date": "2026-11-06"}}, "x")[0] == []
    rows, verdict = ps.reprice(PREV, {s: {"price": p * 100, "date": "2026-11-06"} for s, p in
                                      (("BK", 700), ("MTNR", 200), ("IMR", 120))}, "x")
    assert rows == [] and "disagree" in verdict
    rows, _ = ps.reprice(PREV, {"BK": {"price": 9000.0, "date": "2026-11-06"},
                                "MTNR": {"price": 201.0, "date": "2026-11-06"},
                                "IMR": {"price": 121.0, "date": "2026-11-06"}}, "x")
    assert next(r for r in rows if r["symbol"] == "BK")["price"] == 700.0           # one wild jump is ignored


def test_snapshot_falls_through_to_the_next_source(monkeypatch):
    calls = []
    monkeypatch.setitem(ps.SOURCES, "rse", [
        ("broken", lambda c, d: calls.append("broken") or {}),
        ("good", lambda c, d: calls.append("good") or {"BK": {"price": 705.0, "date": "2026-11-06"},
                                                       "MTNR": {"price": 201.0, "date": "2026-11-06"}})])
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>Maintenance</html>")))
    quotes, _ = markets.fetch_exchange(markets.EXCHANGES["rse"], client, date(2026, 11, 6), PREV)
    assert calls == ["broken", "good"] and next(q for q in quotes if q["symbol"] == "BK")["source"] == "good"
