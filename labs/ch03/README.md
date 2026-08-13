# Chapter 3 — Choose the Right Adaptation Strategy

Manifest-driven adaptation experiment: provenance-aware data, contamination checks, candidate comparison, and an explicit ship/no-ship decision (including “keep the baseline”).

## GitHub evidence

- Source implementation: [src/policyops/adaptation](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/src/policyops/adaptation)
- Primary tests: [tests/adaptation/test_adaptation.py](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/tests/adaptation/test_adaptation.py)
- Recorded verification evidence: [build/ch03](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/build/ch03) | [junit.xml](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch03/junit.xml) | [result.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch03/result.json) | [scorecard.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch03/scorecard.json)

Specs: [PRD](../../docs/implementation-plans/chapters/ch03-adaptation-strategy/prd.md) · [Architecture](../../docs/implementation-plans/chapters/ch03-adaptation-strategy/architecture.md) · [Design](../../docs/implementation-plans/chapters/ch03-adaptation-strategy/design.md)

## Build steps and deliverables

The chapter's Hands-On section builds this lab in five steps, each producing one of the five
deliverables:

| Step | What it does | Deliverable |
| --- | --- | --- |
| 1. Measure the unchanged baseline from Chapter 2 | `measure_ch02_baseline` replays Chapter 2's locked cases offline and records the result before any candidate is touched | `build/ch03/baseline_report.json` |
| 2. Register candidate data with provenance and rights manifests | `load_records` / `build_dataset_manifest` reject records without rights basis, source, or lineage | `build/ch03/dataset_manifest.json`, `build/ch03/dataset_card.json` |
| 3. Run contamination checks on the protected eval split (checkpoint: clean before any candidate scoring) | `contamination_report` gates the candidate-scoring loop; a contaminated or inadmissible run scores nothing | `build/ch03/contamination_report.json` |
| 4. Evaluate the supplied adapter against the baseline and simpler options | `evaluate_candidates` compares baseline, prompt, retrieval-replay, and adapter candidates against mandatory gates | `build/ch03/candidate_matrix.json`, `build/ch03/comparison_report.json` |
| 5. Produce a decision record with justification and a rollback plan | `evaluate_candidates` picks the smallest eligible candidate (or explicitly retains the baseline) | `build/ch03/release_decision.json` |

## What this code teaches

- Do not fine-tune before measuring a locked baseline.
- Records without rights/provenance never enter the dataset.
- Protected splits must not leak into training (exact, normalized, near-duplicate checks).
- Average quality gains cannot override zero-tolerance safety/cost gates.
- “No adaptation” is a first-class successful decision.

## Run

```bash
uv sync --extra dev
uv run policyops env up --lab ch03 --profile fixture
uv run policyops verify ch03 --profile fixture --junit build/ch03/junit.xml --evidence build/ch03
uv run policyops env down --lab ch03
```

## Insights

1. Contaminated experiments are invalid before any model comparison.
2. Adapter admission (hash, license, base model) is a release control, not paperwork.
3. Prefer the simplest eligible candidate when quality is tied.
4. Injected safety regressions must force rollback to baseline.

## Reader questions

1. When should near-duplicate overlap block training even if exact hashes differ?
2. Why lock thresholds before seeing protected-test scores?
3. What evidence belongs in a dataset card vs a model card for this lab?
4. How do you justify shipping a prompt-only candidate over an adapter with slightly higher quality but higher cost?
5. What residual risks remain even after a clean contamination report?
