#!/bin/bash
# push.sh — Push to both public and private repos
#
# Public  (origin):  tracked files only, respects .gitignore
# Private (mirror):  everything — code, design assets, .claude/ memory
#                    dist/ excluded (too large; lives in GitHub Releases)
#
# Usage: bash scripts/push.sh
#        bash scripts/push.sh "optional commit message"

set -e

PROJECT="/Users/andreasmrogenda/Claude Projekte/Playlist Converter Rekordbox"
MIRROR="$HOME/.rekordbox-private-mirror"

# ── 1. Push public repo ───────────────────────────────────────────────────────
echo "▶ Pushing to public repo (origin)..."
git -C "$PROJECT" push origin master
echo "  ✓ Public repo up to date"

# ── 2. Sync mirror and push private repo ─────────────────────────────────────
echo "▶ Syncing private mirror..."
rsync -a --delete \
  --exclude ".git/" \
  --exclude ".venv/" \
  --exclude "dist/" \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  --exclude "*.pyo" \
  --exclude "build/app/" \
  --exclude ".claude/worktrees/" \
  "$PROJECT/" "$MIRROR/"

cd "$MIRROR"

if [ -n "$(git status --porcelain)" ]; then
  MSG="${1:-sync: $(date '+%Y-%m-%d %H:%M')}"
  git add -A
  git commit -m "$MSG"
  echo "▶ Pushing to private repo..."
  git push private master
  echo "  ✓ Private repo up to date"
else
  echo "  ✓ Private repo already up to date (no changes)"
fi

echo ""
echo "Done. Both repos pushed."
