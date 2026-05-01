# Docs Workflow Simplification

**Date:** 2026-03-22
**Status:** Approved
**Scope:** docs-workflow command, docs-writer agent, docs-integrator agent removal

## Problem

The docs-workflow defaults to writing drafts into a `.agent_workspace/` staging area and relies on a convoluted `--integrate` flag with a separate `docs-integrator` agent to place files into the repository. This creates unnecessary friction — most users want docs written directly into the repo.

## Decision

Flip the default: the workflow creates a clean branch from the upstream default and writes documentation directly into the repository. A `--draft` flag preserves the old staging-area behavior. The `docs-integrator` agent is removed; its logic is absorbed into the `docs-writer` agent.

## Design

### New default: update-in-place on a clean branch

1. The orchestrator auto-detects the remote and default branch
2. Fetches the JIRA ticket summary and derives a branch name: `<ticket-lowercase>_<short-desc>` (e.g., `rhaistrat-123_add-autoscaling-support`)
3. Creates and checks out the branch from `<remote>/<default-branch>`
4. The docs-writer detects the repo's build framework, analyzes conventions, and writes files directly to the correct repo locations
5. Technical and style reviewers operate on files at their repo locations
6. Result: a clean branch with reviewed docs ready for PR

### `--draft` mode (old behavior)

When `--draft` is passed:
- No branch creation — stays on current branch
- Writer saves to `.agent_workspace/drafts/<ticket>/` staging area
- Reviewers operate on the staging area
- No repo integration

### `--integrate` removal

The `--integrate` flag and the `docs-integrator` agent are removed entirely. The old `--integrate` behavior is now the default. Users who previously ran without `--integrate` should use `--draft`.

## Changes by file

### `plugins/docs-tools/commands/docs-workflow.md` (orchestrator)

#### Synopsis

```
/docs-workflow [action] <ticket> [--pr <url>] [--create-jira <PROJECT>] [--mkdocs] [--draft]
```

#### New: branch creation step (between Step 2 and Step 3)

After pre-flight validation, before state initialization:

1. Auto-detect remote and default branch:
   ```bash
   REMOTE=$(git remote | head -1)
   DEFAULT_BRANCH=$(git remote show "$REMOTE" 2>/dev/null | awk '/HEAD branch/ {print $NF}')
   ```

2. Fetch latest:
   ```bash
   git fetch "$REMOTE" "$DEFAULT_BRANCH"
   ```

3. Derive branch name from JIRA summary:
   ```bash
   SUMMARY=$(curl -s -u "${JIRA_EMAIL}:${JIRA_AUTH_TOKEN}" \
     "${JIRA_URL}/rest/api/2/issue/${TICKET}?fields=summary" | jq -r '.fields.summary')
   SHORT_DESC=$(echo "$SUMMARY" | tr '[:upper:]' '[:lower:]' | \
     sed 's/[^a-z0-9 ]//g' | awk '{for(i=1;i<=3&&i<=NF;i++) printf "%s-",$i}' | sed 's/-$//')
   TICKET_LOWER=$(echo "$TICKET" | tr '[:upper:]' '[:lower:]')
   BRANCH_NAME="${TICKET_LOWER}_${SHORT_DESC}"
   ```

4. Create and checkout:
   ```bash
   git checkout -b "$BRANCH_NAME" "$REMOTE/$DEFAULT_BRANCH"
   ```

Skip all branch creation when `--draft` is set.

#### Removed: `--integrate` flag and Stage 6

- Remove `--integrate` from argument parsing
- Remove `INTEGRATE` variable and all references
- Remove Stage 6 (integrate) entirely — phase dispatch, confirmation gate, all of it
- Remove `integrate` from stage sequence in Step 4 and Step 5

#### Added: `--draft` flag

- Parse `--draft` flag in argument parsing
- Store as `options.draft` in state file (boolean, default `false`)
- When `--draft` is true, skip branch creation and tell writer to use staging area

#### State file schema

```json
{
  "options": {
    "pr_urls": [],
    "format": "adoc",
    "draft": false,
    "create_jira_project": null
  },
  "stages": {
    "requirements": { ... },
    "planning": { ... },
    "writing": { ... },
    "technical_review": { ... },
    "review": { ... },
    "create_jira": { ... }
  }
}
```

