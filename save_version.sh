#!/bin/bash
# save_version.sh — Run after each Claude update
# Usage:
#   ./save_version.sh "added 3DP bands and hot sums"
#   ./save_version.sh                                  # auto-generates message
#
# HANDY COMMANDS:
#   git tag                                        # list all versions
#   git log --oneline --decorate                   # version history
#   git show v1.3 --stat                           # what files changed in v1.3
#   git diff v1.2..v1.3                            # full diff between versions
#   git diff v1.2..v1.3 -- app.py                  # diff just one file
#   git checkout v1.2 -- templates/rbtl_backtest.html  # restore one file from v1.2
#   git checkout v1.2 -- .                          # restore ALL files from v1.2
set -e

# Check we're in a git repo
if ! git rev-parse --is-inside-work-tree &>/dev/null; then
    echo "❌ Not a git repo. Run setup_git.sh first."
    exit 1
fi

# Check if there are any changes
if git diff --quiet && git diff --cached --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
    echo "✅ No changes detected. Nothing to save."
    exit 0
fi

# Show what's changed
echo "📂 Changed files:"
echo "─────────────────"
git status --short
echo ""

# Auto-generate message from changed filenames if none provided
if [ -n "$1" ]; then
    MSG="$1"
else
    CHANGED=$(git status --short | awk '{print $2}' | sed 's|.*/||' | paste -sd ', ' -)
    MSG="update ${CHANGED}"
fi

DATE=$(date +%Y-%m-%d\ %H:%M)

# Auto-increment version tag
LAST_TAG=$(git tag --sort=-v:refname | grep -E '^v[0-9]' | head -1)
if [ -z "$LAST_TAG" ]; then
    NEXT_TAG="v1.0"
else
    MAJOR=$(echo "$LAST_TAG" | sed 's/^v//' | cut -d. -f1)
    MINOR=$(echo "$LAST_TAG" | sed 's/^v//' | cut -d. -f2)
    NEXT_TAG="v${MAJOR}.$((MINOR + 1))"
fi

# Commit and tag
git add -A
git commit -m "$NEXT_TAG: $MSG"
git tag -a "$NEXT_TAG" -m "$MSG — $DATE"

echo ""
echo "✅ Saved as $NEXT_TAG: $MSG"
echo ""
echo "📋 Version History:"
echo "─────────────────"
git log --oneline --decorate -8
echo ""
echo "📦 Files in $NEXT_TAG:"
echo "─────────────────"
git show --stat --format="" "$NEXT_TAG"
echo ""
echo "💡 Restore any file:  git checkout v1.0 -- app.py"
echo "💡 Compare versions:  git diff v1.2..${NEXT_TAG}"
