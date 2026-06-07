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

### 2. Extract reference files (first time only)

Gold-standard AsciiDoc files are extracted from merged GitLab MRs on demand:

```bash
bash eval/scripts/extract-gold-standard.sh
```

This populates `reference/` directories for 8 cases that have human-written gold standards. The files are not committed to the repo.

### 3. Run the eval

**Quick run (6 gold-standard cases, ~2 hours, ~$200):**

```bash
/eval-run --model claude-opus-4-6 --cases case-001-rhoaieng-45969 case-002-rhaistrat-853 case-004-rhaistrat-1393 case-008-rhai-eng-2620 case-011-rhoaieng-16840 case-012-rhoaieng-40664
```

**Full run (all 11 cases, ~4 hours, ~$400):**

```bash
/eval-run --model claude-opus-4-6
```

The quick run uses 6 gold-standard cases that cover the key ticket types. Use the full run for milestone validations (pre-merge, release candidates).

### 4. Review results

The report is at `eval/runs/<run-id>/report.html`. Key files:

- `summary.yaml` — per-case scores and aggregate metrics
- `analysis.md` — automated analysis with recommendations
- `run_result.json` — execution metadata (cost, duration, tokens)
- `cases/<case-id>/` — per-case artifacts and outputs

## What the judges measure

| Judge | Type | What it measures | Scale |
|-------|------|-----------------|-------|
| `doc_quality` | LLM | Standalone documentation quality — accuracy, completeness, structure, absence of fabrication | 1-5 (1=unusable, 3=acceptable, 5=production-ready) |
| `reference_comparison` | code+LLM | How closely pipeline output matches human-written gold-standard documentation | 1-5 (1=no match, 3=similar with gaps, 5=equivalent to human) |
| `files_exist` | check | Pipeline produced at least one AsciiDoc file | pass/fail |
| `step_results_valid` | check | Requirements, planning, and writing steps completed with valid metadata | pass/fail |
| `pipeline_complete` | check | Workflow finished all steps | pass/fail |
| `pairwise` | LLM | Head-to-head comparison of two runs' output for the same case | A wins / B wins / tie |

**Note**: `reference_comparison` only scores cases with human-written gold-standard references (8 of 11 cases). Cases 002, 004, 005 are pipeline-generated and are skipped.

## Managing baselines

The baseline is your reference point for measuring improvements and regressions. It represents the known-good state of the pipeline on `main`.

### When to create a new baseline

- **After merging a significant change** (new pipeline step, architectural change, model upgrade)
- **NOT for small changes** (prompt tuning, threshold adjustments — compare against the existing baseline)

### Creating a baseline

Run a full eval on `main` after the change has merged:

```bash
git checkout main
git pull
bash eval/scripts/setup-eval-worktrees.sh
bash eval/scripts/extract-gold-standard.sh
/eval-run --model claude-opus-4-6 --run-id baseline-v2
```

### Comparing a branch against the baseline

```bash
# 1. Create a throwaway branch with the eval harness + your changes
git checkout your-feature-branch
git checkout -b test/eval-your-feature
git merge feat/eval-harness-setup

# 2. Reset worktrees (previous runs modified them)
bash eval/scripts/setup-eval-worktrees.sh

# 3. Run with baseline comparison
/eval-run --model claude-opus-4-6 --baseline baseline-v2
```

For quick iteration during development (6 cases, ~$200):

```bash
/eval-run --model claude-opus-4-6 --baseline baseline-v2 --cases case-001-rhoaieng-45969 case-002-rhaistrat-853 case-004-rhaistrat-1393 case-008-rhai-eng-2620 case-011-rhoaieng-16840 case-012-rhoaieng-40664
```

### Interpreting the comparison

The report includes:

- **Judge scores** — side-by-side aggregate scores for each judge
- **Pairwise comparison** — per-case A wins / B wins / tie showing which run produced better docs
- **Cost attribution** — whether cost changes come from pipeline changes or model variance
- **Regressions** — any scores that dropped below configured thresholds

### Baseline lifecycle

```
baseline-v1 (initial main)
  ↑ compare code-learner branch → merge
baseline-v2 (main + code-learner)    ← active baseline
  ↑ compare future branches against this
baseline-v3 (main + next big change) ← after next major merge
```

Old baselines stay in `eval/runs/` for historical reference but aren't used for active comparison. Only compare against the most recent baseline that represents `main`.

### Naming convention

- `baseline-v1`, `baseline-v2`, etc. — milestone baselines on main
- `<feature-name>` — feature branch runs (e.g., `code-learner-port`)
- `YYYY-MM-DD-<model>` — auto-generated IDs for ad-hoc runs

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

11 test cases from gold-standard MRs authored by experienced tech writers (chtyler, stmccart, mmortari). Each case has:

- `input.yaml` — JIRA ticket ID, source repo URL + SHA, docs repo URL + SHA
- `.docs-worktree/` — docs repo checked out at the pinned SHA (created by setup script)
- `reference/` — human-written gold-standard AsciiDoc (extracted on demand, not committed)

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
5. If the case has a gold-standard MR, add it to `eval/scripts/extract-gold-standard.sh`

## Troubleshooting

**Cases timing out**: Increase `execution.timeout` in `eval.yaml`. Complex tickets with many requirements and review cycles can exceed 1 hour.

**LLM judge returns low scores**: Check that `collect-docs-repo-output.sh` ran between execution and collection. Without it, the judge doesn't see the AsciiDoc output.

**reference_comparison returns null**: Run `bash eval/scripts/extract-gold-standard.sh` to populate the reference files. Cases without a `reference/` directory are skipped.

**`google.auth` import error**: Install `google-auth`: `pip3 install --break-system-packages google-auth`

**`jinja2` import error**: Install `jinja2`: `pip3 install --break-system-packages jinja2`
