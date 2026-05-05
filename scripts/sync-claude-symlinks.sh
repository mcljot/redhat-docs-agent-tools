#!/usr/bin/env bash
# Sync .claude/skills/, .claude/agents/, and .claude/reference/ symlinks
# with the contents of plugins/*/. Only manages symlinks — real files and
# directories (e.g., .claude/skills/batch-controller/) are left untouched.
#
# Usage:
#   ./scripts/sync-claude-symlinks.sh          # create/update symlinks
#   ./scripts/sync-claude-symlinks.sh --check  # exit 1 if out of sync
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHECK_MODE=false
[[ "${1:-}" == "--check" ]] && CHECK_MODE=true

CHANGED=0

sync_symlinks() {
  local target_dir="$1"  # e.g., .claude/skills
  local source_glob="$2" # e.g., plugins/*/skills/*
  local type="$3"        # "dir" or "file"

  mkdir -p "${REPO_ROOT}/${target_dir}"

  # Remove stale symlinks (target no longer exists, or points outside plugins/)
  for link in "${REPO_ROOT}/${target_dir}/"*; do
    [ -L "$link" ] || continue
    local dest
    dest="$(readlink "$link")"
    # Resolve relative to the symlink's directory
    if [[ "$dest" != /* ]]; then
      dest="$(cd "$(dirname "$link")" && cd "$(dirname "$dest")" && pwd)/$(basename "$dest")"
    fi
    if [ ! -e "$dest" ]; then
      if $CHECK_MODE; then
        echo "STALE: ${link#"${REPO_ROOT}/"} -> $(readlink "$link")"
      else
        rm "$link"
        echo "Removed stale: ${link#"${REPO_ROOT}/"}"
      fi
      CHANGED=1
    fi
  done

  # Create missing symlinks
  for source in ${REPO_ROOT}/${source_glob}; do
    [ -e "$source" ] || continue
    if [[ "$type" == "dir" ]]; then
      # Skip dirs without SKILL.md (not a real skill)
      [ -f "$source/SKILL.md" ] || continue
    fi
    local name
    name="$(basename "$source")"
    local link="${REPO_ROOT}/${target_dir}/${name}"
    local rel_path
    rel_path="$(python3 -c "import os.path; print(os.path.relpath('$source', '${REPO_ROOT}/${target_dir}'))")"

    if [ -L "$link" ]; then
      # Symlink exists — check it points to the right place
      local current
      current="$(readlink "$link")"
      if [ "$current" = "$rel_path" ]; then
        continue
      fi
      if $CHECK_MODE; then
        echo "WRONG TARGET: ${link#"${REPO_ROOT}/"} -> $current (expected $rel_path)"
      else
        rm "$link"
        ln -s "$rel_path" "$link"
        echo "Updated: ${link#"${REPO_ROOT}/"} -> $rel_path"
      fi
      CHANGED=1
    elif [ -e "$link" ]; then
      # Real file/dir exists — don't touch it
      continue
    else
      if $CHECK_MODE; then
        echo "MISSING: ${link#"${REPO_ROOT}/"} -> $rel_path"
      else
        ln -s "$rel_path" "$link"
        echo "Created: ${link#"${REPO_ROOT}/"} -> $rel_path"
      fi
      CHANGED=1
    fi
  done
}

sync_symlinks ".claude/skills"    "plugins/*/skills/*"    "dir"
sync_symlinks ".claude/agents"    "plugins/*/agents/*.md" "file"
sync_symlinks ".claude/reference" "plugins/*/reference/*.md" "file"

if $CHECK_MODE && [ "$CHANGED" -ne 0 ]; then
  echo ""
  echo "Symlinks are out of sync. Run ./scripts/sync-claude-symlinks.sh to fix."
  exit 1
fi

if [ "$CHANGED" -eq 0 ]; then
  echo "Symlinks are up to date."
fi
