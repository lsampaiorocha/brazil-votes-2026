#!/usr/bin/env bash
# Every 10 minutes: each update makes every open page re-download ~750 KB, so faster costs viewers data.
set -u
cd "$(dirname "$0")"
while true; do
  git add web/data
  if ! git diff --cached --quiet -- web/data; then
    git commit -q -m "Update TSE data $(date +%H:%M)" -- web/data && git push -q origin main && echo "$(date +%H:%M:%S) published"
  fi
  sleep 600
done
