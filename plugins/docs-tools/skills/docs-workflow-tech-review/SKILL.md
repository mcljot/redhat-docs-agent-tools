---
name: docs-workflow-tech-review
description: Technical accuracy review of documentation drafts with optional code-grounded validation. When a source repo is available, runs grounded_review and api_surface against the code to validate documentation claims before dispatching the technical-reviewer agent. Iteration logic is owned by the orchestrator, not this skill.
argument-hint: <ticket> --base-path <path> [--repo <path>]
allowed-tools: Read, Write, Glob, Grep, Edit, Bash, Skill, Agent, WebSearch, WebFetch
---

# Technical Review Step

Step skill for the docs-orchestrator pipeline. Follows the step skill contract: **parse args → [run code-grounded pre-scan] → dispatch agent → write output**.

When a source code repository is available (`--repo`), this step runs the same code-grounded validation pipeline used by `docs-review-technical` (Agent 2): `grounded_review.py` validates documentation claims against source code, and `api_surface.py` extracts the public API surface. These results are passed to the `technical-reviewer` agent as pre-computed evidence, giving the reviewer concrete code verdicts alongside its engineering judgment.

This skill performs a single review pass. The iteration loop (re-running with fixes between passes) is driven by the orchestrator skill, not this step skill.

## Arguments

- `$1` — JIRA ticket ID (required)
- `--base-path <path>` — Base output path (e.g., `.agent_workspace/proj-123`)
- `--repo <path>` — Path to the source code repository (optional, provided by orchestrator when available)

## Input

```
<base-path>/writing/
<repo-path>/ (optional — source code repo for code-grounded validation)
```

## Output

```
<base-path>/technical-review/review.md
<base-path>/technical-review/step-result.json
<base-path>/technical-review/grounded-review.json (when --repo provided)
<base-path>/technical-review/api-surface.json (when --repo provided)
```

## Execution

### 1. Parse arguments

Extract the ticket ID, `--base-path`, and optional `--repo` from the args string.

Set the paths:

```bash
OUTPUT_DIR="${BASE_PATH}/technical-review"
OUTPUT_FILE="${OUTPUT_DIR}/review.md"
GROUNDED_FILE="${OUTPUT_DIR}/grounded-review.json"
API_SURFACE_FILE="${OUTPUT_DIR}/api-surface.json"
mkdir -p "$OUTPUT_DIR"
```

Set `HAS_REPO=true` if `--repo` was provided and the path exists as a directory. Otherwise `HAS_REPO=false`.

### 2. Determine source files

Read the writing step's sidecar at `${BASE_PATH}/writing/step-result.json` to determine the writing mode and file list.

**If the sidecar exists and `mode` is `"update-in-place"` with a non-empty `files` array:**

Build a `<SOURCE_FILES_BLOCK>` listing the files explicitly:

```
Source files — review each of these:
- `/absolute/path/to/file1.adoc`
- `/absolute/path/to/file2.adoc`
```

**Otherwise** (draft mode, missing sidecar, or empty files array):

Set `DRAFTS_DIR="${BASE_PATH}/writing"` and build the block as:

```
Source drafts location: `<DRAFTS_DIR>/`
```

### 3. Code-grounded pre-scan (conditional)

**Skip this step entirely if `HAS_REPO=false`.** Proceed directly to step 3.

When a source repo is available, run the code-grounded validation pipeline before dispatching the reviewer agent. This produces structured evidence the agent uses alongside its own analysis.

#### 2a. Collect draft file paths

Read the writing manifest at `<DRAFTS_DIR>/_index.md`. Extract the absolute file paths from the table rows. If the manifest doesn't exist, fall back to globbing `<DRAFTS_DIR>/` for `.adoc` and `.md` files recursively.

Build a JSON drafts file for batch mode:

```bash
# Build drafts batch file from the collected paths
cat > "${OUTPUT_DIR}/drafts-batch.json" << 'EOF'
[
  {"draft": "/path/to/file1.adoc"},
  {"draft": "/path/to/file2.adoc"}
]
EOF
```

#### 2b. Run grounded review

Check if code-finder is installed:

```bash
python3 -c "import claude_context" 2>/dev/null && echo "INSTALLED" || echo "NOT_INSTALLED"
```

If **INSTALLED**, run directly:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/code-evidence/scripts/grounded_review.py \
  --repo "$REPO_PATH" \
  --drafts-file "${OUTPUT_DIR}/drafts-batch.json" \
  --reindex > "$GROUNDED_FILE"
```

If **NOT_INSTALLED**, prefix with uv:

```bash
uv run --with code-finder python3 ${CLAUDE_PLUGIN_ROOT}/skills/code-evidence/scripts/grounded_review.py \
  --repo "$REPO_PATH" \
  --drafts-file "${OUTPUT_DIR}/drafts-batch.json" \
  --reindex > "$GROUNDED_FILE"
