---
name: docs-workflow-planning
description: Create a documentation plan from requirements analysis output. Dispatches the docs-planner agent. Invoked by the orchestrator.
argument-hint: <ticket> --base-path <path>
allowed-tools: Read, Write, Glob, Grep, Edit, Bash, Skill, Agent
---

# Documentation Planning Step

Step skill for the docs-orchestrator pipeline. Follows the step skill contract: **parse args → dispatch agent → write output**.

## Arguments

- `$1` — JIRA ticket ID (required)
- `--base-path <path>` — Base output path (e.g., `.agent_workspace/proj-123`)

## Input

```
<base-path>/requirements/requirements.md
```

## Output

```
<base-path>/planning/plan.md
```

## Execution

### 1. Parse arguments

Extract the ticket ID and `--base-path` from the args string.

Set the paths:

```bash
INPUT_FILE="${BASE_PATH}/requirements/requirements.md"
OUTPUT_DIR="${BASE_PATH}/planning"
OUTPUT_FILE="${OUTPUT_DIR}/plan.md"
mkdir -p "$OUTPUT_DIR"
```

### 2. Dispatch agent

**You MUST use the Agent tool** to invoke the `docs-planner` subagent. Do NOT read the agent's markdown file or attempt to perform the agent's work yourself — the agent has a specialized system prompt and must run as an isolated subagent.

**Agent tool parameters:**
- `subagent_type`: `docs-tools:docs-planner`
- `description`: `Create documentation plan for <TICKET>`

**Prompt** (pass this as the `prompt` parameter to the Agent tool):

> Create a comprehensive documentation plan based on the requirements analysis.
>
> Read the requirements from: `<INPUT_FILE>`
>
> The plan must include:
> 1. Gap analysis (existing vs needed documentation)
> 2. Module specifications (type, title, audience, content points, prerequisites, dependencies)
> 3. Implementation order based on dependencies
> 4. Assembly structure (how modules group together)
> 5. Content sources from JIRA and PR/MR analysis
>
> Save the complete plan to: `<OUTPUT_FILE>`

**[Include only if `<BASE_PATH>/scope-req-audit/evidence-status.json` exists]** Append the following paragraph to the prompt:

> ## MANDATORY: Scope gating by code evidence
>
> **You MUST read** `<BASE_PATH>/scope-req-audit/evidence-status.json` before creating any module specifications. This file classifies each requirement by whether code evidence exists in the indexed repository.
>
> **This is not optional. Every requirement must be checked against this file.**
>
> - **Grounded** requirements: create full module specifications as normal. Use the `key_files` for each grounded requirement as content source references in the module spec — these are the actual source files where the feature is implemented. The code-evidence step will use them for targeted retrieval
> - **Partial** requirements: create module specifications but note what evidence was found and what is missing — flag for SME review. Include available `key_files` as partial source references
> - **Absent** requirements: check the `secondary_repos` array in the evidence status. If a secondary repo was cloned for this requirement (its ID appears in a `secondary_repos[].requirements` entry), **promote it to partial** — create a module specification flagged as "secondary source" with a note that evidence comes from a companion repo. The code-evidence step will search this secondary repo with lower-priority weighting. If no secondary repo covers the requirement, **STOP. Do NOT create module specifications.** List it in a "Deferred requirements (no code evidence)" section at the end of the plan with: (a) the requirement ID and title, (b) the `action` text from the evidence status, (c) which repository the implementation likely lives in (from the evidence status or discovered repos)
>
> If `discovered_repos` lists repos that weren't indexed and no `secondary_repos` were cloned, note them in the deferred section as potential sources for resolving absent requirements.
>
> **Self-check before writing the plan:** Count your module specifications. If the count exceeds the number of grounded + partial + promoted-from-absent requirements, you have created modules for unresolvable absent requirements — go back and move them to the deferred section.

### 3. Verify output

After the agent completes, verify the output file exists at `<OUTPUT_FILE>`.

If no output file is found, report an error.

**[If `<BASE_PATH>/scope-req-audit/evidence-status.json` exists]** Cross-check the plan against the audit: read the evidence status and verify that no absent requirement has a corresponding module specification in the plan. If any absent requirement was given a full module, log a warning: "Plan includes modules for absent requirement(s): <list>. These risk fabrication." This is a warning, not a blocker — the plan is still valid but the downstream writing step may produce ungrounded content.

### 4. Write step-result.json

Read `<OUTPUT_FILE>` and count the number of module specifications. Count each occurrence of:

- Level-3 headings (`###`) whose text begins with `Module:`
- Numbered or bulleted list items within the "Module Specifications" section that start with `Module:`

Ignore headings or list items outside the "Module Specifications" section, and skip items inside code blocks or blockquotes. Treat duplicate module titles as separate modules (no deduplication). This count becomes the `module_count` field.

Write the sidecar to `<OUTPUT_DIR>/step-result.json`:

```json
{
  "schema_version": 1,
  "step": "planning",
  "ticket": "<TICKET>",
  "completed_at": "<current ISO 8601 timestamp>",
  "module_count": <number of modules in the plan>,
  "context_size_bytes": <total_bytes>
}
```

After writing the sidecar, sum the byte sizes of all output files in the step's output folder and add `context_size_bytes` to the sidecar.
