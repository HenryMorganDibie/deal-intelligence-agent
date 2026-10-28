"""Arabic event headlines are translated, judged and shown in English."""
import json

from src.engines import headline_translate as ht
from src.engines.event_filters import is_corporate_event

AR = [
    "«الأهلي كابيتال» توقع اتفاقية للاستحواذ على حصة «السويدي» في «القاهرة مصر للمنشآت التعليمية»",
    "الحرس الثوري الإيراني يعلن الاستحواذ على تقنيات قنبلة أمريكية بوزن 14 طنا",
]
EN = ["Al Ahly Capital signs agreement to acquire El Sewedy's stake in Cairo Egypt Educational Facilities",
      "Iran's Revolutionary Guard announces acquisition of technology for a 14-ton American bomb"]


def test_arabic_headlines_get_english_in_one_call_and_bad_replies_are_ignored():
    calls = []

    def call(system, user):
        calls.append(user)
        return "Here you go:\n" + json.dumps(EN)
    events = [{"id": "1", "headline": AR[0]}, {"id": "2", "headline": AR[1]},
              {"id": "3", "headline": "Dangote buys stake"}, {"id": "4", "headline": AR[0], "headline_en": "done"}]
    out = ht.add_translations(events, call)
    assert len(calls) == 1 and [e["id"] for e in out] == ["1", "2"]
    assert out[0]["headline_en"] == EN[0] and out[0]["headline_lang"] == "ar"
    assert ht.add_translations(events[:2], lambda s, u: json.dumps(EN[:1])) == []      # count mismatch
    assert ht.add_translations(events[:2], lambda s, u: json.dumps(AR)) == []          # untranslated echo

    def down(system, user):
        raise RuntimeError("no language model API key is configured.")
    assert ht.add_translations(events[:2], down) == []


def test_english_rendering_drives_the_corporate_filter():
    assert is_corporate_event(EN[0], "m_and_a_activity")
    assert not is_corporate_event(EN[1], "m_and_a_activity")
    assert not is_corporate_event("Angola President invites Namibia to purchase stake in Lobito refinery",
                                  "insider_activity")
    assert not is_corporate_event("US-Saudi consortium targets takeover of Al Nassr football club, Ronaldo in the picture",
                                  "m_and_a_activity")
    assert not is_corporate_event("How companies disbursed Kogi LG funds through ‘in-and-out’ paper transactions – "
                                  "EFCC investigator", "regulatory_action")
    assert is_corporate_event("LG Electronics Kenya profits fall on weak shilling", "earnings_surprise")
    assert is_corporate_event("Government invites bids for 30% stake in Ethio Telecom", "m_and_a_activity")


def test_visible_events_hide_untranslated_arabic_except_transactions():
    import src.hosted_market as hm

    rows = [
        {"id": "a", "country": "EG", "signal_type": "earnings_surprise", "headline": "خسائر بـ«المليارات» وفاتورة"},
        {"id": "b", "country": "EG", "signal_type": "m_and_a_activity", "headline": AR[0]},
        {"id": "c", "country": "EG", "signal_type": "m_and_a_activity", "headline": AR[1], "headline_en": EN[1]},
        {"id": "d", "country": "EG", "signal_type": "m_and_a_activity", "headline": AR[0], "headline_en": EN[0]},
    ]
    assert [e["id"] for e in hm._visible_events(rows)] == ["b", "d"]
