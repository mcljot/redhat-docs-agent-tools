# Assessment: agent-eval-harness for RHDAT pipeline evaluation

**Date:** 2026-06-01
**Repo:** https://github.com/opendatahub-io/agent-eval-harness
**Version assessed:** v1.4.0
**Companion docs:** [Pipeline eval harness plan](2026-05-31-pipeline-eval-harness-plan.md), [Eval spec review](2026-06-01-pipeline-eval-spec-review.md)

## What it is

A generic evaluation framework from the OpenDataHub team (Apache-2.0) that evaluates skills as black boxes. Given an `eval.yaml` describing a skill's inputs, outputs, and judges, it runs the skill headlessly across test cases, scores output with inline checks and LLM judges, detects regressions, and produces comparison reports.

## The 7-stage pipeline

| Stage | What it does | Relevant to RHDAT? |
|---|---|---|
| **eval-setup** | Install deps, configure MLflow, verify API keys | Yes -- one-time setup |
| **eval-analyze** | Reads SKILL.md, auto-generates draft eval.yaml with suggested judges | Useful starting point, needs heavy customization |
| **eval-dataset** | Auto-generates test cases (default 5) or fills coverage gaps | Limited -- our test cases are real JIRA tickets + merged MRs, not synthetic |
| **eval-run** | Runs skill headlessly, collects artifacts, scores with judges, detects regressions | The core. Supports parallelism, single-case runs, baseline comparisons |
| **eval-review** | Interactive human review of judge scores, provide feedback | Useful for judge calibration |
| **eval-mlflow** | Syncs datasets/results to MLflow, attaches judge feedback to traces | Nice-to-have for tracking over time |
| **eval-optimize** | Auto-identifies failures from traces, edits skill, re-runs to verify | Interesting but risky for multi-step pipeline |

## How it maps to RHDAT needs

### What aligns well

- **`eval-run` with pairwise judges** is exactly what was discussed with Antonin. The RFE creator example proves it works for multi-step pipelines.
- **`case` mode** maps to our orchestrator (one JIRA ticket = one invocation = one test case).
- **Tool interception** handles `AskUserQuestion` auto-answering during requirements and planning. Three-tier answering (exact override, LLM with context, fallback to first option) is well-designed.
- **Judge types** cover everything needed: inline checks for structural validation, LLM judges for quality scoring, pairwise judges for A/B comparison, external Python modules for custom logic.
- **Thresholds** with `min_mean`, `min_pass_rate`, and `min_win_rate` map directly to regression detection needs.

### What needs adaptation

- **The harness evaluates a single skill invocation.** Our pipeline is a multi-step orchestrator that internally invokes 5-7 sub-skills. Point the harness at `docs-orchestrator` as the top-level skill. This treats the entire pipeline as one black box -- fine for end-to-end quality, but no per-step attribution.
- **Ground truth format.** The harness expects `reference.md` or `annotations.yaml` per case. Merged MR AsciiDoc files need packaging into that format.
- **Cost and timeout.** The RFE creator runs 20 cases in ~43 min at ~$36. Our docs pipeline is heavier (requirements + planning + writing + reviews + MR). Budget 2-3x per case. 15 cases might run 90+ minutes at $50-80.
- **Permissions.** The orchestrator needs git, GitHub/GitLab CLIs, and potentially JIRA access. The `permissions` block needs careful setup to allow these while keeping eval hermetic (e.g., `--dry-run` for MR creation).

### What's missing for the full eval spec (stage 2)

- **No composite decision rules.** Judges evaluated independently with per-judge thresholds. The spec's Section 5.5 composite rule (accuracy AND coverage AND no false-supported increase) would need custom judges or post-processing.
- **No position-bias control.** Pairwise judges don't auto-randomize presentation order.
- **No instrument reliability tracking (M-R1, M-R2, M-R3).** `eval-review` lets humans score alongside the judge, but no automated agreement calculation or distrust threshold.
- **No N-times sampling for variance estimation.** One run per variant per case.

## eval.yaml reference structure

```yaml
skill: my-skill-name
mode: case
runner:
  type: claude-code
models:
  skill: claude-opus-4-6
  judge: claude-opus-4-6
dataset:
  path: eval/dataset/cases
  schema: "each case has input.yaml (prompt) and reference.md"
outputs:
  - type: file
    path: artifacts
judges:
  - name: has_content       # inline check
  - name: output_quality    # LLM judge (1-5)
  - name: pairwise          # A/B comparison (activated with --baseline)
thresholds:
  output_quality:
    min_mean: 3.5
  has_content:
    min_pass_rate: 1.0
```

## Bottom line

The harness is the right tool for step 1. It handles the mechanical parts (headless execution, artifact collection, judge orchestration, regression detection, HTML reporting) so effort focuses on the two things that matter: building the test case dataset and writing a good judge prompt.

The full eval spec (rev 2) goes beyond what the harness provides out of the box. Composite decision rules, instrument reliability metrics, and statistical controls would layer on top as stage 2.
