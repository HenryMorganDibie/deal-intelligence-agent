"""Price-move alerts: which listings count as a followed company, and which closes raise an alert."""
import json

from src.engines import chat_formats, email_alerts, watch

VENUES = {"ngx": {"name": "Nigerian Exchange", "currency": "NGN"}, "nse": {"name": "Nairobi Securities Exchange", "currency": "KES"}}


def q(name, symbol, chg, day="2026-11-16", price=100.0, **kw):
    return {"name": name, "symbol": symbol, "chg_1d": chg, "date": day, "price": price, **kw}


QUOTES = {
    "ngx": [q("Dangote Cement", "DANGCEM", 0.072), q("Dangote Sugar Refinery", "DANGSUGAR", 0.01),
            q("Guaranty Trust Holding Company", "GTCO", -0.11), q("MTN Nigeria", "MTNN", 0.08, volume=0),
            q("Zenith Bank", "ZENITHBANK", 0.09, day="2026-11-13"),          # stale: the exchange's latest is the 16th
            q("Access Holdings", "ACCESSCORP", 0.9)],                          # 90% in a day: a data fault
    "nse": [q("Safaricom", "SCOM", -0.051), q("ABC Bank", "ABCL", 0.2)],
    "jse": [q("Telkom SA SOC Ltd", "TKG", 0.1129, volume=5684794), q("Canal+ SA", "CNP", -0.0907, volume=40)],
}


def wl(companies, pct=5):
    return {"id": "w1", "name": "Banks", "companies": companies, "price_move_pct": pct}


def test_off_by_default_and_without_companies():
    assert watch.price_moves({"companies": ["Dangote Cement"]}, QUOTES, VENUES) == []
    assert watch.price_moves(wl([]), QUOTES, VENUES) == []


def test_moves_past_the_threshold_on_the_latest_close_are_alerted():
    alerts = watch.price_moves(wl(["Dangote", "GTCO", "Safaricom PLC", "Zenith Bank", "Access Holdings", "MTN Nigeria"]), QUOTES, VENUES)
    ids = [a["id"] for a in alerts]
    # GTCO by ticker (biggest move first), Dangote Cement by name (not the 1% sugar move), Safaricom inside a longer name
    assert ids == ["ngx:GTCO:2026-11-16", "ngx:DANGCEM:2026-11-16", "nse:SCOM:2026-11-16"]
    gt = alerts[0]
    assert gt["title"] == "Guaranty Trust Holding Company closed down 11.0% on the Nigerian Exchange"
    assert "close 100.00 NGN" in gt["facts_line"] and gt["kind"] == "price"


def test_threshold_and_short_names_do_not_overmatch():
    assert [a["id"] for a in watch.price_moves(wl(["Dangote Cement"], pct=10), QUOTES, VENUES)] == []
    # "ABC" is too short to match by name, and is not ABC Bank's ticker
    assert watch.price_moves(wl(["ABC"]), QUOTES, VENUES) == []


def test_one_alert_per_listing_per_day_and_stable_fingerprint():
    a = watch.price_moves(wl(["Dangote Cement"]), QUOTES, VENUES)[0]
    revised = dict(a, title=a["title"].replace("7.2", "7.4"))
    assert watch.alert_fingerprint(a) == watch.alert_fingerprint(revised)


def test_price_alerts_render_in_chat_and_email():
    alerts = watch.price_moves(wl(["GTCO"]), QUOTES, VENUES)
    body = json.dumps(chat_formats.slack({"id": "w1", "name": "Banks"}, alerts, "https://example.org/w"))
    assert "closed down 11.0%" in body and "Price move (GTCO)" in body
    title, detail, source = email_alerts._alert_line(alerts[0])
    assert detail.startswith("Price move (GTCO)") and source is None


def test_thinly_traded_moves_are_ignored():
    venues = {**VENUES, "jse": {"name": "Johannesburg Stock Exchange", "currency": "ZAR"}}
    ids = [a["id"] for a in watch.price_moves(wl(["Telkom", "Canal+ SA"]), QUOTES, venues)]
    assert ids == ["jse:TKG:2026-11-16"]                    # Canal+ moved 9% on 40 shares