```

If the command fails (non-zero exit), log a warning and continue without grounded review — set `HAS_GROUNDED=false`. Otherwise `HAS_GROUNDED=true`.

#### 2c. Run API surface extraction

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/code-evidence/scripts/api_surface.py \
  --target "$REPO_PATH" > "$API_SURFACE_FILE"
```

Or with uv fallback if code-finder is not installed.

If the command fails, log a warning and continue without API surface — set `HAS_API_SURFACE=false`. Otherwise `HAS_API_SURFACE=true`.

#### 2d. Summarize code-grounded findings

Read `$GROUNDED_FILE` and triage the results. For each claim verdict:

- `unsupported` — flag as likely inaccurate. Note the evidence that contradicts the claim.
- `no_evidence_found` — note as unverifiable. The claim may reference something outside the repo scope.
- `partially_supported` — note what part is supported and what isn't.
- `supported` — no action needed.

Read `$API_SURFACE_FILE` and note the total entity count and key classes/functions. This gives the reviewer a map of what exists in the code.

Build a `CODE_EVIDENCE_SUMMARY` text block containing:
- Count of claims by verdict (supported, partially_supported, unsupported, no_evidence_found)
- List of unsupported and partially_supported claims with their evidence
- Top-level API surface summary (number of classes, functions, methods)
- List of any doc-referenced APIs not found in the API surface

### 4. Dispatch agent

**You MUST use the Agent tool** to invoke the `technical-reviewer` subagent. Do NOT read the agent's markdown file or attempt to perform the agent's work yourself — the agent has a specialized system prompt and must run as an isolated subagent.

**Agent tool parameters:**
- `subagent_type`: `technical-reviewer`
- `description`: `Technical review of documentation for <TICKET>`

**Prompt** (pass this as the `prompt` parameter to the Agent tool):

> Perform a technical review of the documentation drafts for ticket `<TICKET>`.
> <SOURCE_FILES_BLOCK>
> Review all .adoc and .md files. Follow your standard review methodology.
> Save your review report to: `<OUTPUT_FILE>`
>
> The report must include an `Overall technical confidence: HIGH|MEDIUM|LOW` line.

**[Include only if HAS_REPO=true]** Append:

> Source code repository is available at `<REPO_PATH>`. You may read specific source files to verify technical claims in the documentation.

**[Include only if HAS_GROUNDED=true]** Append:

> ## Code-Grounded Review Evidence
>
> A code-grounded review has been run against the documentation drafts using the source repository. The review extracted claims from the documentation and validated each one against the source code.
>
> Full results: `<GROUNDED_FILE>`
>
> Summary of findings:
> <CODE_EVIDENCE_SUMMARY>
>
> **How to use this evidence:**
> - Claims with verdict `unsupported` are likely inaccurate — verify the evidence and flag as critical or significant issues
> - Claims with verdict `no_evidence_found` may reference features outside the repo scope — flag as SME verification needed unless you can confirm from other sources
> - Claims with verdict `partially_supported` need targeted review — identify what part is wrong
> - Claims with verdict `supported` have code backing — still apply your engineering judgment but these are lower risk

**[Include only if HAS_API_SURFACE=true]** Append:

> Cross-reference the API surface at `<API_SURFACE_FILE>` to check that documented class names, function signatures, and parameters match the actual code.

### 5. Verify output

After the agent completes, verify the review report exists at `<OUTPUT_FILE>`.

The review report **must** include an `Overall technical confidence: HIGH|MEDIUM|LOW` line. If this line is missing from the output, the orchestrator will treat it as a step failure.

The report should also include a `Severity counts: critical=N significant=N minor=N sme=N` line. This enables the orchestrator to skip unnecessary iteration when only SME-verification items remain.

### 6. Write step-result.json

Parse `<OUTPUT_FILE>` to extract the structured review metadata:

1. Find the `Overall technical confidence: HIGH|MEDIUM|LOW` line. Extract the confidence value
2. Find the `Severity counts: critical=N significant=N minor=N sme=N` line if present. Extract each count (default to `0` if the line is missing)

Write the sidecar to `${BASE_PATH}/technical-review/step-result.json`:

```json
{
  "schema_version": 1,
  "step": "technical-review",
  "ticket": "<TICKET>",
  "completed_at": "<current ISO 8601 timestamp>",
  "confidence": "<HIGH|MEDIUM|LOW>",
  "severity_counts": {
    "critical": "<N>",
    "significant": "<N>",
    "minor": "<N>",
    "sme": "<N>"
  },
  "iteration": 1,
  "code_grounded": <true|false>
}
```

The `iteration` field is `1` for the first review pass. If the orchestrator re-invokes this skill after a fix cycle, it passes the current iteration count — increment it for the sidecar.

The `code_grounded` field records whether the code-grounded pre-scan ran (`HAS_GROUNDED`). This is informational — downstream consumers can use it to assess review thoroughness.
