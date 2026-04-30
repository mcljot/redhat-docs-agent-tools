#!/usr/bin/env bash
set -euo pipefail

MARKETPLACE_DIR="$HOME/.claude/plugins/marketplaces/redhat-docs-agent-tools"
CACHE_DIR="$HOME/.claude/plugins/cache/redhat-docs-agent-tools"

usage() {
    echo "Usage: $(basename "$0") --branch <branch> --plugin <plugin> [--reset]"
    echo "For example:"
    echo "scripts/test-upstream-plugin.sh --branch feat/fanout-subagents-per-requirement --plugin docs-tools"
    echo
    echo "Checkout an upstream branch and clear the plugin cache."
    echo
    echo "Options:"
    echo "  --branch <branch>   Remote branch to fetch and checkout"
    echo "  --plugin <plugin>   Plugin name whose cache to delete (e.g. docs-tools)"
    echo "  --reset             Reset the marketplace repo to upstream main and clear"
    echo "                      the plugin cache. Requires --plugin; --branch is ignored."
    echo "  -h, --help          Show this help"
    exit 1
}

branch=""
plugin=""
reset=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --branch) branch="$2"; shift 2 ;;
        --plugin) plugin="$2"; shift 2 ;;
        --reset) reset=true; shift ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1"; usage ;;
    esac
done

if [[ "$reset" == true ]]; then
    if [[ -z "$plugin" ]]; then
        echo "Error: --plugin <plugin> is required with --reset."
        echo
        usage
    fi

    plugin_cache="$CACHE_DIR/$plugin"
    if [[ -d "$plugin_cache" ]]; then
        echo "Deleting plugin cache: $plugin_cache"
        rm -rf "$plugin_cache"
        echo "Cache deleted."
    else
        echo "Warning: cache directory does not exist: $plugin_cache"
    fi

    cd "$MARKETPLACE_DIR"
    echo "Fetching origin/main ..."
    git fetch origin main
    echo "Checking out main and resetting to origin/main ..."
    git checkout main
    git reset --hard origin/main
    echo
    echo "Done. Reset to origin/main."
    echo "Branch: $(git branch --show-current)"
    exit 0
fi

if [[ -z "$branch" || -z "$plugin" ]]; then
    echo "Error: both --branch <branch> and --plugin <plugin> are required."
    echo
    usage
fi

plugin_cache="$CACHE_DIR/$plugin"
if [[ -d "$plugin_cache" ]]; then
    echo "Deleting plugin cache: $plugin_cache"
    rm -rf "$plugin_cache"
    echo "Cache deleted."
else
    echo "Warning: cache directory does not exist: $plugin_cache"
fi

cd "$MARKETPLACE_DIR"

echo "Fetching origin/$branch ..."
git fetch origin "$branch":"refs/remotes/origin/$branch"

current_branch=$(git branch --show-current)
if [[ "$current_branch" == "$branch" ]]; then
    echo "Already on $branch — pulling latest."
    git pull origin "$branch"
else
    if git show-ref --verify --quiet "refs/heads/$branch" 2>/dev/null; then
        echo "Local branch $branch exists — switching and pulling."
        git checkout "$branch"
        git pull origin "$branch"
    else
        echo "Creating local branch $branch tracking origin/$branch."
        git checkout -b "$branch" "origin/$branch"
    fi
fi

echo
echo "Done. Branch: $(git branch --show-current)"
echo "Cache cleared: $plugin_cache"
