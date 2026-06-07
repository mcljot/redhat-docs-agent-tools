# Pipeline Evaluation Harness

Evaluate the `docs-orchestrator` pipeline against a fixed set of test cases to measure quality, completeness, and performance across code changes.

## Prerequisites

- Claude Code with the `agent-eval-harness` plugin installed
- `docs-tools` plugin installed
- Python 3.13+ with `google-auth` and `jinja2` packages
- Access to the JIRA API (`JIRA_API_TOKEN` and `JIRA_EMAIL` environment variables)
- Access to internal GitLab repos (for docs repo worktrees)

Install Python dependencies:

```bash
pip3 install --break-system-packages google-auth jinja2
```

## Quick start

### 1. Set up docs repo worktrees

Each test case needs a docs repo checked out at a pinned SHA. Run the setup script once:

```bash
bash eval/scripts/setup-eval-worktrees.sh
```

This clones and checks out the docs repo for each case at the SHA recorded in `input.yaml`. The worktrees are stored at `eval/dataset/cases/<case>/.docs-worktree`.

### 2. Run the eval

**Quick run (6 gold-standard cases, ~2 hours, ~$200):**

```bash
/eval-run --model claude-opus-4-6 --cases case-001-rhoaieng-45969 case-002-rhaistrat-853 case-004-rhaistrat-1393 case-008-rhai-eng-2620 case-011-rhoaieng-16840 case-012-rhoaieng-40664
```

**Full run (all 11 cases, ~4 hours, ~$400):**

```bash
/eval-run --model claude-opus-4-6
```

The quick run uses 6 gold-standard cases (authored by chtyler/stmccart) that cover the key ticket types. Use the full run for milestone validations (pre-merge, release candidates).

### 3. Review results

The report is at `eval/runs/<run-id>/report.html`. Key files:

- `summary.yaml` — per-case scores and aggregate metrics
- `analysis.md` — automated analysis with recommendations
- `run_result.json` — execution metadata (cost, duration, tokens)
- `cases/<case-id>/` — per-case artifacts and outputs

## Comparing runs after pipeline changes

The primary use case: you've made architectural changes to the pipeline and want to measure the impact.

### 1. Establish a baseline

Run the eval on the current `main` branch (or your known-good state):

```bash
/eval-run --model claude-opus-4-6 --run-id baseline-v1
```

### 2. Make your changes

Switch to your feature branch with the pipeline changes.

### 3. Reset docs repo worktrees

The previous run modified the docs repos in-place. Reset them to the pinned SHAs:

```bash
bash eval/scripts/setup-eval-worktrees.sh
```

### 4. Run the eval with baseline comparison

```bash
/eval-run --model claude-opus-4-6 --baseline baseline-v1
```

This runs the eval, scores it, and adds a **pairwise comparison** section to the report showing wins/losses/ties per judge against the baseline.

### 5. Interpret the comparison

The analysis will show:
- **Which judges improved or regressed** — e.g., pipeline_complete went from 58% to 100%
- **Per-case deltas** — which specific cases changed
- **Cost attribution** — whether cost changes come from your pipeline changes or model variance

## What the judges measure

| Judge | Type | What it checks |
|-------|------|----------------|
| `files_exist` | check | At least 1 AsciiDoc file was written |
| `step_results_valid` | check | Requirements, planning, and writing steps all produced valid `step-result.json` |
| `pipeline_complete` | check | Workflow progress file shows `status: completed` |
| `doc_quality` | LLM | Scores documentation 1-5 on accuracy, completeness, structure, and absence of fabrication |

## Configuration

The eval config is at `eval/eval.yaml`. Key settings:

| Setting | Default | Description |
|---------|---------|-------------|
| `execution.parallelism` | 3 | Concurrent cases |
| `execution.timeout` | 5400 | Per-case timeout in seconds (1h 30m) |
| `execution.max_budget_usd` | 50 | Max spend per case |
| `models.skill` | claude-opus-4-6 | Model for the pipeline |
| `models.judge` | claude-opus-4-6 | Model for LLM judges |

## Dataset

11 test cases from gold-standard MRs authored by experienced tech writers (chtyler, stmccart). Each case has:

- `input.yaml` — JIRA ticket ID, source repo URL + SHA, docs repo URL + SHA
- `.docs-worktree/` — docs repo checked out at the pinned SHA (created by setup script)

Cases cover a range of OpenShift AI features: model caching, agent deployment, Llama Stack providers, RAG pipelines, model registries, and model catalogs.

### Quick vs full case sets

| Set | Cases | Cost | Time | Use for |
|-----|-------|------|------|---------|
| **Quick** (6 gold-standard) | 001, 002, 004, 008, 011, 012 | ~$200 | ~2h | Day-to-day development, iterating on changes |
| **Full** (all 11) | All | ~$400 | ~4h | Pre-merge validation, milestone runs |

The quick set covers the key ticket types (kubeflow, model caching, agent deployment, file citations, model registries, model catalogs) while keeping cost manageable for frequent runs.

## Execution flow

```
/eval-run
  → workspace.py     Creates isolated workspace per case
  → execute.py       Runs docs-orchestrator per case (parallelism 3)
  → collect-docs-repo-output.sh  Copies AsciiDoc from docs repo to workspace
  → collect.py       Gathers artifacts into eval/runs/<id>/cases/
  → score.py         Runs judges against collected outputs
  → report.py        Generates HTML report with analysis
```

## Adding test cases

1. Create a directory under `eval/dataset/cases/` following the naming pattern `case-NNN-<ticket-lower>`
2. Add `input.yaml` with the required fields (see existing cases for the schema)
3. Run `bash eval/scripts/pin-docs-repo.sh <case-dir>` to record the docs repo SHA
4. Run `bash eval/scripts/setup-eval-worktrees.sh` to check out the worktree

## Troubleshooting

**Cases timing out**: Increase `execution.timeout` in `eval.yaml`. Complex tickets with many requirements and review cycles can exceed 1 hour.

**LLM judge returns low scores**: Check that `collect-docs-repo-output.sh` ran between execution and collection. Without it, the judge doesn't see the AsciiDoc output.

**`google.auth` import error**: Install `google-auth`: `pip3 install --break-system-packages google-auth`

**`jinja2` import error**: Install `jinja2`: `pip3 install --break-system-packages jinja2`
