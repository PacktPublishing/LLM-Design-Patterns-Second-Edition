# Chapter 15 Lab: Conduct a Governance Release Review

This lab builds the executable governance package for PolicyOps. The release gate checks not just whether controls exist, but whether current accountable humans, signatures, tests, evidence, rights receipts, and approvals make the system releasable.

## GitHub evidence

- Source implementation: [src/policyops/governance](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/src/policyops/governance)
- Primary tests: [tests/governance/test_governance.py](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/tests/governance/test_governance.py)
- Recorded verification evidence: [build/ch15](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/build/ch15) | [junit.xml](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch15/junit.xml) | [result.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch15/result.json) | [scorecard.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch15/scorecard.json)

Specs: [PRD](../../docs/implementation-plans/chapters/ch15-governance-release-review/prd.md) · [Architecture](../../docs/implementation-plans/chapters/ch15-governance-release-review/architecture.md) · [Design](../../docs/implementation-plans/chapters/ch15-governance-release-review/design.md)

## What you build

- A system inventory, risk/autonomy records, owner directory, and approval matrix.
- A control-to-evidence graph tied to prior chapter artifacts.
- A deterministic evidence resolver and release policy engine.
- Correction and deletion receipts covering primary and derived stores.
- A transparency notice generated from the inventory.
- Invalid-evidence drills and a final immutable release decision package.

## Run

```bash
uv run policyops verify ch15 --profile fixture --junit build/ch15/junit.xml --evidence build/ch15
uv run policyops fault ch15 --scenario all
```

## Evidence

The verification command writes:

- `system_inventory.json`
- `risk_autonomy_records.json`
- `ownership_records.json`
- `approval_matrix.json`
- `control_evidence_graph.json`
- `evidence_index.json`
- `rights_receipts.json`
- `transparency_notice.json`
- `invalid_evidence_decisions.json`
- `release_decision.json`
- `governance_scorecard.json`

## Production lesson

Governance is not a checklist stapled to the end of engineering. It is an executable release policy that fails closed when evidence is stale, ownerless, unsigned, tampered, scoped to the wrong configuration, self-approved, or incomplete across user-rights surfaces.
