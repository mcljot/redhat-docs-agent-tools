---
name: commit-analyst
description: >-
  Analyzes a git commit, PR/MR, or branch diff to determine documentation
  impact. Produces structured requirements with acceptance criteria, grades
  impact, identifies affected documentation, and recommends next steps.
  Optionally enriches with JIRA context when a ticket is provided. Use when
  triaging code changes for documentation needs or driving a commit-based
  documentation workflow.
argument-hint: "--commit <url-or-sha> [--ticket <JIRA-ID>] [--repo <path>] [--base-branch <branch>]"
allowed-tools: Read, Write, Bash, Grep, Glob, Skill, WebSearch, WebFetch
---

# Commit Analyst

Analyze code changes (commits, PRs, MRs, branch diffs) for documentation impact. Produce structured requirements compatible with the docs-orchestrator pipeline.

## Parse arguments

Extract from `$ARGUMENTS`:

- `--commit <url-or-sha-or-branch>` — **required**. The code change to analyze. Accepts:
  - GitHub PR URL: `https://github.com/org/repo/pull/42`
  - GitLab MR URL: `https://gitlab.com/org/repo/-/merge_requests/5`
  - Commit SHA: `abc1234`
  - Branch name: `feature-branch`
- `--ticket <JIRA-ID>` — optional. JIRA ticket for context enrichment
- `--repo <path>` — optional. Path to local source repository (required for commit SHA and branch refs)
- `--base-branch <branch>` — optional. Base branch for comparison (default: main)
- `--base-path <path>` — optional. Output directory (pipeline mode)

If `--base-path` is provided, set output path:

```bash
OUTPUT_DIR="${BASE_PATH}/requirements"
OUTPUT_FILE="${OUTPUT_DIR}/requirements.md"
mkdir -p "$OUTPUT_DIR"
```

If `--base-path` is NOT provided (standalone mode), write to stdout summary only — do not create files.

## Step 1: Run gather_changes.py

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/gather_changes.py \
  --commit <ref> \
  [--repo <path>] \
  [--base-branch <branch>]
```

Capture the JSON output. If the script exits non-zero, report the stderr message and stop.

Read the JSON output and note:
- `ref_type` — how the ref was interpreted (pr, commit, branch)
- `pr_metadata` — title, description, labels, linked issues
- `summary` — files changed, lines added/removed
- `categories` — files grouped by type (source_code, documentation, tests, config, ci_cd, build)
- `signals` — new files, API changes, config changes, breaking indicators, docs already modified
- `key_diffs` — diff excerpts for high-signal files
- `code_context` — import/reference context for key files
- `docs_scan` — affected doc files and coverage gaps in the docs repo (cwd)

## Step 2: Load impact grading framework

Read [reference/impact-criteria.md](reference/impact-criteria.md).

## Step 3: Grade impact

Apply the grading criteria to the gathered data:

1. Map each signal to its minimum grade using the signal-to-grade table
2. Cross-reference `docs_scan.affected_files` — if existing docs reference changed code, grade is at least MEDIUM
3. Check `docs_scan.coverage_gaps` — new features without doc coverage push toward HIGH
4. Check `signals.breaking_indicators` — any breaking change is HIGH
5. The overall grade is the **highest individual grade** found

Identify documentation action categories from the impact-criteria reference (new feature, enhancement, breaking change, API change, config change, etc.).

## Step 4: If NONE — write brief report and stop

If the overall impact grade is NONE, write a brief explanation:

```markdown
# Documentation Requirements

**Source**: <ref URL or identifier>
**Date**: <YYYY-MM-DD>
**Overall documentation impact**: NONE

## Summary

No documentation impact detected. <Brief explanation — e.g., "Test-only changes with no user-facing impact" or "Internal refactoring — no behavior change.">.

Files analyzed: N (N source, N test, N config, N other)
```

If `--base-path` is set, write this to `OUTPUT_FILE`. Otherwise, print to the user.

**Stop here.** Do not proceed to JIRA enrichment or web search for NONE-grade changes.

## Step 5: JIRA enrichment (optional)

Run this step when:
- `--ticket` was explicitly provided, OR
- `pr_metadata.linked_issues` contains JIRA keys (e.g., `PROJ-456`) discovered from the PR description/commits

For each JIRA key:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/jira-reader/scripts/jira_reader.py --issue <TICKET>
```

For the primary ticket (from `--ticket`), also traverse the ticket graph:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/jira-reader/scripts/jira_reader.py --graph <TICKET>
```

Extract: ticket description, acceptance criteria, priority, status, related tickets.

**If JIRA access fails** (missing token, 403, timeout), log a warning and continue with diff-only analysis. JIRA is enrichment, not a hard dependency.

## Step 6: Web search expansion

Build 1-3 targeted search queries from:
- Features identified in the diff (e.g., "user preferences API <product-name>")
- Technologies introduced (e.g., "OAuth PKCE implementation guide")
- Breaking changes that need migration context (e.g., "<product> v2 API migration")

Use WebSearch for each query. Evaluate results for relevance to documentation. Save key findings (URL, title, relevance note) for the report. **Do not include raw search queries in the final output** — only curated, relevant references.

## Step 7: Article extraction (when relevant URLs found)

If web search or PR description references specific documentation pages (upstream API docs, RFC pages, vendor docs), extract their content for reference:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/article-extractor/scripts/article_extractor.py \
  --url <url> --format markdown
```

