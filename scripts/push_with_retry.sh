#!/usr/bin/env bash
# Push the current commit to main, retrying when GitHub errors or main moved meanwhile.
# Up to 5 attempts with growing pauses (5, 10, 20, 40 seconds); between attempts the commit is rebased onto the
# latest main, so concurrent jobs that commit generated files never block each other.
set -uo pipefail
branch="${1:-main}"
for attempt in 1 2 3 4 5; do
  if git push origin "HEAD:${branch}"; then
    echo "Pushed on attempt ${attempt}."
    exit 0
  fi
  [ "$attempt" -eq 5 ] && break
  wait=$(( 5 * 2 ** (attempt - 1) ))
  echo "Push failed (attempt ${attempt}); retrying in ${wait}s after rebasing onto the latest ${branch}."
  sleep "$wait"
  git fetch origin "$branch" && git rebase "origin/${branch}" || { git rebase --abort 2>/dev/null; exit 1; }
done
echo "::error::Could not push to ${branch} after 5 attempts."
exit 1
