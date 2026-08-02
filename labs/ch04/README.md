# Chapter 4 Lab: Adaptive Inference Gateway

This lab implements a fixture-runnable inference gateway for PolicyOps. It allocates
test-time compute by request risk, verifies candidates deterministically, escalates
from small to stronger profiles only when needed, enforces spend/time/candidate
budgets, and uses a tenant-safe response cache.

Run it with:

```powershell
uv run policyops verify ch04 --profile fixture --junit build/ch04/junit.xml --evidence build/ch04
uv run policyops fault ch04 --scenario all
```

Evidence is written under `build/ch04/`, including raw benchmark rows, an inference
report, a serving ADR, fingerprints, JUnit, and the standard redacted trace sample.
Fixture latency and spend are learning evidence, not hosted-provider performance
claims.

## GitHub evidence

- Source implementation: [src/policyops/inference](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/src/policyops/inference)
- Primary tests: [tests/inference](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/tests/inference)
- Recorded verification evidence: [build/ch04](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/build/ch04) | [junit.xml](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch04/junit.xml) | [result.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch04/result.json) | [scorecard.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch04/scorecard.json)

