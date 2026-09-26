#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
#
# Bring the Synthetic Data Designer into this repository as src/sdd, pinned to one
# commit of the repository it lives in: the deeploans monorepo
# (https://github.com/Algoritmica-ai/deeploans, folder synthetic-data-designer/).
# The designer generates the test cases, and the evidence UI serves its web app at /sdd/.
#
#   scripts/sync_sdd.sh <deeploans checkout>/synthetic-data-designer
#
# Copies the package, its licence and notice, and its bundled recipes; adds this
# repository's credit-underwriting recipe to them, so the designer opens it; records the
# commit in src/sdd/VENDORED.md. Change the designer in its own repository, then sync.
set -euo pipefail
SRC=$(cd "${1:?usage: sync_sdd.sh <deeploans checkout>/synthetic-data-designer}" && pwd)
HERE=$(cd "$(dirname "$0")/.." && pwd)
DST=$HERE/src/sdd

if [[ ! -d "$SRC/src/sdd" ]]; then
  echo "$SRC holds no src/sdd: point at the designer's folder, e.g. deeploans/synthetic-data-designer" >&2
  exit 1
fi
if [[ -n "$(git -C "$SRC" status --porcelain -- .)" ]]; then
  echo "$SRC has uncommitted changes: commit them in the designer's repository first" >&2
  exit 1
fi
commit=$(git -C "$SRC" rev-parse HEAD)
branch=$(git -C "$SRC" rev-parse --abbrev-ref HEAD)
url=$(git -C "$SRC" remote get-url origin 2>/dev/null || echo "unknown")
folder=$(git -C "$SRC" rev-parse --show-prefix)
folder=${folder%/}

mkdir -p "$DST"
rsync -a --delete --exclude __pycache__ --exclude .DS_Store "$SRC/src/sdd/" "$DST/"
mkdir -p "$DST/packs"
cp "$SRC"/packs/*.yaml "$DST/packs/"
cp "$HERE/specs/credit_underwriting.yaml" "$DST/packs/"
cp "$SRC/LICENSE" "$DST/LICENSE"
cp "$SRC/NOTICE" "$DST/NOTICE"
cat > "$DST/VENDORED.md" <<EOF
# Synthetic Data Designer, vendored

This directory is a copy of the Synthetic Data Designer package (\`sdd\`), pinned to one
commit of its own repository. Change the designer there, then run
\`scripts/sync_sdd.sh <checkout>\` here; do not edit these files in place.

- Source: $url, folder \`${folder:-.}\`
- Commit: \`$commit\` (branch \`$branch\`)
- Synced: $(date -u +%Y-%m-%dT%H:%M:%SZ)
- Licence: Apache-2.0 (\`LICENSE\`, \`NOTICE\`)

\`packs/\` holds the designer's bundled recipes and this repository's
\`specs/credit_underwriting.yaml\`, the recipe the test cases are generated from.
EOF
echo "synced sdd at ${commit:0:12} ($branch) into src/sdd"
