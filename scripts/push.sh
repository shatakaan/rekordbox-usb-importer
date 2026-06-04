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
  --exclude "build/PlaylistConverter/" \
  --exclude ".claude/worktrees/" \
  "$PROJECT/" "$MIRROR/"

# Restore mirror's own .gitignore (rsync overwrites it with the main project's)
cat > "$MIRROR/.gitignore" << 'MIRRORIGNORE'
# Python virtual env (too large, recreatable)
.venv/

# Build output (in GitHub Releases)
dist/
__pycache__/
*.pyc
*.pyo
build/app/
build/PlaylistConverter/

# macOS
.DS_Store
**/.DS_Store

# Worktrees (temp Claude build dirs)
.claude/worktrees/
MIRRORIGNORE

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
