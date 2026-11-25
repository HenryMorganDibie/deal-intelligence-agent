from datetime import date

from src.engines import ngx_archive as na

TEXT_2014 = """Prices for Securities Traded as of 01/07/2014
PRICES FOR EQUITY SECURITIES TRADED ON 01/07/2014
S/N COMPANY PCLOSE OPEN HIGH LOW %SPREAD CLOSE CHANGE %CHANGE TRADES VOLUME VALUE
1 7UP 93.00 97.65 102.53 102.53 - 102.53 9.53 10.25 23 88,590 9,077,032.70
3 ACADEMY 1.71 - - - - 1.71 - - 7 102,919 175,005.92
4 ACCESS 9.55 9.60 9.80 9.50 3.06 9.80 0.25 2.62 184 88,717,261 847,370,277.58
9 GUARANTY 28.50 28.60 28.90 28.50 1.40 28.76 0.26 0.91 300 8,247,623 238,322,831.49
24 CONTINSURE 1.06 1.09 1.09 1.09 - 1.09 0.03 2.83 3 280,000,4"""

TEXT_2020 = """PRICES FOR EQUITY SECURITIES TRADED ON 01/07/2020
S/N COMPANY PCLOSE OOPEN OPEN HIGH LOW %SPREAD OCLOSE CLOSE CHANGE %CHANGE TRADES VOLUME VALUE
3 ACCESS 6.55 - 6.55 6.60 6.50 1.52 - 6.60 0.05 0.76 100 1,649,403 10,780,456.95
4 AFRIPRUD 4.11 - 4.11 4.10 4.05 1.22 4.05 4.05 -0.06 -1.46 53 1,701,066 6,940,685.19
S/N BANKING MARKET CAP(Nm) PRICE %CHANGE TRADES VOLUME
1 ACCESS BANK PLC. 234,598.49 6.60 0.76 100 1,649,403"""


def test_each_page_is_read_by_its_own_header():
    day, rows = na.parse_price_text(TEXT_2014)
    assert day == date(2014, 7, 1)
    assert rows["7UP"] == {"close": 102.53, "volume": 88590.0, "value": 9077032.7}
    assert rows["ACADEMY"]["close"] == 1.71                       # untraded columns shown as '-'
    assert "CONTINSURE" not in rows                                # a row cut short is skipped, not guessed
    day, rows = na.parse_price_text(TEXT_2020)
    assert day == date(2020, 7, 1)
    assert rows["AFRIPRUD"]["close"] == 4.05 and rows["ACCESSCORP"]["volume"] == 1649403.0


def test_old_tickers_join_the_current_listing():
    _, rows = na.parse_price_text(TEXT_2014)
    assert rows["GTCO"]["close"] == 28.76 and rows["ACCESSCORP"]["close"] == 9.8
    assert "GUARANTY" not in rows and "ACCESS" not in rows


def test_zip_refs_read_dates_and_ignore_other_files():
    refs = ["/DownloadsContent/Gainers and Price list for 01-07-2014.zip",
            "/DownloadsContent/GAINERS AND PRICE LIST FOR 1-07-2020.zip",
            "/DownloadsContent/Daily Official List - Equities for 01-07-2014.pdf",
            "/DownloadsContent/Gainers and Price list for 31-02-2015.zip"]
    assert na.zip_refs(refs) == {date(2014, 7, 1): refs[0], date(2020, 7, 1): refs[1]}


def test_a_zip_without_a_price_list_gives_nothing():
    assert na.parse_zip(b"not a zip") == (None, {})
