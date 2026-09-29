# Chapter 5 Design: Context Planner

The implemented lab adds `policyops.context`, a deterministic planner that sits
between the answer service and the Chapter 4 inference gateway. It plans before
rendering: source summaries are inspected, unsafe or irrelevant items are
excluded, selected items are lazily materialized, current-call state is compacted,
and the final model context is rendered with stable-prefix and full-context
fingerprints.

## Implemented components

- Versioned schemas for context requests, items, summaries, plans, manifests,
  compaction results, and rendered context.
- Fixture source adapters for policy, project instructions, verified evidence,
  current-call state, capability metadata, and image/table observations.
- Authority ceilings by source kind so text cannot self-promote into policy.
- Frozen tokenizer fixture and deterministic budget checks.
- Lazy materialization, compaction, stable-prefix ordering, structured answer
  schema binding, redacted manifests, token reports, and fault drills.

## Verification

```powershell
uv run ruff check src/policyops/context tests/context
uv run policyops verify ch05 --profile fixture --junit build/ch05/junit.xml --evidence build/ch05
uv run policyops fault ch05 --scenario all
```

The fixture profile proves context-planning behavior and safety gates. It does
not implement production retrieval, long-term memory, MCP/tool discovery, or
durable execution, which are owned by later chapters.
