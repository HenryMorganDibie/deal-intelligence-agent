-- Free accounts browse everything (deals, companies, investors, markets, countries, comparables, country risk) and
-- may try 30 briefs and research runs a month (at most 15 a day, set in the API); alerts and CSV export are Pro and
-- above. Habit forms on browsing and a real evaluation takes 20 to 40 runs, so the paywall sits on alerts, exports
-- and volume, not on exploring. Existing alerts are untouched (no free account owns one).
update public.api_plans set ai_monthly = 30, alerts_max = 0, exports = false where plan = 'free';
