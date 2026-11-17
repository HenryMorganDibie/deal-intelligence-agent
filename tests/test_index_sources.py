from datetime import date, datetime, timezone

from src.engines import index_sources as s

MYSTOCKS = """<title>Price list &#8212; 16 Nov 2026 - myStocks Mobile</title>
<tr class="row r0"> <td class=nm><a href="/m/stock=%255EN25I">^N25I</a><br>
<td class=n>6,829.19<td class="n x1">&#9650; 0.13%<td class=n>-<tr class="row r0">
<td class=nm><a href="/m/stock=%255ENASI">^NASI</a><br>
<td class=n>241.56<td class="n x-1">&#9660; 0.07%<td class=n>-<tr class="row r1">"""

DSE = (r'<span>Daily Market Report</span> <span>16 Nov 2026</span> ... '
       r'{\"name\":\"TSI\",\"close\":9552.99,\"change\":28.2,\"pct\":0.3,\"series\":[[1794873600,9552.99]]},'
       r'{\"name\":\"DSEI\",\"close\":4342.61,\"change\":8.51,\"pct\":0.2,\"series\":[[1794873600,4342.61]]}')

MSE = """<p>Stats as at 17 November 2026</p><tbody> <tr> <th>MASI</th> <td class="text-right">480,359.72</td>
<td class="text-right">480,354.17</td> <td class="text-right">1,293</td></tr>"""

SEM = """<li> <div class="name">SEMDEX</div> <div class="num less"><span class="icn"></span></span>2,314.94 </div> </li>
<li> <div class="name">SEM-ASI</div> <div class="num less"><span class="icn"></span></span>2,074.15 </div> </li>"""

SIKA = """<tr><th></th><th>Nom</th><th>Dernier</th><th>Variation</th><th>Date</th></tr>
<tr><td></td><td><a>BRVM COMPOSITE</a></td><td>512,85</td><td>-0.60%</td><td>16/11/2026</td><td>48,33%</td></tr>
<tr><td></td><td>NIGERIA ALL SHARE INDEX</td><td>252&#xA0;882,78</td><td>-0.44%</td><td>28/10/2026</td></tr>
<tr><td></td><td>TUNINDEX</td><td>18&#xA0;989,99</td><td>0.79%</td><td>13/11/2026</td></tr>"""


def test_nairobi_all_share_level_change_and_date():
    assert s.parse_mystocks_nasi(MYSTOCKS) == {"exchange": "nse", "name": "NSE ASI", "level": 241.56,
                                               "chg_1d": -0.0007, "date": "2026-11-16",
                                               "source": "NSE price list (myStocks)"}


def test_dse_index_is_dated_by_the_market_report_not_the_chart():
    row = s.parse_dse(DSE)
    assert (row["level"], row["chg_1d"], row["date"]) == (4342.61, 0.002, "2026-11-16")


def test_malawi_change_is_close_over_open():
    row = s.parse_mse_index(MSE)
    assert row["level"] == 480354.17 and row["date"] == "2026-11-17"
    assert row["chg_1d"] == round(480354.17 / 480359.72 - 1, 6)


def test_mauritius_reads_sem_asi_not_semdex():
    assert s.parse_sem(SEM, "2026-11-16")["level"] == 2074.15


def test_ngx_and_uganda_levels():
    assert s.parse_ngx_snapshot({"ASI": 252809.78, "DEALS": 5105}, "2026-11-16")["level"] == 252809.78
    feed = [{"type": "EQUITY", "stock": "MTN", "price": 300}, {"type": "INDEX", "stock": "ALSI", "price": 2528.35}]
    assert s.parse_use_index(feed, "2026-11-16")["level"] == 2528.35
    assert s.parse_ngx_snapshot({}, "2026-11-16") is None


def test_sikafinance_keeps_only_the_indices_it_still_updates():
    rows = {r["exchange"]: r for r in s.parse_sika_indices(SIKA)}
    assert set(rows) == {"brvm", "bvmt"}                 # its NGX row stopped with the listing site
    assert rows["brvm"] == {"exchange": "brvm", "name": "BRVM-CI", "level": 512.85, "chg_1d": -0.006,
                            "date": "2026-11-16", "source": "sikafinance"}
    assert rows["bvmt"]["level"] == 18989.99 and rows["bvmt"]["date"] == "2026-11-13"


def test_change_from_previous_only_when_official_and_one_session_back():
    row = {"exchange": "ngx", "level": 253000.0, "chg_1d": None, "date": "2026-11-17"}
    official = {"exchange": "ngx", "level": 252809.78, "chg_1d": None, "date": "2026-11-16"}
    assert s.with_change_from_previous(row, official)["chg_1d"] == round(253000 / 252809.78 - 1, 6)
    assert s.with_change_from_previous(row, {**official, "estimated": True})["chg_1d"] is None
    assert s.with_change_from_previous(row, {**official, "date": "2026-11-01"})["chg_1d"] is None
    # an unchanged level means the exchange did not trade: the previous row stands, with its own date
    assert s.with_change_from_previous({**row, "level": 252809.78}, official) == official


def test_level_only_sources_are_not_read_during_the_session(monkeypatch):
    calls = []

    def fake_json(client, url):
        calls.append(url)
        return {"ASI": 1.0} if url == s.NGX_SNAPSHOT else None

    monkeypatch.setattr(s, "_json", fake_json)
    monkeypatch.setattr(s, "_page", lambda client, url: "")
    tuesday = date(2026, 11, 17)
    s.official_indices(None, tuesday, now=datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc))
    assert s.NGX_SNAPSHOT not in calls                   # 11:00 in Lagos: NGX is trading
    rows = s.official_indices(None, tuesday, now=datetime(2026, 11, 17, 17, 23, tzinfo=timezone.utc))
    assert [(r["exchange"], r["date"]) for r in rows] == [("ngx", "2026-11-17")]
