# ACP JIRA Label Conventions

The ACP pipeline uses JIRA labels to track documentation workflow state. These labels are managed by `jira_writer.py` via `--labels-add` and `--labels-remove`.

## Workflow labels

| Label | Meaning | Set by |
|-------|---------|--------|
| `ambient-docs-ready` | Ticket is queued for documentation generation | Human / triage |
| `ambient-docs-processing` | Pipeline has claimed this ticket for the current session | `batch-find-tickets.sh` |
| `ambient-docs-generated` | Documentation was successfully generated and pushed | Pipeline on success |
| `ambient-docs-failed` | Pipeline attempted but failed to generate documentation | Pipeline on failure |

## Label lifecycle

```
ambient-docs-ready  →  ambient-docs-processing  →  ambient-docs-generated
                                                 →  ambient-docs-failed
```

1. A human or triage process adds `ambient-docs-ready` to a JIRA ticket
2. `batch-find-tickets.sh` finds the ticket, swaps `ambient-docs-ready` for `ambient-docs-processing`
3. On success, the pipeline removes `ambient-docs-processing` and adds `ambient-docs-generated`
4. On failure, the pipeline removes `ambient-docs-processing` and adds `ambient-docs-failed`

## jira-writer examples

**Claim a ticket (swap ready → processing):**
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/jira-writer/scripts/jira_writer.py \
  --issue PROJ-123 \
  --labels-remove ambient-docs-ready \
  --labels-add ambient-docs-processing
```

**Mark success:**
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/jira-writer/scripts/jira_writer.py \
  --issue PROJ-123 \
  --labels-remove ambient-docs-processing \
  --labels-add ambient-docs-generated
```

**Mark failure:**
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/jira-writer/scripts/jira_writer.py \
  --issue PROJ-123 \
  --labels-remove ambient-docs-processing \
  --labels-add ambient-docs-failed
```

## Configuration

Label names are configurable via environment variables (see `adapters/ambient/CLAUDE.md`):

| Variable | Default |
|----------|---------|
| `DOCS_TRIGGER_LABEL` | `ambient-docs-ready` |
| `DOCS_PROCESSING_LABEL` | `ambient-docs-processing` |
| `DOCS_DONE_LABEL` | `ambient-docs-generated` |
| `DOCS_FAILED_LABEL` | `ambient-docs-failed` |
