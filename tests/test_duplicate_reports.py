from src.engines import deals as dm


def deal(**kw):
    base = {"deal_type": "acquisition", "announced": "2026-04-23", "countries": [], "sources": [{"url": kw.get("headline", "")}]}
    return {**base, **kw}


def test_two_wordings_of_one_acquisition_are_one_transaction():
    a = deal(target="ROK", buyer="Canal+", headline="Canal+ acquires ROK studios as part of Africa expansion plans")
    b = deal(target="Leading Nigerian Studio ROK", buyer="CanalPlus", headline="Vivendi's CanalPlus Acquires Leading Nigerian Studio ROK")
    assert dm.strong_same_report(a, b)
    c = deal(target="Kenyan Label AI Records", buyer="UMG", headline="UMG Buys Majority Stake in Kenyan Label AI Records")
    d = deal(target="Kenyan Label AI Records", buyer="Universal Music Group", headline="Universal Music Group Purchases Stake")
    assert dm.strong_same_report(c, d)


def test_a_round_reported_by_its_lead_and_by_its_size_is_one():
    a = deal(deal_type="equity_funding", target="Arnergy Solar", buyer="CardinalStone",
             headline="CardinalStone leads investment in Nigeria's Arnergy Solar", announced="2025-04-15")
    b = deal(deal_type="equity_funding", target="Arnergy", buyer=None, amount_usd=18_000_000,
             headline="Nigeria's Arnergy Raises $18M to Scale Solar Lease Plans", announced="2025-04-14")
    assert dm.strong_same_report(a, b)


def test_different_buyers_amounts_countries_or_listings_stay_apart():
    sc1 = deal(target="Standard Chartered Bank Angola", buyer="Finibanco", headline="Finibanco adquire 60% do Standard Chartered Bank Angola")
    sc2 = deal(target="Standard Chartered", buyer="Access Bank", headline="Access Bank acquires Standard Chartered's subsidiaries in 5 African countries")
    assert not dm.strong_same_report(sc1, sc2)
    m1 = deal(target="MoMo", buyer="MTN Nigeria", amount_usd=4_699_232, headline="MTN Nigeria acquires stake in MoMo for N6.95bn")
    m2 = deal(target="MoMo PSB", buyer="MTN Nigeria", amount_usd=43_800_000, headline="MTN Nigeria Acquires Minority Stake in MoMo PSB for US$43.8 Million")
    assert not dm.strong_same_report(m1, m2)
    t1 = deal(target="Standard Chartered Tanzania", buyer="Access Bank", headline="Access Bank acquires Standard Chartered Tanzania operations")
    t2 = deal(target="Standard Chartered", buyer="Access Bank", headline="Access Bank takes over Standard Chartered in The Gambia", announced="2026-04-30")
    assert not dm.strong_same_report(t1, t2)
    i1 = deal(deal_type="ipo", target="Dangote", headline="Dangote Plans Fertiliser Listing After Refinery IPO")
    i2 = deal(deal_type="ipo", target="Dangote Petroleum Refinery", headline="Billionaire Dangote launches oil refinery 'people's IPO'")
    assert not dm.strong_same_report(i1, i2)


def test_reports_far_apart_or_of_a_different_kind_stay_apart():
    a = deal(target="Minet Botswana", deal_type="exit", seller="Africa Lighthouse Capital", announced="2026-07-07",
             headline="Africa Lighthouse Capital exits stake in Minet Botswana")
    b = deal(target="Minet", buyer="Adenia Partners", announced="2026-06-30", headline="Adenia Partners acquires Minet from Capitalworks")
    assert not dm.strong_same_report(a, b)                       # an exit and an acquisition a week apart
    c = deal(deal_type="equity_funding", target="Watu Credit", headline="Watu Credit Raises $7M")
    d = deal(deal_type="debt_financing", target="Watu Credit", headline="Watu Credit secures $7M loan")
    assert not dm.strong_same_report(c, d)


def test_stored_duplicates_are_folded_into_the_fuller_record():
    from src import hosted_market as hm
    a = deal(id="a", target="Arnergy Solar", deal_type="equity_funding", buyer="CardinalStone", announced="2025-04-15",
             headline="CardinalStone leads investment in Nigeria's Arnergy Solar")
    b = deal(id="b", target="Arnergy", deal_type="equity_funding", buyer=None, amount_usd=18_000_000, announced="2025-04-14",
             headline="Nigeria's Arnergy Raises $18M to Scale Solar Lease Plans")
    out = hm._reclassify_stored({"a": a, "b": b}, {})
    assert out["a"]["merged_into"] == "b"
    assert out["b"]["buyer"] == "CardinalStone" and len(out["b"]["sources"]) == 2


def test_a_sale_and_its_completed_acquisition_are_one_transaction():
    a = deal(deal_type="exit", target="Honeywell", seller="Oba Otudeko", amount_usd=51_645_719, announced="2022-05-03",
             headline="Oba Otudeko sells Honeywell for N22bn to repay age long loan to First Bank of Nigeria Holding")
    b = deal(target="Honeywell Flour Mills", buyer="FMN", announced="2022-04-30",
             headline="FMN completes acquisition of Honeywell Flour Mills")
    assert dm.strong_same_report(a, b)


def test_the_more_specific_target_name_is_kept():
    from src import hosted_market as hm
    a = deal(id="a", target="Kenyan Label AI Records", buyer="UMG", announced="2018-03-05",
             headline="UMG Buys Majority Stake in Kenyan Label AI Records")
    b = deal(id="b", target="Kenyan Label", buyer="Universal Music Group", announced="2018-03-04",
             headline="Universal Music Group Purchases Stake In Kenyan Label",
             sources=[{"url": "x"}, {"url": "y"}])
    out = hm._reclassify_stored({"a": a, "b": b}, {})
    assert out["a"]["merged_into"] == "b" and out["b"]["target"] == "Kenyan Label AI Records"


def test_a_mixed_equity_and_debt_round_reported_both_ways_is_one():
    a = deal(deal_type="debt_financing", target="Numida", amount_usd=12_300_000, announced="2022-09-28",
             headline="YC-backed fintech Numida raises $12.3M led by Serena Ventures to extend loans")
    b = deal(deal_type="equity_funding", target="Numida", amount_usd=12_846_154, announced="2022-09-28",
             headline="Numida secures $16.7 million CAD in Serena Ventures-led round")
    assert dm.strong_same_report(a, b)
    far = {**b, "amount_usd": 30_000_000}
    assert not dm.strong_same_report(a, far)                     # amounts too far apart: two different raises
