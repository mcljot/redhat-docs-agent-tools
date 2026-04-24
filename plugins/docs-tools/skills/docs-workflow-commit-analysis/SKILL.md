---
name: docs-workflow-commit-analysis
description: >-
  Analyze documentation impact of a commit, PR/MR, or branch diff.
  Produces requirements.md for the planning step. Invoked by the
  orchestrator as the first step in the commit-driven workflow.
argument-hint: "<ticket> --base-path <path> --commit <url> [--repo <path>] [--base-branch <branch>]"
allowed-tools: Read, Write, Bash, Grep, Glob, Skill, AskUserQuestion
---

# Commit Analysis Step

Step skill for the docs-orchestrator pipeline. Follows the step skill contract: **parse args → invoke skill → verify output → write sidecar**.

## Arguments

- `$1` — Identifier (ticket ID or auto-derived from commit URL)
- `--base-path <path>` — Base output path (e.g., `.claude/docs/repo-pr-42`)
- `--commit <url>` — Commit, PR, or MR URL (required)
- `--repo <path>` — Path to local source repository (optional)
- `--base-branch <branch>` — Base branch for comparison (optional)
- `--ticket <JIRA-ID>` — JIRA ticket for enrichment (optional, passed if $1 matches JIRA pattern)

## Output

```
<base-path>/requirements/requirements.md
```

Writes to the same location as the standard requirements step so the planning step reads from the same path regardless of workflow.

## Execution

### 1. Parse arguments

Extract `$1`, `--base-path`, `--commit`, `--repo`, `--base-branch`, and `--ticket` from the args string.

Set the output path:

```bash
OUTPUT_DIR="${BASE_PATH}/requirements"
OUTPUT_FILE="${OUTPUT_DIR}/requirements.md"
mkdir -p "$OUTPUT_DIR"
```

### 2. Invoke commit-analyst skill

Build the skill invocation args:

```
--commit <COMMIT_URL> --base-path <BASE_PATH>
```

Add optional flags:
- If `--ticket` was provided OR if `$1` matches JIRA pattern `[A-Z]+-[0-9]+`: add `--ticket <value>`
- If `--repo` was provided: add `--repo <path>`
- If `--base-branch` was provided: add `--base-branch <branch>`

Invoke the skill:

```
Skill: docs-tools:commit-analyst, args: "<constructed args>"
```

### 3. Check impact grade

After the skill completes, read `OUTPUT_FILE`. Find the line containing "Overall documentation impact" and extract the grade (HIGH, MEDIUM, LOW, or NONE).

If the grade is **NONE**:

Use AskUserQuestion to prompt the user:

> No documentation impact detected for this change. Continue the pipeline anyway?

Options:
- **No — stop here (Recommended)**: Exit. Do not delete `OUTPUT_FILE` (the NONE report is still useful as a record). The orchestrator sees the step as complete but the planning step will find minimal requirements.
- **Yes — continue anyway**: Proceed normally. The planning step will work with whatever minimal requirements exist.

### 4. Verify output

Confirm `OUTPUT_FILE` exists and is non-empty.

If missing, report an error: "Commit analysis failed — no output file at `<OUTPUT_FILE>`."

### 5. Write step-result.json

Run the title-extraction script (reused from the requirements step):

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/docs-workflow-requirements/scripts/parse_title.py "<OUTPUT_FILE>"
```

The script prints `{"title": "..."}` to stdout. If it exits non-zero, report the stderr message as an error.

Extract the impact grade from the output file (the "Overall documentation impact" line).

Count files analyzed from the Summary section.

Extract documentation impact categories from the Summary section's "Impact categories" line (e.g., `new_feature, api_change`). Split on commas and trim whitespace.

Write the sidecar to `${OUTPUT_DIR}/step-result.json`:

```json
{
  "schema_version": 1,
  "step": "commit-analysis",
  "ticket": "<IDENTIFIER>",
  "completed_at": "<current ISO 8601 timestamp>",
  "title": "<first heading from parse_title.py, max 80 chars>",
  "impact_grade": "HIGH|MEDIUM|LOW|NONE",
  "files_analyzed": 15,
  "doc_impact_categories": ["new_feature", "api_change"]
}
```