Removed: `integrate` option and stage.
Added: `draft` option.

#### Stage sequence

```
requirements → planning → writing → technical_review → review → create_jira (optional)
```

#### Writer prompt changes

The orchestrator must tell the writer which mode to use:

**Default mode prompt addition:**
> Place files directly in the repository following existing conventions. Detect the build framework, analyze file naming and directory conventions, and write modules to the correct repo locations. Update navigation/TOC files as needed.

**Draft mode prompt addition:**
> Save files to the `.agent_workspace/drafts/<jira-id>/` staging area. Do not modify any existing repository files.

#### Review stage prompt changes

Stages 4 and 5 must reference files at their actual locations:

**Default mode:** Pass the `_index.md` manifest path so reviewers can find all written files.

**Draft mode:** Same as current behavior — hardcoded `.agent_workspace/drafts/<ticket>/` paths.

#### Usage examples update

Remove all `--integrate` examples. Add `--draft` examples:

```bash
# Default: clean branch, docs written directly in repo
/docs-workflow start RHAISTRAT-123

# Draft mode: staging area, no branch
/docs-workflow start RHAISTRAT-123 --draft

# With PR and JIRA creation
/docs-workflow start RHAISTRAT-123 --pr https://github.com/org/repo/pull/456 --create-jira INFERENG
```

### `plugins/docs-tools/agents/docs-writer.md`

#### New section: Build framework detection and repo placement

Added before the writing guidelines, active only in default (non-draft) mode:

1. **Detect the build framework** — scan for `antora.yml`, `mkdocs.yml`, `conf.py`, `docusaurus.config.js`, `_config.yml`, `_topic_map.yml`, Makefiles with docs targets
2. **Analyze repo conventions** — file naming (kebab-case, prefixed/unprefixed), directory layout, include patterns, nav/TOC structure, AsciiDoc attributes
3. **Determine target paths** — map each planned module to its correct location
4. **Write files directly** to detected locations
5. **Update nav/TOC** — add entries following existing patterns

#### Output location changes

- **Default mode:** Files written directly to repo locations. The `_index.md` manifest is still created at `.agent_workspace/drafts/<jira-id>/` as a record of what was written and where.
- **Draft mode (`--draft`):** Files written to `.agent_workspace/drafts/<jira-id>/` (current behavior, unchanged).

#### Removed

- Symlink setup for `_attributes/` etc. (unnecessary when writing directly in repo)
- All language implying `.agent_workspace/drafts/` is the *default* output

### `plugins/docs-tools/agents/docs-integrator.md`

**Deleted.** All logic absorbed into docs-writer.

### Registry files

- `plugins/docs-tools/.claude-plugin/plugin.json` — remove docs-integrator from agents list if present
- `.claude-plugin/marketplace.json` — remove docs-integrator reference if present

## End-to-end flows

### Default mode

```
1. Parse args, validate JIRA token
2. Fetch JIRA summary → "Add autoscaling support"
3. Auto-detect remote/default branch (origin/main)
4. git checkout -b rhaistrat-123_add-autoscaling-support origin/main
5. Requirements analyst → .agent_workspace/requirements/
6. Docs planner → .agent_workspace/plans/
7. Docs writer:
   - Detects build framework (e.g., Antora)
   - Analyzes repo conventions
   - Writes modules to repo (e.g., docs/modules/ROOT/pages/)
   - Updates nav.adoc
   - Creates _index.md manifest
8. Technical reviewer → reviews files at repo locations
9. Style reviewer → edits files in place
10. (Optional) Create JIRA ticket
```

### Draft mode

```
1. Parse args, validate JIRA token
2. NO branch creation
3. Requirements analyst → .agent_workspace/requirements/
4. Docs planner → .agent_workspace/plans/
5. Docs writer → .agent_workspace/drafts/<ticket>/
6. Technical reviewer → reviews drafts
7. Style reviewer → edits drafts in place
8. (Optional) Create JIRA ticket
```

## Migration

Users who previously used `--integrate` get that behavior by default now.
Users who previously ran without `--integrate` should use `--draft`.
