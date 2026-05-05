# Batch Controller Reference

## repo-info.json schema

Written by `repo-setup.sh` to `artifacts/<ticket>/repo-info.json`:

| Field | Type | Description |
|-------|------|-------------|
| `ticket` | string | Original ticket key (e.g., `VROOM-123`) |
| `jira_project` | string | Extracted project key (e.g., `VROOM`) |
| `repo_url` | string\|null | Target repo URL, or null if no mapping / clone failed |
| `clone_path` | string | Absolute path to local clone (under `.work/`) |
| `branch` | string | Feature branch name (lowercase ticket key) |
| `platform` | string | `github`, `gitlab`, or `unknown` |
| `default_branch` | string | Target branch for MR/PR (usually `main`) |
| `format` | string | `mkdocs` or `adoc` |

## step-result.json schema

Written by the `docs-workflow-create-merge-request` step to `artifacts/<ticket>/create-merge-request/step-result.json`:

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | number | Always `1` |
| `step` | string | Always `"create-merge-request"` |
| `ticket` | string | Ticket key (uppercase) |
| `completed_at` | string | ISO 8601 timestamp |
| `commit_sha` | string\|null | Commit SHA if committed, null if skipped |
| `branch` | string\|null | Feature branch name |
| `pushed` | boolean | Whether the branch was pushed to remote |
| `url` | string\|null | MR/PR URL, or null if skipped |
| `action` | string | `created`, `found_existing`, or `skipped` |
| `platform` | string | `github`, `gitlab`, or `unknown` |
| `skipped` | boolean | Whether the step was skipped |
| `skip_reason` | string\|null | Reason for skip (e.g., `draft`, `no_files`, `no_changes`) |

Commit, push, and MR/PR creation are handled by a single orchestrator workflow step, not by adapter scripts.

## Configuration

| Variable | Purpose | Default |
|----------|---------|---------|
| `DOCS_TRIGGER_LABEL` | Label marking tickets for processing | `ambient-docs-ready` |
| `DOCS_PROCESSING_LABEL` | Label added when ticket is claimed | `ambient-docs-processing` |
| `DOCS_DONE_LABEL` | Label added after success | `ambient-docs-generated` |
| `DOCS_FAILED_LABEL` | Label added after failure | `ambient-docs-failed` |
| `DOCS_JIRA_PROJECT` | Limit to specific JIRA project | — |

## Batch summary format

Write to `artifacts/batch-summary.md`:

```markdown
# Batch Summary

**Date**: YYYY-MM-DD HH:MM UTC
**Tickets processed**: N
**Successful**: X
**Failed**: Y

## Results

| Ticket | Status | Output Path | MR/PR | Notes |
|--------|--------|-------------|-------|-------|
| PROJ-123 | success | artifacts/proj-123/ | <url> | 5 modules written |
| PROJ-456 | failed | — | — | Error: ... |

## Errors

### PROJ-456

<error details>
```
