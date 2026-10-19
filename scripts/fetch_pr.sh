#!/usr/bin/env bash
# Fetch PR metadata and diff for the all-in-pr-podcast skill.
# Usage: fetch_pr.sh <pr-url-or-number>
# Prints the episode output directory on stdout.
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <pr-url-or-number>" >&2
  exit 2
fi
PR="$1"

FIELDS=number,title,body,url,author,baseRefName,headRefName,state,additions,deletions,changedFiles,files,commits,labels,reviews,comments

meta=$(gh pr view "$PR" --json "$FIELDS")
url=$(jq -r .url <<<"$meta")
number=$(jq -r .number <<<"$meta")
# https://host/org/repo/pull/123 -> repo
repo=$(sed -E 's#https?://[^/]+/[^/]+/([^/]+)/pull/.*#\1#' <<<"$url")

OUT="${PR_PODCAST_DIR:-$HOME/pr-podcasts}/${repo}-${number}"
mkdir -p "$OUT"

jq . <<<"$meta" >"$OUT/pr.json"
gh pr diff "$url" --color=never >"$OUT/diff.patch"  # final combined diff, not per-commit patches
jq -r '.files[] | "+\(.additions)\t-\(.deletions)\t\(.path)"' "$OUT/pr.json" >"$OUT/diffstat.txt"

lines=$(wc -l <"$OUT/diff.patch" | tr -d ' ')
echo "fetched $url ($lines diff lines, $(jq -r .changedFiles "$OUT/pr.json") files)" >&2
echo "$OUT"
