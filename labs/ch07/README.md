# Chapter 7 Lab: Graph Retrieval

This lab adds a source-linked graph route beside the Chapter 6 hybrid retriever.
It demonstrates typed query routing, alias resolution, bounded traversal,
temporal contradiction handling, evidence projection, tenant isolation, and
copy-on-write snapshot repair.

Run it with:

```powershell
uv run policyops verify ch07 --profile fixture --junit build/ch07/junit.xml --evidence build/ch07
uv run policyops fault ch07 --scenario all
```

The mandatory fixture profile is deterministic and offline. It does not require
an external graph database or hosted extraction model.

## GitHub evidence

- Source implementation: [src/policyops/graph](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/src/policyops/graph)
- Primary tests: [tests/graph/test_graph_retrieval.py](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/tests/graph/test_graph_retrieval.py)
- Recorded verification evidence: [build/ch07](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/build/ch07) | [junit.xml](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch07/junit.xml) | [result.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch07/result.json) | [scorecard.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch07/scorecard.json)

Specs: [PRD](../../docs/implementation-plans/chapters/ch07-graph-retrieval/prd.md) · [Architecture](../../docs/implementation-plans/chapters/ch07-graph-retrieval/architecture.md) · [Design](../../docs/implementation-plans/chapters/ch07-graph-retrieval/design.md)
