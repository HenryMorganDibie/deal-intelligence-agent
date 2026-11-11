-- Free accounts browse everything (deals, companies, investors, markets, countries, comparables, country risk);
-- briefs and research runs, alerts and CSV export are Pro and above. Habit forms on browsing, so the paywall sits on
-- what a user creates, not on what they explore. Existing alerts are untouched (no free account owns one).
update public.api_plans set ai_monthly = 0, alerts_max = 0, exports = false where plan = 'free';
