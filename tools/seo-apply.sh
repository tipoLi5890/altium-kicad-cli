#!/usr/bin/env bash
#
# seo-apply.sh — apply the repo-settings SEO assets from docs/seo.md (single source of truth).
#
# Reads the GitHub About string, homepage, and the 20 Topics out of docs/seo.md and applies them with
# the GitHub CLI:
#   gh repo edit --description "<about>" --homepage "<homepage>"
#   gh repo edit --add-topic <topic>      # once per topic
#
# Usage:
#   tools/seo-apply.sh [REPO] [--dry-run]
#     REPO       optional "owner/name" (defaults to the repo gh detects from cwd)
#     --dry-run  print the gh commands instead of running them
#
# Requires: bash, awk, grep, and the `gh` CLI authenticated (`gh auth login`).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SEO="$ROOT/docs/seo.md"

REPO=""
DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) sed -n '3,17p' "$0"; exit 0 ;;
    *) REPO="$arg" ;;
  esac
done

[ -f "$SEO" ] || { echo "error: cannot find $SEO" >&2; exit 1; }
command -v awk >/dev/null 2>&1 || { echo "error: awk not found" >&2; exit 1; }
if [ "$DRY_RUN" -eq 0 ]; then
  command -v gh >/dev/null 2>&1 || { echo "error: gh CLI not found (install: https://cli.github.com)" >&2; exit 1; }
fi

# Extract the first fenced code block following a "## <section>" heading.
extract_block() {
  awk -v sec="$1" '
    $0 ~ ("^## " sec) {f=1; next}
    f && /^```/ {c++; if (c==1){inb=1; next} if (c==2){exit}}
    f && inb {print}
  ' "$SEO"
}

ABOUT="$(extract_block '7\.1 ')"
ABOUT="${ABOUT#"${ABOUT%%[![:space:]]*}"}"   # ltrim
ABOUT="${ABOUT%"${ABOUT##*[![:space:]]}"}"   # rtrim
HOMEPAGE="$(grep '^Homepage' "$SEO" | head -n1 | grep -oE 'https?://[^`]+' | head -n1 || true)"
TOPICS=()
while IFS= read -r line; do
  [ -n "$line" ] && TOPICS+=("$line")
done < <(extract_block '7\.2 ' | grep -E '^[a-z0-9-]+$')

[ -n "$ABOUT" ] || { echo "error: could not parse About string from $SEO (## 7.1)" >&2; exit 1; }
[ "${#TOPICS[@]}" -gt 0 ] || { echo "error: could not parse Topics from $SEO (## 7.2)" >&2; exit 1; }

echo "About    (${#ABOUT} chars): $ABOUT" >&2
echo "Homepage: ${HOMEPAGE:-<none>}" >&2
echo "Topics   (${#TOPICS[@]}): ${TOPICS[*]}" >&2
[ "${#ABOUT}" -le 350 ] || echo "warning: About exceeds 350 chars (GitHub limit)" >&2
[ "${#TOPICS[@]}" -eq 20 ] || echo "warning: expected exactly 20 topics, found ${#TOPICS[@]}" >&2

REPO_ARGS=()
[ -n "$REPO" ] && REPO_ARGS=("$REPO")

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf 'DRY-RUN:'; printf ' %q' "$@"; printf '\n'
  else
    "$@"
  fi
}

DESC_ARGS=(gh repo edit ${REPO_ARGS[@]+"${REPO_ARGS[@]}"} --description "$ABOUT")
[ -n "$HOMEPAGE" ] && DESC_ARGS+=(--homepage "$HOMEPAGE")
run "${DESC_ARGS[@]}"

for t in "${TOPICS[@]}"; do
  run gh repo edit ${REPO_ARGS[@]+"${REPO_ARGS[@]}"} --add-topic "$t"
done

echo "done: applied About/homepage + ${#TOPICS[@]} topics" >&2
