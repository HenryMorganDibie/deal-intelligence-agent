from datetime import date

from src.engines import price_history as ph


def test_pack_years_one_row_per_year_in_date_order():
    pts = [(date(2011, 1, 3), 10.0), (date(2010, 12, 31), 9.5), (date(2010, 1, 4), 8.0),
           (date(2010, 1, 1), 7.0),            # holiday artefact: dropped
           (date(2010, 1, 4), 8.2),            # the same day again: the last close wins
           (date(2011, 1, 4), 0.0)]            # no price: dropped
    rows = ph.pack_years("brvm", "snts", pts, "sikafinance history")
    assert [(r["year"], r["days"], r["closes"]) for r in rows] == [(2010, [4, 365], [8.2, 9.5]), (2011, [3], [10.0])]
    assert rows[0]["symbol"] == "SNTS" and rows[0]["exchange"] == "brvm"


def test_yahoo_cents_are_converted_and_dates_are_local():
    payload = {"chart": {"result": [{"meta": {"currency": "ZAc", "gmtoffset": 7200},
                                     "timestamp": [1795503600, 1795590000],
                                     "indicators": {"quote": [{"close": [62800.0, None]}]}}]}}
    assert ph.parse_yahoo(payload) == [(date(2026, 11, 24), 628.0)]
    egp = {"chart": {"result": [{"meta": {"currency": "EGP", "gmtoffset": 7200}, "timestamp": [1795503600],
                                 "indicators": {"quote": [{"close": [127.5]}]}}]}}
    assert ph.parse_yahoo(egp) == [(date(2026, 11, 24), 127.5)]
    assert ph.parse_yahoo({"chart": {"result": None}}) == []


def test_sika_tickers_and_rows():
    html = ('<a href="/marches/cotation_SNTS.sn">Sonatel</a><a href="/marches/cotation_ORAC.ci">Orange</a>'
            '<a href="/marches/cotation_\' + msg[i].ticker + \'">x</a>')
    assert ph.sika_tickers(html) == {"SNTS": "SNTS.sn", "ORAC": "ORAC.ci"}
    rows = ph.parse_sika({"lst": [{"Date": "04/01/2010", "Close": 1250}, {"Date": "bad", "Close": 1}]})
    assert rows == [(date(2010, 1, 4), 1250.0)]
    assert ph.parse_sika({"lst": "", "error": "nodata"}) == []


def test_quarters_cover_the_whole_period_without_gaps():
    q = ph.quarters_back(date(2026, 10, 27), date(2010, 1, 1))
    assert q[0] == (date(2026, 8, 1), date(2026, 10, 27)) and q[-1][0] == date(2010, 1, 1)
    for (lo, _), (_, hi) in zip(q, q[1:]):
        assert (lo - hi).days == 1


def test_walk_back_stops_when_history_ends_or_never_starts():
    calls = []

    def ends_in_2020(lo, hi):
        calls.append(lo)
        return [(lo, 1.0)] if lo.year >= 2020 else []
    pts = ph.sika_history(ends_in_2020, date(2010, 1, 1), date(2026, 10, 27), give_up_after=8)
    assert min(d for d, _ in pts).year == 2020 and min(calls).year == 2018      # 8 empty quarters, then stop
    calls.clear()
    assert ph.sika_history(lambda lo, hi: calls.append(lo) or [], date(2010, 1, 1), date(2026, 10, 27)) == []
    assert len(calls) == 4                                                       # nothing in a year: no history
