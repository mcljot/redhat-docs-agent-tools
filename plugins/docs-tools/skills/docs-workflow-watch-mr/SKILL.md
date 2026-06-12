---
name: docs-workflow-watch-mr
description: "[DEFERRED — v2] Poll an MR/PR for new SME review comments and trigger resolve-feedback when found. Designed for /loop usage. Checks for new unresolved comments since the last check, invokes resolve-feedback and quality-gate if new comments are found. Stops the loop when quality-gate passes and no new comments remain."
argument-hint: <ticket> [--base-path <path>]
allowed-tools: Read, Write, Bash, Glob, Grep, Skill
---

# Watch MR (Deferred — v2)

> **Status**: This skill is scaffolded but not yet active. The script and SKILL.md are
> ready for when SME comment polling is needed. For v1, resolve SME comments manually
> by re-running resolve-feedback after reviewing the MR.

Standalone polling skill for post-MR SME review resolution. **Not** part of the workflow YAML — invoked manually via `/loop`.

After the pipeline creates an MR, SMEs review it and leave comments. This skill polls the MR at regular intervals, detects new comments, and triggers the resolve-feedback → quality-gate loop to address them automatically.

## Usage

```
/loop 6h /docs-tools:docs-workflow-watch-mr RHAIENG-2620
```

This checks the MR every 6 hours. For testing, use a shorter interval:

```
/loop 60s /docs-tools:docs-workflow-watch-mr RHAIENG-2620
```

## Arguments

- `$1` — Ticket ID (required)
- `--base-path <path>` — Base output path (optional, defaults to `.agent_workspace/<ticket-lowercase>`)

## Execution

### 1. Parse arguments and resolve paths

Extract `TICKET` from `$1`. If `--base-path` is not provided, derive it: `.agent_workspace/<ticket-lowercase>`.

### 2. Check for MR

Read `${BASE_PATH}/create-merge-request/step-result.json` to find the MR URL.

If no MR exists (file missing, or `skipped: true`), report:
> "No MR found for <TICKET>. Create one first with the pipeline, then re-run this watch."

Exit without scheduling a next check (loop ends).

### 3. Check for new comments

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/watch_mr.py \
  --base-path "${BASE_PATH}"
```

The script:
1. Reads the MR URL from `create-merge-request/step-result.json`
2. Fetches comments via `git_pr_reader.py comments <url> --json`
3. Filters to unresolved comments created after the last check timestamp
4. Writes `watch-mr/last-checked.json` with the current timestamp and seen comment IDs
5. Outputs JSON: `{"new_comments": [...], "count": N, "action_needed": bool}`

### 4. Handle results

Parse the script's JSON output:

**If `action_needed` is true (new comments found):**

Report:
> "Found <count> new SME comment(s) on MR. Resolving..."

Then invoke resolve-feedback and re-run quality-gate:

```
Skill: docs-tools:docs-workflow-resolve-feedback, args: "<TICKET> --base-path <BASE_PATH>"
```

After resolve-feedback completes:

```
Skill: docs-tools:docs-workflow-quality-gate, args: "<TICKET> --base-path <BASE_PATH>"
```

Read the updated `quality-gate/step-result.json` and report the new scores.

If the writing fix produced changes, push them to the MR branch:
1. Read the MR branch from `create-merge-request/step-result.json` → `branch`
2. Stage and commit the modified files with message: `"fix: resolve SME review comments for <TICKET>"`
3. Push to the remote branch

**If `action_needed` is false (no new comments):**

Read `quality-gate/step-result.json` (if it exists) to check the current gate status.

- If `passed` is true: report "All clear — quality gate passed, no new SME comments." Exit without scheduling a next check (loop ends).
- If `passed` is false or quality-gate hasn't run: report "No new comments. Quality gate status: <status>. Will check again at next interval."
- If quality-gate doesn't exist yet: report "No new comments. Waiting for SME review."

### 5. Error handling

If `git_pr_reader.py` fails (e.g., auth error, network issue), report the error and continue to the next interval rather than stopping the loop.

If the Anthropic API fails during quality-gate, report the error and continue.

## State

The skill maintains polling state in `${BASE_PATH}/watch-mr/last-checked.json`:

```json
{
  "last_checked": "2026-06-11T18:00:00+00:00",
  "comments_seen": [12345, 67890]
}
```

This prevents re-processing comments that were already handled in a previous iteration.

## Exit conditions

The loop ends (no next wakeup) when:
- No MR exists for the ticket
- Quality gate has passed AND no new comments in the latest check
- The MR is merged or closed (not yet implemented — deferred to v2)
