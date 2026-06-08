---
name: docs-workflow-tech-review
description: Technical accuracy review of documentation drafts with optional code-learner validation. When code analysis is available, validates documentation claims against learn-code analysis data before dispatching the technical-reviewer agent. Iteration logic is owned by the orchestrator, not this skill.
argument-hint: <ticket> --base-path <path> [--repo <path>]...
allowed-tools: Read, Write, Glob, Grep, Edit, Bash, Skill, Agent, WebSearch, WebFetch
---

# Technical Review Step

Step skill for the docs-orchestrator pipeline. Follows the step skill contract: **parse args → [run claim validation] → dispatch agent → write output**.

When code-learner analysis is available (from the `code-analysis` step), this step validates documentation claims against the analysis data by dispatching `code-questioner` agents. These validation results are passed to the `technical-reviewer` agent as pre-computed evidence, giving the reviewer concrete verdicts alongside its engineering judgment.

This skill performs a single review pass. The iteration loop (re-running with fixes between passes) is driven by the orchestrator skill, not this step skill.

## Arguments

- `$1` — JIRA ticket ID (required)
- `--base-path <path>` — Base output path (e.g., `.agent_workspace/proj-123`)
- `--repo <path>...` — Path to the source code repository (optional, repeatable, provided by orchestrator when available). The first `--repo` is the primary source repo. Additional `--repo` values are secondary repos with code-learner analysis at `<base-path>/code-analysis-<repo-name>/`

## Input

```
<base-path>/writing/
<repo-path>/ (optional — source code repo for code-grounded validation)
```

## Output

```
<base-path>/technical-review/review.md
<base-path>/technical-review/step-result.json
<base-path>/technical-review/claim-validation.json (when code-analysis available)
```

## Execution

### 1. Parse arguments

Extract the ticket ID, `--base-path`, and optional `--repo` value(s) from the args string.

Collect all `--repo` values. The first becomes the primary `REPO_PATH`. Additional values are stored in an `ADDITIONAL_REPO_PATHS` list.

Set the paths:

```bash
OUTPUT_DIR="${BASE_PATH}/technical-review"
OUTPUT_FILE="${OUTPUT_DIR}/review.md"
CLAIMS_FILE="${OUTPUT_DIR}/claim-validation.json"
CODE_ANALYSIS_DIR="${BASE_PATH}/code-analysis"
mkdir -p "$OUTPUT_DIR"
```

Set `HAS_REPO=true` if at least one valid `--repo` path was provided and exists as a directory. Otherwise `HAS_REPO=false`.

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

### 3. Claim validation pre-scan (conditional)

**Skip this step entirely if no code-analysis data exists** (check `${CODE_ANALYSIS_DIR}/ONBOARDING.md`). Proceed directly to step 4.

When code-learner analysis is available from the code-analysis step, validate documentation claims against the analysis data before dispatching the reviewer agent.

#### Reuse check (iterations 2+)

Before running validation, check if `claim-validation.json` and `validation-summary.md` both exist in `$OUTPUT_DIR` (from a prior iteration). If both files exist and are non-empty:

- Set `HAS_CLAIMS=true`
- Skip steps 3a–3d entirely — reuse the existing files
- Log: `"Reusing claim validation from prior iteration"`

If only `claim-validation.json` exists but `validation-summary.md` is missing (possible from a partial prior run), skip steps 3a-3c and re-run step 3d only to generate the summary.

This is safe because iterations only change the documentation (via the fix cycle), not the source code analysis. The validation from iteration 1 remains valid.

#### 3a. Extract claims from draft documentation

Delegate claim extraction to a subagent so that full draft file content (~50-100KB) stays out of the orchestrator's context.

```
Agent:
  description: "Extract technical claims from docs for <TICKET>"
  prompt: |
    Extract verifiable technical claims from documentation draft files.

    <SOURCE_FILES_BLOCK>

    Read all .adoc and .md files from the source location above.
    For each file, extract factual claims that can be verified against code:
    - Function names, method signatures, parameter lists
    - Behavior descriptions ("X happens when Y")
    - Configuration options, environment variables, default values
    - API endpoints, resource types, CRD kinds
    - Class names, return types, data structures
    - Command-line flags, subcommands, option values

    Focus on claims that can be verified against source code.

    Write the claims list to: <OUTPUT_DIR>/claims-list.json

    Format:
    [
      {"id": "claim-1", "text": "The CreateCluster function accepts a ClusterConfig parameter", "file": "proc-creating-cluster.adoc", "line": 42},
      {"id": "claim-2", "text": "Authentication uses JWT tokens stored in the session cookie", "file": "con-auth-overview.adoc", "line": 15}
    ]

    After writing, print ONLY: Written <OUTPUT_DIR>/claims-list.json
```

After the agent completes, extract the claim count and IDs from disk without reading the full file into context:

```bash
python3 -c "
import json
claims = json.load(open('<OUTPUT_DIR>/claims-list.json'))
print(json.dumps({
    'count': len(claims),
    'items': [{'id': c['id'], 'text': c['text'][:60]} for c in claims]
}))
"
```

This gives the orchestrator enough to dispatch code-questioner agents (claim IDs and truncated text for agent descriptions) without loading full claim details.

#### 3b. Dispatch code-questioner agents for validation

For each claim (from the step 3a compact output), dispatch a `code-questioner` agent. Launch ALL agents in a **single message** (parallel execution).

Each agent reads analysis data from disk and writes its verdict to a per-claim file. This keeps the orchestrator's context lean — agent prompts are compact (~0.3KB each) and agent results are one-line confirmations.

