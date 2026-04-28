---
name: docs-workflow-writing
description: Write documentation from a documentation plan. Dispatches the docs-writer agent. Supports AsciiDoc (default) and MkDocs formats. Default placement is UPDATE-IN-PLACE; use --draft for staging area. Also supports fix mode for applying technical review corrections.
argument-hint: <ticket> --base-path <path> --format <adoc|mkdocs> [--draft] [--repo-path <path>] [--fix-from <review_path>] [--import-from <manifest_path>]
allowed-tools: Read, Write, Glob, Grep, Edit, Bash, Skill, Agent
---

# Documentation Writing Step

Step skill for the docs-orchestrator pipeline. Follows the step skill contract: **run script → dispatch agent → verify output**.

## Execution

### 1. Run the script

Run the build script to parse arguments, validate inputs, determine mode, and create output directories:

```bash
bash ${CLAUDE_SKILL_DIR}/scripts/build_writing_args.sh <args>
```

Pass through the full args string. The script emits JSON on stdout:

```json
{
  "mode":          "update-in-place | draft | fix | import",
  "ticket":        "PROJ-123",
  "format":        "adoc | mkdocs",
  "input_file":    "<base-path>/planning/plan.md",
  "evidence_file": "<base-path>/code-evidence/evidence.json | null",
  "has_evidence":  true | false,
  "output_dir":    "<base-path>/writing",
  "output_file":   "<base-path>/writing/_index.md",
  "repo_path":     "<path> | null",
  "fix_from":      "<path> | null",
  "import_from":   "<path> | null",
  "verify_output": true | false
}
```

If the script exits non-zero, stop and report the error from stderr.

### 2. Dispatch the docs-writer agent

**You MUST use the Agent tool** to invoke the `docs-writer` subagent. Do NOT read the agent's markdown file or attempt to perform the agent's work yourself — the agent has a specialized system prompt and must run as an isolated subagent.

Select the prompt based on `mode` and `format` from the JSON output. In every prompt below, substitute the `<TICKET>`, `<INPUT_FILE>`, `<OUTPUT_FILE>`, `<OUTPUT_DIR>`, `<REPO_PATH>`, and `<FIX_FROM>` placeholders with the corresponding values from the script's JSON.

**Agent tool parameters for all modes:**
- `subagent_type`: `docs-tools:docs-writer`
- `description`: use the value described under each mode below

---

#### Mode: `update-in-place`, format: `adoc`

**Description:** `Write adoc documentation for <TICKET>`

**Prompt:**

> Write complete AsciiDoc documentation based on the documentation plan for ticket `<TICKET>`.
>
> Read the plan from: `<INPUT_FILE>`
>
> **[Include only if HAS_EVIDENCE=true]** Code evidence is available at `<EVIDENCE_FILE>`. Read it and use the `source_results` for accurate function signatures, parameter types, and code examples. Use `context_results` for narrative context, installation steps, and architectural patterns. Prefer evidence over assumptions — if the evidence contradicts the plan, follow the evidence.
>
> **IMPORTANT**: Write COMPLETE .adoc files, not summaries or outlines.
>
> **Placement mode: UPDATE-IN-PLACE**
>
> [If `repo_path` is not null: "The target repository is at `<REPO_PATH>`. Explore **that directory** for framework detection and write files there."]
>
> Place files directly in the repository following existing conventions. Before writing any files:
> 1. Detect the repository's documentation build framework (Antora, ccutil, Sphinx, etc.)
> 2. Analyze existing file naming conventions, directory layout, include patterns, and nav/TOC structure
> 3. Determine the correct target path for each module based on the detected framework and conventions
>
> Write modules and assemblies directly to their correct repo locations. Update navigation/TOC files as needed, following existing patterns.
>
> Create a manifest at `<OUTPUT_FILE>` listing **all files written and modified** with **absolute paths**. The manifest must include every intentional change — both new files created and existing files modified (e.g., nav/TOC updates).
>
> [If `repo_path` is not null: "Record `Target repo: <REPO_PATH>` in the manifest header."]

---

#### Mode: `update-in-place`, format: `mkdocs`

**Description:** `Write mkdocs documentation for <TICKET>`

**Prompt:**

> Write complete Material for MkDocs Markdown documentation based on the documentation plan for ticket `<TICKET>`.
>
> Read the plan from: `<INPUT_FILE>`
>
> **[Include only if HAS_EVIDENCE=true]** Code evidence is available at `<EVIDENCE_FILE>`. Read it and use the `source_results` for accurate function signatures, parameter types, and code examples. Use `context_results` for narrative context, installation steps, and architectural patterns. Prefer evidence over assumptions — if the evidence contradicts the plan, follow the evidence.
>
> **IMPORTANT**: Write COMPLETE .md files with YAML frontmatter (title, description). Use Material for MkDocs conventions: admonitions, content tabs, code blocks with titles, heading hierarchy starting at `# h1`.
>
> **Placement mode: UPDATE-IN-PLACE**
>
> [If `repo_path` is not null: "The target repository is at `<REPO_PATH>`. Explore **that directory** for framework detection and write files there."]
>
> Place files directly in the repository following existing conventions. Before writing any files:
> 1. Detect the repository's documentation build framework (MkDocs, Docusaurus, Hugo, etc.)
> 2. Analyze existing file naming conventions, directory layout, and nav structure
> 3. Determine the correct target path for each page based on the detected framework and conventions
>
> Write pages directly to their correct repo locations. Update `mkdocs.yml` nav section or equivalent as needed, following existing patterns.
>
> Create a manifest at `<OUTPUT_FILE>` listing **all files written and modified** with **absolute paths**. The manifest must include every intentional change — both new files created and existing files modified (e.g., `mkdocs.yml` nav updates).
>
> [If `repo_path` is not null: "Record `Target repo: <REPO_PATH>` in the manifest header."]

