#!/usr/bin/env bash
# Vercel "Ignored Build Step" for the API project: exit 0 skips the deployment, exit 1 builds it.
# A deployment empties the edge cache and restarts every function instance (each cold start reinstalls the
# Python packages), so the API is redeployed only when something it serves has changed. Automatic data commits
# that only the web app or the GitHub jobs read (feed replacements, Corporate of the Week) no longer redeploy it.
prev="${VERCEL_GIT_PREVIOUS_SHA:-}"
if [ -z "$prev" ] || ! git cat-file -e "${prev}^{commit}" 2>/dev/null; then
  echo "No previous deployment to compare with: building."; exit 1
fi
changed="$(git diff --name-only "$prev" HEAD)"
# Paths the API never reads at runtime.
ignored='^(web/|\.github/|tests/|scripts/|supabase/|deploy/|evaluation/review/[^/]+/pool\.jsonl$|[^/]+\.md$|docs/[^/]+\.md$|LICENSE$|src/data/feed_overrides\.json$)'
if [ -n "$changed" ] && printf '%s\n' "$changed" | grep -qvE "$ignored"; then
  echo "API files changed: building."; printf '%s\n' "$changed" | grep -vE "$ignored" | head -20; exit 1
fi
echo "Nothing the API serves changed: skipping this deployment."; exit 0
