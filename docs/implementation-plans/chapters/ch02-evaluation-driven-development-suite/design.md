# Chapter 2 Design: Evaluation-Driven Development Suite

**Sources:** [PRD](./prd.md) · [Architecture](./architecture.md)
**Upstream:** Chapter 1 contracts + answer/API boundary
**Status:** Implemented and fixture-verified (`policyops verify ch02` passed)
**Profile:** `fixture` (deterministic graders + frozen rubric replay)

## Design summary

Add an offline evaluation runner that loads versioned cases/manifests, invokes PolicyOps through the Chapter 1 candidate port, grades with deterministic graders (plus optional frozen rubric replay), adjudicates failures, and emits immutable evidence including cost-per-successful-outcome inputs. Mandatory CI gates never depend on live hosted graders.

## Design review findings

| ID | Finding | Severity | Resolution |
|---|---|---|---|
| DR-01 | Broken graders must not blame the candidate | High | Reference verifier + grader integrity checks before release-blocking scoring; grader errors adjudicated separately |
| DR-02 | Holdouts must stay immutable in candidate workflows | High | `evals/holdouts/hashes.lock.json` + `verify_holdout_integrity()` fails closed on drift; suite=`all` excludes holdouts |
| DR-03 | Cost/latency missing → silent zeros | Medium | Explicit `unavailable` labels when usage/cost absent |
| DR-04 | Throttle/retry storms | High | Bounded candidate/grader pools, exponential backoff+jitter, resumable trial IDs (fixture 429 replay) |
| DR-05 | Gaming via wording-only answers | High | Deterministic citation/state graders override rubric wording |
| DR-06 | Stochastic noise in PR CI | Medium | `trials: 3` only for marked cases; live rubric outside mandatory PR gates |
| DR-07 | Case count below 30 | High | Ship 20 seed + ≥10 added cases covering six risk areas |

## Module layout

```text
src/policyops/eval/
  schemas.py          # TaskCase, Trial, GraderResult, Outcome, SuiteManifest
  candidate.py        # Candidate port wrapping AnswerService / replay
  graders/            # schema, citation, authorization, tool_args, abstention
  runner.py           # schedule, grade, adjudicate, metrics, evidence
  throttle.py         # bounded pools + backoff
labs/ch02/README.md
evals/cases/{capability,regression,adversarial}/
evals/holdouts/
evals/labels/
evals/graders/
tests/eval/
```

## CLI

```text
uv run policyops eval run --suite regression --profile fixture
uv run policyops eval compare --baseline ch01 --candidate work/ch02
uv run policyops verify ch02 --profile fixture --junit build/ch02/junit.xml --evidence build/ch02
```

## Verification gates

1. Schema round-trips + immutable hashes
2. ≥30 cases, six risk areas, suite partitions
3. Deterministic graders identical across two runs
4. Authz/citation/schema/tool regressions block
5. Gaming candidate fails deterministic checks
6. Throttle fixture: no unbounded retries / duplicate trials
7. Evidence includes CPSO inputs or explicit unavailable

## Handoff

Chapter 3 consumes suite manifests and CPSO comparisons for adapt-or-not decisions; Chapter 12 later owns online telemetry.
