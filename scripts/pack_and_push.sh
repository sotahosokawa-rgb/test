#!/usr/bin/env bash
# Usage: pack_and_push.sh SRC_DIR DEST_FILE(.tar.age) MESSAGE
set -euo pipefail
src="$1"; dest="$2"; msg="$3"
mkdir -p "$(dirname "$dest")"
tar -C "$src" -cf - . | age -r "$(cat scripts/age_recipient.txt)" -o "$dest"
git config user.name "boatrace-bot"
git config user.email "boatrace-bot@users.noreply.github.com"
git add "$dest"
git commit -q -m "$msg [skip ci]" || { echo "nothing to commit"; exit 0; }
for i in 1 2 3 4 5; do
  git pull -q --rebase origin "${GITHUB_REF_NAME}" && git push -q origin "HEAD:${GITHUB_REF_NAME}" && exit 0
  git rebase --abort 2>/dev/null || true
  sleep $((i * 7))
done
exit 1
