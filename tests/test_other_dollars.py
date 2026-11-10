import pytest

from src.engines import deals as dm


@pytest.mark.parametrize("headline,expected", [
    ("Numida secures $16.7 million CAD in Serena Ventures-led round", (16_700_000, "CAD")),
    ("Pan African completes C$54.2m deal", (54_200_000, "CAD")),
    ("Miner raises A$20 million for Ghana gold", (20_000_000, "AUD")),
    ("Firm raises 20 million Australian dollars", (20_000_000, "AUD")),
    ("Startup S$3 million seed", (3_000_000, "SGD")),
    # US dollars stay US dollars, including when a local figure is given alongside.
    ("Float Raises $2.6m (R46 Million) to Scale", (2_600_000, "USD")),
    ("Ghana firm raises US$5m", (5_000_000, "USD")),
    ("NNPC secures $3b emergency crude-for-cash loan to stabilise naira", (3_000_000_000, "USD")),
])
def test_dollar_currencies_are_told_apart(headline, expected):
    assert dm.deal_amount(headline) == expected


def test_other_dollars_convert_at_the_year_rate():
    assert dm.to_usd(16_700_000, "CAD", 2022) == pytest.approx(12_846_154, rel=1e-6)
    assert dm.to_usd(20_000_000, "AUD", 2019) == pytest.approx(13_888_889, rel=1e-6)


def test_a_stored_record_with_the_wrong_currency_is_corrected_and_others_are_left():
    wrong = {"deal_type": "equity_funding", "currency": "USD", "amount": 16_700_000.0, "amount_usd": 16_700_000.0,
             "announced": "2022-09-28", "target": "Numida",
             "headline": "Numida secures $16.7 million CAD in Serena Ventures-led round"}
    assert dm.reclassify(wrong) == {"currency": "CAD", "amount_usd": 12_846_154.0}
    right = {**wrong, "amount": 2_600_000.0, "amount_usd": 2_600_000.0, "target": "Float",
             "headline": "South Africa's Fintech Startup Float Raises $2.6m (R46 Million) to Scale"}
    assert dm.reclassify(right) is None
