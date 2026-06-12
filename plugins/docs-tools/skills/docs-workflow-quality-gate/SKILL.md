---
name: docs-workflow-quality-gate
description: Score documentation quality and intent alignment using LLM judges (Sonnet 4-6). Runs two judge passes (doc_quality, intent_alignment) against writing output, extracts specific gaps from AC coverage analysis, and cross-references against scope-req-audit evidence. Produces pass/fail gate with actionable gap list. Iteration logic is owned by the orchestrator, not this skill.
argument-hint: <ticket> --base-path <path>
allowed-tools: Read, Write, Bash, Glob, Grep
---

# Quality Gate

Score the pipeline's documentation output before creating a merge request. This skill does **not** dispatch an agent — it runs a Python script that calls the Anthropic API directly with two judge prompts (doc_quality and intent_alignment) using Sonnet 4-6.

The quality gate produces a pass/fail verdict and, when intent alignment is below threshold, a structured list of gaps with recommended actions. The orchestrator uses these gaps to drive the resolve-feedback step.

## Arguments

- `$1` — Ticket ID (required, e.g., `RHAIENG-2620`)
- `--base-path <path>` — Base output path (required, e.g., `.agent_workspace/rhaieng-2620`)

## Inputs

Reads from upstream steps by convention:

| Source | Path | Required |
|--------|------|----------|
| Writing output | `<base-path>/writing/step-result.json` | Yes — files array lists AsciiDoc paths |
| Requirements context | `<base-path>/requirements/discovery.json` | Yes — ticket summary and AC items |
| Evidence status | `<base-path>/scope-req-audit/evidence-status.json` or `<base-path>/validate/evidence-status.json` | No — used to classify gaps by code evidence |

## Execution

### 1. Parse arguments

Extract `TICKET` from `$1` and `BASE_PATH` from `--base-path`.

### 2. Create output directory

```bash
mkdir -p "${BASE_PATH}/quality-gate"
```

### 3. Run the quality gate script

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/quality_gate.py \
  --ticket "${TICKET}" \
  --base-path "${BASE_PATH}"
```

The script:

1. Reads AsciiDoc files from `writing/step-result.json` → files array
2. Reads ticket context from `requirements/discovery.json` (summary + requirements with AC items)
3. Reads evidence status from `scope-req-audit/evidence-status.json` (optional)
4. Calls Sonnet 4-6 with the **doc_quality** prompt — scores on technical accuracy, completeness, modular structure, fabrication
5. Calls Sonnet 4-6 with the **intent_alignment** prompt — scores on scope match, AC coverage, audience alignment. Also extracts `missed_items` listing specific AC items not addressed
6. Cross-references missed items against evidence status to classify each gap:
   - `absent` → `document_as_unsupported` (add "not supported in this release" note)
   - `partial` → `expand_with_evidence` (expand with available code evidence)
   - `grounded` → `add_missing_section` (writing step missed it — re-include from plan)
   - `unknown` → `investigate` (evidence status unavailable)
7. Writes `quality-gate/step-result.json` and `quality-gate/judge-results.md`
8. Outputs the step-result JSON to stdout

### 4. Verify output

Read `${BASE_PATH}/quality-gate/step-result.json` and verify it contains:
- `doc_quality` (integer 1-5)
- `intent_alignment` (integer 1-5)
- `passed` (boolean)
- `gaps` (array)

If the file is missing or malformed, report the error.

### 5. Report results

Report the scores and pass/fail status:
- "Quality gate: doc_quality=N/5, intent_alignment=N/5, passed=true/false, gaps=N"
- If gaps exist, list each gap's `ac_item` and `action`

## Output

### step-result.json

```json
{
  "schema_version": 1,
  "step": "quality-gate",
  "ticket": "PROJ-123",
  "completed_at": "2026-06-11T16:00:00+00:00",
  "doc_quality": 5,
  "intent_alignment": 4,
  "passed": false,
  "iteration": 1,
  "gaps": [
    {
      "ac_item": "Document confidence scores",
      "judge": "intent_alignment",
      "evidence_status": "absent",
      "action": "document_as_unsupported"
    }
  ]
}
```

### judge-results.md

Human-readable summary with rationales from both judges and the gap list.

## Thresholds

- `intent_alignment >= 4` → `passed = true`
- `doc_quality` is reported but does **not** trigger resolve-feedback. If `doc_quality < 4`, the orchestrator logs a warning ("manual review recommended") but proceeds. Only intent_alignment gaps — specific missed AC items — are actionable via targeted rewrites
- The orchestrator decides what to do when `passed = false` (run resolve-feedback, or accept with warning after max iterations)

## Model

Uses `claude-sonnet-4-6` by default. Override via the `QUALITY_GATE_MODEL` environment variable.
