#!/bin/bash
# eval-baseline-prompt.sh
#
# Stop hook: when a successful eval run exists on the main branch
# and hasn't been committed, remind the user to share it.
#
# Exit codes:
#   0 = allow stop (always — this is advisory, never blocks)
#
# Outputs reminder to stderr so Claude sees it and can relay to user.

set -u

if ! cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null; then
  exit 0
fi

RUNS_DIR="${AGENT_EVAL_RUNS_DIR:-eval/runs}"

# Only prompt on main branch
BRANCH=$(git branch --show-current 2>/dev/null)
if [ "$BRANCH" != "main" ]; then
  exit 0
fi

# Look for uncommitted runs with a summary.yaml (completed + scored)
shopt -s nullglob
RUNS=("$RUNS_DIR"/*/summary.yaml)
shopt -u nullglob

if [ ${#RUNS[@]} -eq 0 ]; then
  exit 0
fi

UNCOMMITTED=()
for summary in "${RUNS[@]}"; do
  run_dir=$(dirname "$summary")
  run_id=$(basename "$run_dir")

  # Skip already-committed baselines
  case "$run_id" in
    baseline-main-*) continue ;;
  esac

  # Skip if git-tracked
  if git ls-files --error-unmatch "$summary" >/dev/null 2>&1; then
    continue
  fi

  UNCOMMITTED+=("$run_id")
done

if [ ${#UNCOMMITTED[@]} -eq 0 ]; then
  exit 0
fi

{
  echo ""
  echo "[eval] You have ${#UNCOMMITTED[@]} scored eval run(s) on main that haven't been shared:"
  for id in "${UNCOMMITTED[@]}"; do
    echo "  - $id"
  done
  echo ""
  echo "To share as a baseline for the team:"
  echo "  bash eval/scripts/commit-baseline.sh <run-id> baseline-main-YYYY-MM-DD"
  echo ""
} >&2

exit 0