---

#### Mode: `draft`, format: `adoc`

**Description:** `Write adoc documentation for <TICKET>`

**Prompt:**

> Write complete AsciiDoc documentation based on the documentation plan for ticket `<TICKET>`.
>
> Read the plan from: `<INPUT_FILE>`
>
> **[Include only if HAS_EVIDENCE=true]** Code evidence is available at `<EVIDENCE_FILE>`. Read it and use the `source_results` for accurate function signatures, parameter types, and code examples. Use `context_results` for narrative context, installation steps, and architectural patterns. Prefer evidence over assumptions — if the evidence contradicts the plan, follow the evidence.
>
> **IMPORTANT**: Write COMPLETE .adoc files, not summaries or outlines.
>
> **Placement mode: DRAFT (staging area)**
>
> Save files to the staging area. Do not modify any existing repository files.
>
> Output folder structure:
> ```
> <OUTPUT_DIR>/
> ├── _index.md                     # Index of all modules
> ├── assembly_<name>.adoc          # Assembly files at root
> └── modules/                      # All module files
>     ├── <concept-name>.adoc
>     ├── <procedure-name>.adoc
>     └── <reference-name>.adoc
> ```
>
> Save modules to: `<OUTPUT_DIR>/modules/`
> Save assemblies to: `<OUTPUT_DIR>/`
> Create index at: `<OUTPUT_FILE>`

---

#### Mode: `draft`, format: `mkdocs`

**Description:** `Write mkdocs documentation for <TICKET>`

**Prompt:**

> Write complete Material for MkDocs Markdown documentation based on the documentation plan for ticket `<TICKET>`.
>
> Read the plan from: `<INPUT_FILE>`
>
> **[Include only if HAS_EVIDENCE=true]** Code evidence is available at `<EVIDENCE_FILE>`. Read it and use the `source_results` for accurate function signatures, parameter types, and code examples. Use `context_results` for narrative context, installation steps, and architectural patterns. Prefer evidence over assumptions — if the evidence contradicts the plan, follow the evidence.
>
> **IMPORTANT**: Write COMPLETE .md files with YAML frontmatter (title, description). Use Material for MkDocs conventions: admonitions, content tabs, code blocks with titles, heading hierarchy starting at `# h1`.
>
> **Placement mode: DRAFT (staging area)**
>
> Save files to the staging area. Do not modify any existing repository files.
>
> Output folder structure:
> ```
> <OUTPUT_DIR>/
> ├── _index.md                     # Index of all pages
> ├── mkdocs-nav.yml                # Suggested nav tree fragment
> └── docs/                         # All page files
>     ├── <concept-name>.md
>     ├── <procedure-name>.md
>     └── <reference-name>.md
> ```
>
> Save pages to: `<OUTPUT_DIR>/docs/`
> Create nav fragment at: `<OUTPUT_DIR>/mkdocs-nav.yml`
> Create index at: `<OUTPUT_FILE>`

---

#### Mode: `fix`

**Description:** `Fix documentation for <TICKET>`

**Prompt:**

> Apply fixes to documentation drafts based on technical review feedback for ticket `<TICKET>`.
>
> Read the review report from: `<FIX_FROM>`
> Drafts location: `<OUTPUT_DIR>/`
>
> For each issue flagged in the review:
> 1. If the fix is clear and unambiguous, apply it directly
> 2. If the issue requires broader context or judgment, skip it
> 3. Do NOT rewrite content that was not flagged
>
> Edit files in place. Do NOT create copies or new files.

In fix mode, the skill does not create new modules or restructure content.

---

#### Mode: `import`

**Description:** `Import markdown updates for <TICKET>`

**Prompt:**

