#!/usr/bin/env bash
# Vercel "Ignored Build Step" for the web project (root directory web/): exit 0 skips the deployment, exit 1
# builds it. The web app reads only files under web/, so commits that change nothing here (API code, feed
# replacements, research data for the API) no longer redeploy it.
prev="${VERCEL_GIT_PREVIOUS_SHA:-}"
if [ -z "$prev" ] || ! git cat-file -e "${prev}^{commit}" 2>/dev/null; then
  echo "No previous deployment to compare with: building."; exit 1
fi
if git diff --quiet "$prev" HEAD -- . ':(exclude)e2e' ':(exclude)tests' ':(exclude)*.md'; then
  echo "Nothing under web/ changed: skipping this deployment."; exit 0
fi
echo "Web files changed: building."; exit 1
