---
name: docs-workflow-import-markdown
description: Split an edited markdown file by headings and match sections to existing AsciiDoc modules using URL fragment IDs. Produces a match manifest for the writing step.
argument-hint: <ticket> --markdown <path> --base-path <path> [--repo-path <path>]
allowed-tools: Bash, Read
---

# Import Markdown Step

Step skill for the docs-orchestrator import pipeline. Follows the step skill contract: **run script → verify output**.

## Execution

### 1. Run the script

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/import_markdown.py <args>
```

Pass through the full args string. The script:

1. Reads the markdown file
2. Splits it into sections by heading level (`##`, `###`, `####`)
3. Extracts `docs.redhat.com` URL fragment IDs from heading links
4. Matches each section to an `.adoc` module in the target repo (by ID stem grep, then heading text fallback)
5. Writes `match-manifest.json` to `<base-path>/import-markdown/`

The script emits JSON on stdout:

```json
{
  "manifest_path": "<base-path>/import-markdown/match-manifest.json",
  "output_dir": "<base-path>/import-markdown",
  "summary": {
    "matched": 12,
    "new": 3,
    "skipped": 1,
    "preamble_skipped": 1,
    "total": 17
  }
}
```

If the script exits non-zero, stop and report the error from stderr.

### 2. Verify output

Check that the `manifest_path` from the JSON output exists.

### 3. Report summary

Print the summary to the user:

```
Import matching complete: <matched> matched, <new> new, <skipped> skipped
```

If there are skipped sections, add:

```
Skipped sections require manual attention — see match-manifest.json for details.
```

## Known limitations

**Structural changes redistribute content.** When SMEs add new sub-headings and move existing content under them (e.g., splitting section 4.3 into 4.3 + 4.3.1), the parent section's content becomes empty while the child gets the content. The matched parent module will be updated with a near-empty body, and the child will be created as a new module. The content is not lost — it moves to the new module — but the writer should review the MR diff carefully to verify the restructuring is correct.
