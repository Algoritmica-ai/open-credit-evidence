#!/usr/bin/env bash
# Publish the engine as a Hugging Face Space (Docker SDK).
#
#   ./deploy/huggingface/push_to_space.sh Algoritmica/credit-evidence-engine
#
# Assembles a Space repo from the project — source, packs, regulations, the
# committed runs, packaging metadata — plus the Dockerfile and the Space card
# beside this script. Requires git and `hf auth login` with write access.
# NVIDIA_API_KEY is added afterwards as a Space secret, in the Space settings.
set -euo pipefail

SPACE="${1:-}"
if [[ -z "$SPACE" || "$SPACE" != */* ]]; then
  echo "usage: $0 <owner>/<space-name>" >&2; exit 2
fi
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

hf auth whoami >/dev/null || { echo "Not logged in. Run: hf auth login" >&2; exit 1; }
hf repo create "$SPACE" --repo-type space --space-sdk docker --exist-ok >/dev/null

# The token rides in the clone URL of a temp directory the EXIT trap removes.
TOKEN="$(hf auth token 2>/dev/null || true)"
[[ -n "$TOKEN" ]] || { echo "No token from 'hf auth token'. Run: hf auth login" >&2; exit 1; }
git clone -q "https://user:${TOKEN}@huggingface.co/spaces/$SPACE" "$STAGING/space"
cd "$STAGING/space"

rm -rf src packs regulations runs specs pyproject.toml LICENSE NOTICE THIRD_PARTY_NOTICES.md Dockerfile README.md
cp -R "$ROOT/src" "$ROOT/packs" "$ROOT/regulations" "$ROOT/specs" .
mkdir -p runs
for run in "$ROOT"/runs/*/; do
  [[ -f "$run/checksums.sha256" ]] && cp -R "$run" runs/
done
cp "$ROOT/pyproject.toml" "$ROOT/LICENSE" "$ROOT/NOTICE" "$ROOT/THIRD_PARTY_NOTICES.md" .
cp "$HERE/Dockerfile" "$HERE/README.md" .
# Nothing generated, nothing private, no vector index (rebuilt from vectors.jsonl).
find . -path ./.git -prune -o \( -name '__pycache__' -o -name 'passages.db' -o -name 'answer_key.json' -o -name '*.parquet' \) -print0 | xargs -0 rm -rf
rm -f .env

git add -A
if git diff --cached --quiet; then echo "Nothing changed."; exit 0; fi
git -c user.name="${GIT_AUTHOR_NAME:-$(git config user.name || echo deploy)}" \
    -c user.email="${GIT_AUTHOR_EMAIL:-$(git config user.email || echo deploy@localhost)}" \
    commit -q -m "Deploy Credit Evidence Engine"
git push -q
echo "Done: https://huggingface.co/spaces/$SPACE — the first build takes a few minutes (Logs tab)."
