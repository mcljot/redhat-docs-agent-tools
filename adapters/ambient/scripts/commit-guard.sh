#!/usr/bin/env bash
# Guard against committing from the agent-tools repository.
# Run before commit.sh to ensure we're targeting a docs repo, not this repo.
#
# Exit codes:
#   0 = safe to proceed
#   1 = refusing (agent-tools repo detected)
#
# Usage: bash commit-guard.sh [--repo-path <path>]
set -euo pipefail

REPO_PATH="${1:-.}"

if [[ "$1" == "--repo-path" ]]; then
  REPO_PATH="${2:-.}"
fi

if ! git -C "$REPO_PATH" rev-parse --git-dir >/dev/null 2>&1; then
  echo "ERROR: ${REPO_PATH} is not a git repository." >&2
  exit 1
fi

REPO_DIR="$(git -C "$REPO_PATH" rev-parse --show-toplevel)"

if [[ -d "${REPO_DIR}/adapters/ambient" ]]; then
  echo "ERROR: Refusing to commit from the agent-tools repository. Target a docs repository instead." >&2
  exit 1
fi