For each claim, use:

```
Agent:
  subagent_type: docs-tools:code-questioner
  description: "Verify claim-NNN: <text truncated to 40 chars>"
  prompt: |
    Verify a documentation claim against the source code.

    QUESTION: "Verify: <claim text>. Is this accurate according to the source code? Report the actual implementation details."

    Read the learn-code analysis data from: <CODE_ANALYSIS_DIR>/
    Files available:
    - detection.json
    - registry.json
    - ONBOARDING.md
    - summaries/ (per-module analysis)
    - relationships/ (cross-module coupling)

    REPO_PATH: <repo_path>

    OUTPUT_FILE: <OUTPUT_DIR>/verdict-<NNN>.json

    IMPORTANT: Write a JSON verdict to OUTPUT_FILE (not a markdown answer):
    {
      "claim_id": "<claim-id>",
      "claim_text": "<claim text>",
      "verdict": "supported|partially_supported|unsupported|no_evidence_found",
      "evidence": "<brief excerpt of what you found — 1-2 sentences>"
    }

    After writing, print ONLY: Written <OUTPUT_DIR>/verdict-<NNN>.json
```

Where `<NNN>` is the zero-padded claim number (e.g., claim-1 produces verdict-001.json).

**Important:** All Agent calls MUST be in a single message so they run in parallel.

#### 3c. Collect verdicts from disk

After all code-questioner agents complete, verify which verdict files were written:

```bash
ls <OUTPUT_DIR>/verdict-*.json 2>/dev/null | wc -l
```

Log: `"<found_count>/<total_count> verdict files written to disk"`

For any missing verdict files (agent failed or was skipped), the merge agent in step 3d will create a fallback entry with verdict `no_evidence_found`.

#### 3d. Assemble claim-validation.json and validation summary via merge agent

Delegate the assembly of the claim validation output to a merge subagent. This keeps the full validation data out of the orchestrator's context.

```
Agent:
  description: "Merge claim verdicts for <TICKET>"
  prompt: |
    Assemble claim-validation.json and validation-summary.md from per-claim verdict files.

    CLAIMS_LIST_FILE: <OUTPUT_DIR>/claims-list.json
    OUTPUT_DIR: <OUTPUT_DIR>
    CLAIMS_FILE: <OUTPUT_DIR>/claim-validation.json
    SUMMARY_FILE: <OUTPUT_DIR>/validation-summary.md
    CODE_ANALYSIS_DIR: <CODE_ANALYSIS_DIR>

    Instructions:
    1. Read CLAIMS_LIST_FILE for the full claims list (id, text, file, line)
    2. For each claim, read <OUTPUT_DIR>/verdict-<NNN>.json
       - If a verdict file is missing, create a fallback:
         {"claim_id": "<id>", "claim_text": "<text>",
          "verdict": "no_evidence_found",
          "evidence": "Agent did not return a verdict"}
    3. Assemble CLAIMS_FILE:
       {
         "claims": [
           {"id": "<claim-id>", "text": "...", "verdict": "supported|...",
            "evidence": "...", "file": "...", "line": N}
         ],
         "summary": {
           "supported": N,
           "partially_supported": N,
           "unsupported": N,
           "no_evidence_found": N
         }
       }
    4. Read <CODE_ANALYSIS_DIR>/registry.json for module coverage context
    5. Write SUMMARY_FILE as markdown containing:
       - Count of claims by verdict
       - List of unsupported and partially_supported claims with their evidence
       - Module coverage summary from registry.json
    6. After writing both files, print ONLY:
       Written <CLAIMS_FILE>
       Written <SUMMARY_FILE>
```

Set `HAS_CLAIMS=true`.

### 4. Dispatch agent

**You MUST use the Agent tool** to invoke the `technical-reviewer` subagent. Do NOT read the agent's markdown file or attempt to perform the agent's work yourself — the agent has a specialized system prompt and must run as an isolated subagent.

**Agent tool parameters:**
- `subagent_type`: `docs-tools:technical-reviewer`
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

**[Include only if ADDITIONAL_REPO_PATHS is non-empty]** Append:

> Additional source code repositories are available for cross-verification:
> <for each path in ADDITIONAL_REPO_PATHS, output: "- `<path>`">
>
> Additional code-learner analyses (if available):
> <for each additional repo, if `<BASE_PATH>/code-analysis-<repo-name>/ONBOARDING.md` exists, output: "- `<BASE_PATH>/code-analysis-<repo-name>/`">
>
> Use these to verify claims that reference features outside the primary repository.

**[Include only if HAS_CLAIMS=true]** Append:

> ## Claim Validation Evidence
>
> Documentation claims have been validated against code-learner analysis of the source repository.
>
> Read the validation summary from: `<OUTPUT_DIR>/validation-summary.md`
> Full claim-by-claim results are at: `<CLAIMS_FILE>`
>
> **How to use this evidence:**
> - Claims with verdict `unsupported` are likely inaccurate — verify the evidence and flag as critical or significant issues
> - Claims with verdict `no_evidence_found` may reference features outside the analyzed modules — flag as SME verification needed
> - Claims with verdict `partially_supported` need targeted review — identify what part is wrong
> - Claims with verdict `supported` have analysis backing — still apply your engineering judgment but these are lower risk

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

The `code_grounded` field records whether code-learner analysis was available for claim validation — either from running the validation (`HAS_CLAIMS`) or from reusing prior iteration files. Set to `true` if the reviewer agent received claim validation evidence in its prompt, regardless of whether the validation ran in this invocation or a prior one.
