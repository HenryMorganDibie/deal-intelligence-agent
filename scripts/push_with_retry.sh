#!/usr/bin/env bash
# Push the current commit to main, retrying when GitHub errors or main moved meanwhile.
# Up to 5 attempts with growing pauses (5, 10, 20, 40 seconds); between attempts the commit is rebased onto the
# latest main, so concurrent jobs that commit generated files never block each other.
#
# Generated files can still conflict when two jobs rebuild the same file at once (a rebase cannot merge two
# versions of an archive). Set REGENERATE_CMD (and REGENERATE_PATHS, COMMIT_MSG) and, on a conflict, the job
# starts again from the latest main, rebuilds the file there and commits that instead: always correct for a
# generated file, and a no-op when the other job already published the same result.
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
  git fetch origin "$branch" || continue
  if git rebase "origin/${branch}"; then
    continue
  fi
  git rebase --abort 2>/dev/null
  if [ -z "${REGENERATE_CMD:-}" ]; then
    echo "::error::Rebase onto ${branch} hit a conflict."
    exit 1
  fi
  echo "Conflict on generated files; rebuilding them on the latest ${branch}."
  git reset --hard "origin/${branch}"
  bash -c "$REGENERATE_CMD" || { echo "::error::Regeneration failed."; exit 1; }
  # shellcheck disable=SC2086
  git add ${REGENERATE_PATHS:-.}
  if git diff --cached --quiet; then
    echo "The latest ${branch} already has this result; nothing to push."
    exit 0
  fi
  git commit -m "${COMMIT_MSG:-Regenerate data files}"
done
echo "::error::Could not push to ${branch} after 5 attempts."
exit 1
