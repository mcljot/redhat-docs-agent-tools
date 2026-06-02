# Review: Evaluation & experimentation spec (rev 2)

**Date:** 2026-06-01
**Reviewing:** [Evaluation & Experimentation Spec: Doc Generation Pipeline](https://claude.ai/public/artifacts/e158ed56-c997-4025-91b9-a84d217da419)
**Companion:** [Pipeline eval harness plan](2026-05-31-pipeline-eval-harness-plan.md)

## Summary

The spec is a rigorous evaluation framework for code-grounded documentation quality. It defines 17 metrics across 4 categories, a composite decision rule that prevents gaming, instrument reliability checks, and a paired A/B experiment protocol with statistical controls. The methodology is sound and the Goodhart protections are well-placed.

The main concern is scope relative to current readiness. Several metrics depend on PRD enablement signals (FR-6.1 through FR-6.5) that don't exist yet, and the labelling investment is substantial. The recommendation is to start with the simpler eval-harness approach for immediate directional signal, and build toward this spec incrementally.

## Strengths

### Composite decision rule (Section 5.5)

Requiring accuracy AND coverage AND no false-supported increase before accepting a variant is the strongest design choice. Explicitly rejecting accuracy gains that come with coverage loss prevents the most common gaming pattern in eval setups.

### Instrument reliability metrics (M-R1, M-R2, M-R3)

Measuring the measurement. Judge-human agreement tracking with automatic distrust below threshold catches judge drift before it costs you. Baseline self-consistency checks (M-R3) catch environmental drift. Most LLM-as-judge setups skip this entirely.

### Goodhart protections (Section 9)

Monitoring evidence-source distribution (M-I5) for shifts toward "easily-matched trivia" is a subtle failure mode. Maintaining a human-inspected regression set not tuned against catches overfitting. Periodically reading top- and bottom-scoring outputs catches evasive high-scoring documents.

### LLM-as-judge controls (Section 8)

Position-bias control (randomize order, run both, average), verbosity-bias control, and self-preference warnings are proper methodology that the RFE creator reference implementation doesn't do explicitly.

### Scope discipline (Section 14)

Keeping intent-based evaluation out of scope while acknowledging it exists is the right call. Trying to evaluate business intent and code-grounded accuracy in one framework would muddy both.

## Concerns

### Infrastructure dependencies

Sections 5.1 and 12 depend on PRD FR-6.1 through FR-6.5 (run manifests, grounded-review-on-output, coverage reports, machine-readable verdict logs, pinned input sets). Until those ship, roughly half the metrics are aspirational. The eval-harness approach works with what exists now (merged MRs as ground truth, the orchestrator as-is).

### Labelling investment

50-100 hand-labelled items (Section 6.1), each with correct code evidence (file + symbol), correct verdict, and API-element classification. Estimate 15-30 minutes per item for careful labelling = 25-50 hours before the first eval run. The eval-harness approach starts useful at 10-15 cases with lighter annotations.

### Statistical apparatus vs dataset size

Paired tests, effect sizes, confidence intervals, minimum detectable effect sizing (Section 7.3) are proper methodology but premature at N=15-20 cases. At that sample size, there isn't statistical power for anything subtle. Win/loss/tie from the pairwise judge gives actionable directional signal without the apparatus.

### Metric count

17 metrics across 4 categories is a lot of surface area. In practice, decisions will be based on 3-4 of them (M-E1, M-E2, M-I2, pairwise judge). The rest are diagnostic. Risk: spending more time building metric infrastructure than improving the pipeline.

### N-times sampling cost

Sampling the writer N times per item per variant (Section 7.2) multiplies eval spend by N. At current pipeline costs (~$35-40 per 20-case run), running 3x per variant means ~$200-240 per A/B comparison. Correct in theory, expensive in practice for iterative development.

## How the two approaches relate

These are not competing -- they are different stages of the same journey.

| | Eval harness (step 1) | This spec (step 2) |
|---|---|---|
| Ground truth | Merged MRs (free, already exist) | Hand-labelled code evidence (expensive, higher precision) |
| Primary signal | Pairwise win/loss/tie | Composite decision rule across 5+ metrics |
| Infrastructure needed | eval.yaml + judge prompt | PRD FR-6.1 through FR-6.5, labelling pipeline, statistical tooling |
| Time to first result | Days | Weeks to months |
| Good for | Directional signal during active refactoring | Rigorous gating before release |

## Recommendations

1. **Prioritize the metrics.** Mark M-E1, M-E2, M-I2, and the pairwise judge as P0. Everything else P1 or P2.

2. **Bootstrap the labelled set from eval-harness runs.** Every time the pairwise judge flags an interesting case (a loss or a close tie), have a human label the ground truth. Build the 50-100 set organically rather than in a waterfall.

3. **Add M-R1 (judge-human agreement) early.** Even with the simple eval harness, scoring 5 cases yourself alongside the judge gives a sanity check on judge prompt calibration.

4. **Defer N-times sampling until gating a release.** Single runs with the pairwise judge give enough signal for iterative improvement.

5. **Ship the eval-harness approach first.** Get directional signal during the current pipeline refactor. Layer in the intrinsic metrics as PRD enablement signals land. Add statistical controls once the dataset is large enough for them to matter.