> Convert edited markdown content back into AsciiDoc modules for `<TICKET>`.
>
> Read the import manifest from: `<INPUT_FILE>`
>
> The manifest is a JSON file with a `sections` array. Each section has a `status`, `heading`, `content`, and optionally a `module_path`.
>
> [If `repo_path` is not null: "The target repository is at `<REPO_PATH>`. All module paths in the manifest are relative to this directory."]
>
> **CRITICAL: Preserve the author's original wording.** The `content` field contains text written by subject matter experts. Your job is to convert markdown syntax to AsciiDoc syntax — NOT to rewrite, rephrase, summarize, expand, or improve the prose. Every sentence in the output must come from the input. Do not add sentences, remove sentences, merge sentences, or split sentences. Do not add introductory or concluding text that is not in the source. If the original text is awkward or incomplete, keep it as-is — the writer will fix it during review.
>
> **Syntax conversion rules:**
> - `**bold**` → `*bold*`
> - `[link text](url)` → `link:url[link text]`
> - `` `code` `` → `` `code` `` (no change)
> - Code blocks → `[source,language]\n----\n...\n----`
> - `- item` / `* item` → `* item` (AsciiDoc unordered list)
> - `1. item` → `. item` (AsciiDoc ordered list)
> - Nested lists → use `**` / `***` prefix levels
> - `> blockquote` → use AsciiDoc admonition if appropriate, otherwise keep as-is
> - Tables → AsciiDoc table syntax (`|===`)
> - Headings within a section body → use relative AsciiDoc heading levels (`.Title` for titled blocks, or `=` levels relative to module root)
> - One sentence per line (ventilated prose)
>
> **For sections with status `matched`:**
>
> 1. Check `module_path` — if it starts with `upstream/`, **skip this section entirely**. Upstream modules are maintained by an upstream project and must never be modified during import.
> 2. Read the existing AsciiDoc module at `module_path`
> 3. Replace the body content with the `content` from the manifest, converting markdown syntax to AsciiDoc syntax using the rules above
> 4. Preserve the following elements from the original module — do NOT remove or modify them:
>    - `:_mod-docs-content-type:` attribute
>    - `[id="..._{context}"]` anchor
>    - `[role="_abstract"]` tag
>    - Any `ifdef::` / `ifndef::` / `ifeval::` conditionals
>    - Any `:context:` attribute assignments
>    - Any `include::` directives — do NOT add, remove, or modify include directives. Assembly wiring is handled by a separate post-processing step.
> 5. Write the updated module back to the same path
>
> **For sections with status `new`:**
>
> 1. Determine the content type (CONCEPT, PROCEDURE, or REFERENCE) from the content structure:
>    - Numbered steps or "Prerequisites" → PROCEDURE
>    - Tables, lists of specs, API fields → REFERENCE
>    - Everything else → CONCEPT
> 2. Create a new AsciiDoc module in `modules/` following the repo's existing file naming conventions (e.g., `modules/<kebab-title>.adoc`). Never create files under `upstream/`.
> 3. Include the standard module scaffolding: content type attribute, ID anchor, title, and abstract tag
> 4. Convert the `content` from markdown to AsciiDoc syntax using the rules above — do NOT rewrite the prose
> 5. Do NOT add `include::` directives to assembly files — assembly wiring is handled by a separate post-processing step
>
> **Skip sections with status `skipped` or `preamble`.** Do not process them.
>
> Create a manifest at `<OUTPUT_FILE>` listing **all files written and modified** with **absolute paths**. The manifest must include every intentional change — both new files created and existing files modified (e.g., assembly updates).
>
> [If `repo_path` is not null: "Record `Target repo: <REPO_PATH>` in the manifest header."]

---

### 3. Post-processing: Wire assemblies (import mode only)

**Only run this step when `mode == "import"` AND `repo_path` is not null.**

After the writing agent finishes, run the assembly wiring script to add `include::` directives deterministically:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/docs-workflow-import-markdown/scripts/wire_assemblies.py \
  --manifest <INPUT_FILE> --repo-path <REPO_PATH>
```

The script reads the match manifest, parses original assembly files to learn which sections were previously inlined vs included, and rebuilds each assembly preserving the same structure. It also creates new assemblies and updates `master.adoc` when needed.

The script emits JSON on stdout with:
- `assemblies_updated`: list of assembly files modified
- `assemblies_created`: list of new assembly files created
- `master_updated`: path to master.adoc if updated
- `missing_modules`: include targets where the module file does not exist on disk — report these to the user

If `missing_modules` is non-empty, warn the user:

> The following modules are referenced by include directives but do not exist on disk. They may need to be created manually: `<list>`

### 4. Verify output

If `verify_output` is `true` in the script's JSON output, check that `output_file` exists.

If `verify_output` is `false` (fix mode), no verification is needed — files are edited in place.

### 4. Write step-result.json

Skip this step if `mode` is `"fix"` (fixes edit files in place — no new manifest to parse).

Read the manifest at `<OUTPUT_FILE>` (`_index.md`). Extract every absolute file path from the table rows. These become the `files` array.

Write the sidecar to `<OUTPUT_DIR>/step-result.json` using the `mode` and `format` values from the script's JSON output:

```json
{
  "schema_version": 1,
  "step": "writing",
  "ticket": "<TICKET>",
  "completed_at": "<current ISO 8601 timestamp>",
  "files": [
    "/absolute/path/to/file1.adoc",
    "/absolute/path/to/file2.adoc"
  ],
  "mode": "<mode from script JSON>",
  "format": "<format from script JSON>"
}
```
