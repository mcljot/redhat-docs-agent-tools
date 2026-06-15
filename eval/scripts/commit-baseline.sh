#!/usr/bin/env bash
# Strip large files from an eval run and prepare it for commit as a shared baseline.
#
# Usage: bash eval/scripts/commit-baseline.sh <run-id> [<new-name>]
#
# Examples:
#   bash eval/scripts/commit-baseline.sh 2026-06-11-opus baseline-main-2026-06-11
#   bash eval/scripts/commit-baseline.sh 2026-06-11-opus   # keeps original name
#
# What it keeps:
#   summary.yaml, collection.json, run_result.json, analysis.md, report.html
#   cases/<case>/run_result.json, cases/<case>/input.yaml
#   cases/<case>/_modified/.output/  (collected AsciiDoc output for pairwise judges)
#
# What it strips:
#   stdout.log, stderr.log, subagents/ (debug transcripts)
#   _modified/.agent_workspace/ (intermediate pipeline artifacts)
#   _modified/hooks/, _modified/tool_handlers.yaml

set -euo pipefail

RUNS_DIR="${AGENT_EVAL_RUNS_DIR:-eval/runs}"
RUN_ID="${1:?Usage: $0 <run-id> [<new-name>]}"
NEW_NAME="${2:-}"

SRC="$RUNS_DIR/$RUN_ID"
[ -d "$SRC" ] || { echo "ERROR: $SRC does not exist"; exit 1; }

if [ -n "$NEW_NAME" ] && [ "$NEW_NAME" != "$RUN_ID" ]; then
    DEST="$RUNS_DIR/$NEW_NAME"
    [ -d "$DEST" ] && { echo "ERROR: $DEST already exists"; exit 1; }
    mv "$SRC" "$DEST"
    echo "Renamed: $RUN_ID -> $NEW_NAME"

    # Update run_id in summary.yaml
    if [ -f "$DEST/summary.yaml" ]; then
        python3 -c "
import yaml
with open('$DEST/summary.yaml') as f:
    data = yaml.safe_load(f)
data['run_id'] = '$NEW_NAME'
with open('$DEST/summary.yaml', 'w') as f:
    yaml.dump(data, f, default_flow_style=False, sort_keys=True)
"
    fi
else
    DEST="$SRC"
    NEW_NAME="$RUN_ID"
fi

before=$(du -sh "$DEST" | awk '{print $1}')

for case_dir in "$DEST"/cases/*/; do
    [ -d "$case_dir" ] || continue

    rm -f "$case_dir/stdout.log" "$case_dir/stderr.log"
    rm -rf "$case_dir/subagents/"
    rm -rf "$case_dir/_modified/.agent_workspace"
    rm -rf "$case_dir/_modified/hooks"
    rm -f "$case_dir/_modified/tool_handlers.yaml"
done

after=$(du -sh "$DEST" | awk '{print $1}')
echo "Stripped: $before -> $after"
echo ""
echo "Baseline ready at: $DEST"
echo ""
echo "To commit:"
echo "  git checkout -b baseline/$NEW_NAME"
echo "  git add $DEST/"
echo "  git commit -m \"eval: add baseline $NEW_NAME\""
echo "  git push -u origin baseline/$NEW_NAME"
