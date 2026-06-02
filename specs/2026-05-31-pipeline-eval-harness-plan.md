# Pipeline evaluation harness for RHDAT

**Date:** 2026-05-31
**Status:** Planning
**Context:** Slack discussion with Antonin re: using `agent-eval-harness` to measure pipeline quality across refactors. Reference implementation: [rfe-creator eval.yaml](https://github.com/opendatahub-io/rfe-creator/blob/b948f9990d5d10a61410131e3a95590c8e749379/eval.yaml)

## Problem

We are refactoring the docs-orchestrator pipeline based on lessons learned from merged MRs. We need to measure whether pipeline changes produce better or worse documentation, using the merged MR content (with human edits) as ground truth.

## Approach

Use `agent-eval-harness` with a custom LLM pairwise judge, following the pattern established by the RFE creator. The harness orchestrates: run the pipeline, collect output, judge output against ground truth, produce a comparison report (win/loss/tie per case with diffs and rationale).

## Steps

### 1. Build the eval dataset from merged MRs

Create `eval/dataset/cases/` with one directory per completed documentation ticket:

```
eval/dataset/cases/
  case-001-rhaistrat-1393/
    input.yaml          # Pipeline inputs: JIRA ticket, source repo, PRs
    annotations.yaml    # Ground truth: final merged AsciiDoc after human edits
  case-002-infereng-5576/
    input.yaml
    annotations.yaml
  ...
```

- **input.yaml** contains everything the orchestrator needs: ticket ID, source repo URL, PRs, workflow type
- **annotations.yaml** contains the final merged AsciiDoc files from the MR after human review and edits
- Start with 10-15 merged MRs covering variety: different doc types (concept, procedure, reference), complexity levels, and products

**How to capture ground truth:** Script extraction from merge commits (checkout the merge commit, extract the doc files) or manually curate. Curation quality directly determines eval usefulness.

### 2. Write the pairwise judge prompt

Create `eval/config/pairwise-judge.md`. This is the most important artifact. The judge compares pipeline output (candidate) against merged MR content (reference) on specific dimensions:

- **Completeness** -- does the candidate cover all topics present in the reference?
- **Technical accuracy** -- are procedures, commands, prerequisites correct?
- **Structure** -- does it follow modular docs (assembly + concept/proc/ref modules)?
- **Style compliance** -- IBM Style Guide, Red Hat SSG adherence
- **Signal-to-noise** -- no fabricated content, no filler, no hallucinated features

Calibrate the prompt on 3-5 cases manually before committing to a full eval run. Read the judge rationale and adjust until verdicts match your human judgement.

### 3. Write the eval.yaml

Model on the RFE creator structure. Key sections:

```yaml
skill: docs-tools:docs-orchestrator
mode: batch
runner: claude-code
timeout: 7200

models:
  skill: claude-opus-4-6
  judge: claude-opus-4-7

dataset:
  path: eval/dataset/cases

evaluators:
  # Inline/programmatic checks
  - name: files_exist
    # Did the pipeline produce AsciiDoc output?

  - name: step_results_valid
    # Are all step-result.json sidecars well-formed?

  - name: pipeline_flow
    # Did all orchestrator steps complete without error?

  # LLM judges
  - name: doc_quality
    type: llm
    # Absolute quality score (1-5) per case

  - name: pairwise
    type: llm
    prompt_file: eval/config/pairwise-judge.md
    # A/B comparison: pipeline output vs merged MR ground truth
```

### 4. Capture a baseline run

Run the eval harness against the **current** pipeline before any refactoring. This baseline is what all future comparisons measure against. The report records scores, cost, duration, and per-case verdicts.

### 5. Refactor the pipeline

Make changes: new steps, different prompts, model swaps, workflow restructuring. The eval harness doesn't care what changed -- it only compares outputs.

### 6. Run the eval with `--baseline`

Point `--baseline` at the step 4 run. This triggers the pairwise judge and produces the side-by-side comparison report: win/loss/tie per case, with diffs and rationale. Same format as the [Opus 4.7 vs 4.6 comparison report](eval-report-example.html).

### 7. Iterate

Review per-case results:
- **Losses** -- where the refactored pipeline regressed. Investigate root cause.
- **Ties** -- neutral changes. Check if the judge prompt is sensitive enough.
- **Wins** -- confirmed improvements.

Tune pipeline and re-run until consistently winning or tying across cases.

## Key decisions to make

| Decision | Options | Impact |
|----------|---------|--------|
| Ground truth extraction | Script from merge commits vs manual curation | Curation quality = eval quality |
| Judge prompt calibration | Iterate on 3-5 cases manually first | Noisy judge = useless eval |
| Dataset size | 10-15 cases minimum, more is better | Too few = results dominated by variance |
| Judge model | Same as pipeline model vs stronger model | Stronger judge reduces bias but costs more |
| Which merged MRs to include | Recent only vs historical spread | Variety of doc types matters more than recency |

## Reference

- **RFE creator eval.yaml:** [GitHub link](https://github.com/opendatahub-io/rfe-creator/blob/b948f9990d5d10a61410131e3a95590c8e749379/eval.yaml) -- 20 cases, 8 judges (6 inline + 2 LLM + 1 pairwise), 100% pass thresholds on inline checks, mean >= 3.5 on LLM judges
- **Pairwise judge prompt:** Lives in external file (`eval/config/pairwise-judge.md`), not inlined in eval.yaml
- **Report format:** HTML with per-case expandable sections showing verdicts, diffs, and judge rationale
- **RFE eval results example:** 17W / 1L / 2T across 20 cases, 43 min runtime, $36.48 cost per run
