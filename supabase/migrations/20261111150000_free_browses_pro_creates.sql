-- Free accounts browse everything (deals, companies, investors, markets, countries, comparables, country risk), may
-- try 30 briefs and research runs a month (at most 15 a day, set in the API) and keep 3 alerts, the reason to come
-- back tomorrow; CSV export and higher volumes are Pro and above. Habit forms on browsing and on alerts, and a real
-- evaluation takes 20 to 40 runs, so the paywall sits on exports and volume, not on exploring or returning.
update public.api_plans set ai_monthly = 30, alerts_max = 3, exports = false where plan = 'free';
