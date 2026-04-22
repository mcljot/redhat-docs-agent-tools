# Import Markdown Design Spec

**Date:** 2026-04-22
**Status:** Draft
**Scope:** Tactical bridge tool (months, not years)

## Problem

A documentation writer receives a large markdown file that has been collaboratively edited in Google Docs. The markdown was originally generated from published AsciiDoc (HTML export copied into Google Docs), then edited by a team of SMEs who add new content, delete sections, and reword existing content. The writer must manually find each corresponding AsciiDoc module, apply the edits, and create new modules for new content. This is time-consuming and error-prone.

## Solution

A new step skill (`docs-workflow-import-markdown`) that splits the markdown by headings, matches sections to existing AsciiDoc modules using URL fragment IDs, and produces a match manifest. The existing docs-writer agent then applies the edits in place on a feature branch, and the existing commit/create-mr steps produce a merge request for review.

The writer reviews changes in GitLab's diff view and merges when satisfied.

## Context

This is a bridge tool. The long-term solution is an agentic pipeline with a full review and edit cycle. This tool covers the interim period where collaborative editing happens in Google Docs. Design for reliability at 80% accuracy, not perfection.

## Data flow

```
markdown file
    |
    v
[import-markdown] -- splits by heading, matches to .adoc modules
    |
    v
match-manifest.json
    |
    v
[prepare-branch] -- creates feature branch (existing step)
    |
    v
[writing (import mode)] -- updates matched modules, creates new ones (existing agent, new mode)
    |
    v
[commit] -- commits and pushes (existing step)
    |
    v
[create-mr] -- creates MR for review (existing step)
```

## Design

### 1. Content matching (import-markdown skill)

The skill takes two inputs: the markdown file path and the target docs repo path (current working directory by default).

**Splitting:** Split the markdown into sections by heading level (`##`, `###`, `####`). Each section gets its heading text, body content (everything until the next heading of equal or higher level), and heading level.

**ID extraction:** Most headings contain `docs.redhat.com` links with URL fragments that include the AsciiDoc module ID. For example:

```markdown
### [2.1. About the Red Hat Python index](https://docs.redhat.com/...#about-the-python-index_custom-models)
```

The fragment `about-the-python-index_custom-models` maps to `[id="about-the-python-index_{context}"]` in the AsciiDoc source. The `_{context}` portion is a variable placeholder — the actual ID stem is everything before it. To extract the stem, strip the last `_<word>` segment from the fragment (e.g., `about-the-python-index_custom-models` becomes `about-the-python-index`). This is a simple heuristic that works because context variables are single tokens like `custom-models`, `rhoai-user`, etc.

**Matching:** For each extracted ID stem, grep the docs repo for `[id="<id-stem>_` in `.adoc` files (the trailing underscore ensures we match the stem, not a substring). This gives the file path.

**Fallback:** Sections without `docs.redhat.com` links fall back to heading-text matching — search for the heading text (stripped of numbering like "2.1.") in existing module titles (`= <title>` lines in `.adoc` files).

**Classification:**
- `matched` — ID or heading matched exactly one module file
- `new` — no URL fragment and no heading match; this is new content
- `skipped` — ambiguous match (multiple files match) or other failure, with a logged reason

**Preamble handling:** Content before the first `##` heading (e.g., the draft instructions, abstract, legal notice) is classified as `preamble` and skipped with a note.

### 2. Match manifest schema

```json
{
  "source_file": "/path/to/markdown.md",
  "repo_path": "/path/to/docs-repo",
  "sections": [
    {
      "heading": "About the Red Hat Python index",
      "level": 3,
      "status": "matched",
      "module_path": "modules/about-the-python-index.adoc",
      "matched_by": "url_fragment",
      "id_fragment": "about-the-python-index_custom-models",
      "content": "..."
    },
    {
      "heading": "New feature section",
      "level": 3,
      "status": "new",
      "module_path": null,
      "matched_by": null,
      "id_fragment": null,
      "content": "..."
    },
    {
      "heading": "Ambiguous section",
      "level": 3,
      "status": "skipped",
      "module_path": null,
      "matched_by": null,
      "id_fragment": "some-id",
      "reason": "Multiple matches: modules/foo.adoc, modules/bar.adoc",
      "content": "..."
    }
  ],
  "summary": {
    "matched": 12,
    "new": 3,
    "skipped": 1,
    "preamble_skipped": 1,
    "total": 17
  }
}
```

