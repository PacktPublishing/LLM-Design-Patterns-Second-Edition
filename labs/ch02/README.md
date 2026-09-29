# Chapter 2 — Evaluation-Driven Development Suite

Offline evaluation runner for PolicyOps: versioned cases, deterministic graders, failure adjudication, and cost-per-successful-outcome evidence.

## GitHub evidence

- Source implementation: [src/policyops/eval](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/src/policyops/eval)
- Primary tests: [tests/eval/test_eval.py](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/tests/eval/test_eval.py)
- Recorded verification evidence: [build/ch02](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/build/ch02) | [junit.xml](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch02/junit.xml) | [result.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch02/result.json) | [scorecard.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch02/scorecard.json)

Specs: [PRD](../../docs/implementation-plans/chapters/ch02-evaluation-driven-development-suite/prd.md) · [Architecture](../../docs/implementation-plans/chapters/ch02-evaluation-driven-development-suite/architecture.md) · [Design](../../docs/implementation-plans/chapters/ch02-evaluation-driven-development-suite/design.md)

## What this code teaches

- Define success/failure **before** changing prompts or models.
- Separate capability, regression, adversarial, and protected-holdout suites.
- Prefer deterministic graders for CI; keep live rubric grading optional.
- Report distributions (pass@k / pass^k) for stochastic cases, not a single lucky score.
- Track cost per successful outcome as a first-class comparison input.
- Adjudicate grader defects and fixture noise separately from candidate failures.

## Prerequisites

Chapter 1 fixture profile working (`labs/ch01`). Python 3.12+, `uv`.

## Run

```bash
uv sync --extra dev
python scripts/generate_ch02_cases.py
uv run policyops env up --lab ch02 --profile fixture
uv run policyops eval run --suite regression --profile fixture
uv run policyops verify ch02 --profile fixture --junit build/ch02/junit.xml --evidence build/ch02
uv run policyops env down --lab ch02
```

## Insights

1. **Broken graders lie.** Integrity checks and adjudication prevent blaming the model for evaluator bugs.
2. **Holdouts stay sealed.** Aggregate hashes only during normal candidate work.
3. **Gaming looks fluent.** Deterministic citation/state checks beat wording-only rubric scores.
4. **Throttle is a gate.** Bounded pools + backoff prevent false release decisions under 429s.
5. **CPSO needs honesty.** If cost is unknown, label it `unavailable` instead of inventing zero.

## Reader questions

1. Which failure class should a flaky fixture timeout receive, and who is allowed to reopen the case?
2. Why keep protected holdouts out of the candidate-writable tree?
3. How would you add a new risk area without silently weakening zero-tolerance gates?
4. When is pass@k misleading without pass^k?
5. What evidence would convince you a rubric grader is calibrated enough for non-blocking experiments but not for PR merge?