Use extracted content to inform requirements — do not copy it verbatim into the output.

## Step 8: Write structured requirements report

Write the report to `OUTPUT_FILE` (pipeline mode) or present to user (standalone mode). The format MUST be compatible with the planning step (docs-planner agent).

```markdown
# Documentation Requirements

**Source**: <PR/MR/commit URL or ref>
**JIRA**: <ticket URL if provided, "N/A" otherwise>
**Date**: <YYYY-MM-DD>
**Overall documentation impact**: HIGH | MEDIUM | LOW

## Summary

- Files analyzed: N (N source, N test, N config, N docs, N other)
- Documentation impact grade: HIGH | MEDIUM | LOW
- Impact categories: new_feature, api_change, config_change, breaking_change, enhancement, bug_fix
- New modules needed: N
- Existing modules to update: N
- Breaking changes requiring docs: N

## Change analysis

### Source code changes

<Categorized list of source changes with diff excerpts for high-signal files. Include file paths, what changed, and why it matters.>

### Signals detected

<List signals from gather_changes.py: new files, API surface changes, config changes, schema changes, breaking indicators.>

### Existing documentation affected

<From docs_scan.affected_files: doc files that reference changed code, with line numbers and match context. If none, state "No existing documentation references the changed code.">

### Coverage gaps identified

<From docs_scan.coverage_gaps: features or APIs without existing documentation coverage. If none, state "All changed features have existing documentation coverage.">

## Requirements by priority

### Critical

#### REQ-001: <Requirement title>
- **Source**: <PR URL> | <JIRA ticket> | <code file:line>
- **Summary**: <What changed and why it matters to users>
- **User impact**: <How users are affected>
- **Documentation action**:
  - [ ] Create `module-name.adoc` (PROCEDURE)
  - [ ] Update `existing-module.adoc` — add new parameter section
- **Acceptance criteria**:
  - [ ] <Specific, verifiable criterion 1>
  - [ ] <Specific, verifiable criterion 2>
- **References**:
  - <PR URL>: Source change
  - `src/api/preferences.py:12-45`: Implementation
  - [Upstream API docs](https://...): Reference

### High
<Same format as Critical>

### Medium
<Same format>

### Low
<Same format>

## Documentation scope

### New documentation needed

| Requirement | Module type | Description |
|---|---|---|
| REQ-001 | Concept + Procedure + Reference | <what to document> |

### Existing documentation to update

| Requirement | File | What changed |
|---|---|---|
| REQ-002 | `modules/ref-api-endpoints.adoc:45` | API endpoint modified |

### Breaking changes

| Change | Migration needed | Deprecation notice | References |
|---|---|---|---|
| <description> | Yes/No | <version/timeline> | <sources> |

## Related context

### JIRA context

<Ticket description, acceptance criteria, related tickets — include only if --ticket was provided or JIRA keys were auto-discovered. If no JIRA context, omit this subsection.>

### Web search findings

<Curated references: URL, title, relevance note. No raw search queries.>

### Existing documentation references

<Red Hat docs, upstream docs, specs consulted during analysis.>

## Sources consulted

### Code changes
- <PR/commit URL>: <title>
- `src/file.py:lines`: <what was found>

### JIRA tickets
- [PROJ-123](url): <summary>

### Pull requests / Merge requests
- [PR #42](url): <title>

### External references
- [RFC 7636](url): <relevance>
- [Upstream API docs](url): <relevance>

### Web search findings
- [Result title](url): <relevance>
```

### Report quality rules

1. **Every requirement must have acceptance criteria** — specific, verifiable conditions the documentation must satisfy
2. **Every requirement must have references** — link to source code, PRs, JIRA tickets, or external docs that support it
3. **Documentation actions must be concrete** — name specific files to create or update, with module types (CONCEPT, PROCEDURE, REFERENCE)
4. **Omit empty sections** — if no breaking changes, omit the Breaking changes table. If no JIRA context, omit that subsection.
5. **Priority is based on user impact**, not code complexity. A one-line config default change that silently breaks user workflows is Critical.

## Step 9: Reference tracking

Track all URLs and file paths consulted throughout the analysis. Include in the "Sources consulted" section:
- PR/MR/commit URLs
- JIRA ticket URLs
- Code file paths with line numbers
- Web search result URLs (with relevance notes)
- Extracted article URLs
- Existing documentation file paths

Same standard as requirements-analyst: every claim in the report should be traceable to a source.