### 3. Writing step integration

Add an `import` mode to the existing `docs-workflow-writing` skill. Triggered by a new `--import-from <manifest-path>` flag.

The `build_writing_args.sh` script detects `--import-from` and sets `mode: import`. The prompt to the docs-writer agent:

**For matched sections:** Read the existing AsciiDoc module at `module_path`. Replace the body content with the content from the manifest, converting markdown to proper AsciiDoc. Preserve:
- `:_mod-docs-content-type:` attribute
- `[id="..._{context}"]` anchor
- `[role="_abstract"]` tag
- Any `include::` directives not covered by the new content
- Existing AsciiDoc attributes and conditionals

**For new sections:** Create a new AsciiDoc module. Determine the content type (CONCEPT, PROCEDURE, REFERENCE) from the content structure. Follow the repo's existing file naming and directory conventions. Add an `include::` statement in the appropriate assembly file.

**Skip sections with status "skipped".**

Output: a writing manifest (`_index.md`) listing all files written and modified — same format the commit step expects.

### 4. Workflow YAML

New file at `defaults/docs-import.yaml`:

```yaml
workflow:
  name: docs-import
  description: Import edited markdown back into AsciiDoc modules, creating a merge request for review.

  steps:
    - name: import-markdown
      skill: docs-workflow-import-markdown
      description: Split markdown and match sections to AsciiDoc modules

    - name: prepare-branch
      skill: docs-workflow-prepare-branch
      description: Create feature branch
      inputs: [import-markdown]

    - name: writing
      skill: docs-workflow-writing
      description: Apply content updates to matched modules
      inputs: [import-markdown, prepare-branch]

    - name: commit
      skill: docs-workflow-commit
      description: Commit and push changes
      inputs: [writing]

    - name: create-mr
      skill: docs-workflow-create-mr
      description: Create merge request
      inputs: [commit]
```

Invoked via the orchestrator: `/docs-tools:docs-orchestrator custom-models-3.4 --workflow import --markdown /path/to/edited-doc.md`

### 5. Skill arguments

**import-markdown skill:**
- `$1` — label/identifier (e.g., `custom-models-3.4` or a JIRA ticket ID)
- `--markdown <path>` — path to the markdown file (required)
- `--base-path <path>` — output path for manifest and logs

**Orchestrator additions:**
- `--workflow import` — selects `docs-import.yaml`
- `--markdown <path>` — passed through to the import-markdown step

### 6. Files to create/modify

| File | Action | Description |
|------|--------|-------------|
| `skills/docs-workflow-import-markdown/SKILL.md` | New | Matching and splitting skill |
| `skills/docs-orchestrator/defaults/docs-import.yaml` | New | Workflow definition |
| `skills/docs-workflow-writing/SKILL.md` | Modify | Add `import` mode prompt |
| `skills/docs-workflow-writing/scripts/build_writing_args.sh` | Modify | Handle `--import-from` flag |
| `.claude/skills/docs-workflow-import-markdown` | New | Symlink |
| `.claude-plugin/plugin.json` | Modify | Version bump |

### 7. Logging and failure handling

The match manifest includes a `skipped` status with a `reason` field for sections that fail matching. The skill prints a summary at completion:

```
Import matching complete: 12 matched, 3 new, 1 skipped
Skipped sections require manual attention — see match-manifest.json for details.
```

Skipped sections are not passed to the writing step. The user resolves them manually after reviewing the MR.

## Out of scope

- Style review (follow-on enhancement)
- Technical review (follow-on enhancement)
- Multi-file markdown input (single file only)
- Automated context variable detection (use simple last-underscore-segment heuristic)
- Full agentic review/edit pipeline (this is the bridge to that future)

## Testing

Test with the provided sample document (`Copy of DRAFT for 3.4 updates_ Customize models to build gen AI applications.md`) against the `openshift-ai-documentation` repo. Success criteria:
- All sections with `docs.redhat.com` links match to the correct module
- New sections (if any) are classified as `new`
- The docs-writer produces valid AsciiDoc that preserves module scaffolding
- The MR diff shows clean, reviewable changes
