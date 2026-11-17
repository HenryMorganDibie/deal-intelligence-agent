#!/usr/bin/env bash
# Vercel "Ignored Build Step" for the web project (root directory web/): exit 0 skips the deployment, exit 1
# builds it. The web app reads only files under web/, so commits that change nothing here (API code, feed
# replacements, research data for the API) no longer redeploy it.
prev="${VERCEL_GIT_PREVIOUS_SHA:-}"
if [ -z "$prev" ] || ! git cat-file -e "${prev}^{commit}" 2>/dev/null; then
  echo "No previous deployment to compare with: building."; exit 1
fi
# The same commit again is a deliberate redeploy (usually to pick up a changed environment variable): build it.
if [ "$(git rev-parse "$prev")" = "$(git rev-parse HEAD)" ]; then
  echo "Redeploy of the same commit: building."; exit 1
fi
# Vercel's previous SHA is the last deployment attempted, not the last one built: when a build was skipped or
# blocked (the free plan's daily deployment limit), web changes behind it were never compared again. The last five
# commits are checked as well, so such changes still build. A skipped deployment counts against the limit like a
# built one, so building costs only build time.
recent="$(git rev-parse --verify -q HEAD~5 || git rev-list --max-parents=0 HEAD | tail -1)"
if git diff --quiet "$prev" HEAD -- . ':(exclude)e2e' ':(exclude)tests' ':(exclude)*.md' \
   && git diff --quiet "$recent" HEAD -- . ':(exclude)e2e' ':(exclude)tests' ':(exclude)*.md'; then
  echo "Nothing under web/ changed: skipping this deployment."; exit 0
fi
echo "Web files changed: building."; exit 1
