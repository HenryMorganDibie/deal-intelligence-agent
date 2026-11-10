import pytest

from src.engines import investors as inv


def _deal(i, investors, deal_type="equity_funding", target=None):
    return {"id": f"d{i}", "deal_type": deal_type, "investors": investors, "target": target or f"Startup {i}",
            "announced": f"2026-0{1 + i % 9}-01", "amount_usd": 1_000_000}


@pytest.fixture(autouse=True)
def fresh():
    inv._VARIANTS, inv._LEARNED_FOR = {}, None
    yield
    inv._VARIANTS, inv._LEARNED_FOR = {}, None


def names(board):
    return {row["name"]: row["deal_count"] for row in board}


def test_spellings_of_one_firm_are_one_investor():
    deals = [_deal(1, ["Ribbit Capital"]), _deal(2, ["Ribbit Capital"]), _deal(3, ["Ribbit"]),
             _deal(4, ["YCombinator"]), _deal(5, ["DFS Labs"]), _deal(6, ["DFS Lab"]),
             _deal(7, ["Novastar Ventures"]), _deal(8, ["Novastar fund"])]
    board = names(inv.leaderboard(deals, limit=50))
    assert board["Ribbit Capital"] == 3 and "Ribbit" not in board          # most-used spelling wins
    assert sum(1 for n in board if n.lower().startswith("dfs lab")) == 1
    assert sum(1 for n in board if n.startswith("Novastar")) == 1


def test_registry_name_is_kept_for_a_known_investor():
    deals = [_deal(1, ["Y Combinator"]), _deal(2, ["YCombinator"]), _deal(3, ["YCombinator"])]
    board = names(inv.leaderboard(deals, limit=50))
    assert board == {"Y Combinator": 3}


def test_ordinary_words_and_different_firms_are_not_merged():
    deals = [_deal(1, ["Play"]), _deal(2, ["Play Ventures"]), _deal(3, ["ReNew"]), _deal(4, ["Renew Capital"]),
             _deal(5, ["Village Capital"]), _deal(6, ["Village Global"]),
             _deal(7, ["Africa Infrastructure Fund"]), _deal(8, ["African Infrastructure Investment Managers"])]
    board = names(inv.leaderboard(deals, limit=50))
    for n in ("Play", "Play Ventures", "ReNew", "Renew Capital", "Village Capital", "Village Global",
              "Africa Infrastructure Fund", "African Infrastructure Investment Managers"):
        assert n in board, n


def test_profile_and_portfolio_follow_the_merged_name():
    deals = [_deal(1, ["Ribbit Capital"], target="Kuda"), _deal(2, ["Ribbit"], target="Chipper Cash")]
    p = inv.profile(deals, "Ribbit")
    assert p["name"] == "Ribbit Capital" and p["deal_count"] == 2
    assert {row["company"] for row in inv.portfolio(deals, "Ribbit")} == {"Kuda", "Chipper Cash"}
