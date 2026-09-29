# Chapter 7 Design: Graph Retrieval

The implemented lab adds `policyops.graph`, a fixture graph retrieval module that
routes graph-suitable queries beside the Chapter 6 retriever. The graph remains a
derived index: every served claim must project back to Chapter 6 citation-ready
evidence.

## Implemented components

- Typed schemas for entities, claims, graph paths, graph queries, snapshot
  manifests, repair receipts, and comparative scorecards.
- Fixture graph snapshot with aliases, tenant partitions, effective-dated claims,
  contradictions, communities, and source links into Chapter 6 spans.
- Query router for standard RAG, local graph, multi-hop graph, temporal graph,
  global graph, and hybrid graph/vector routes.
- Bounded traversal, temporal filtering, contradiction preservation, tenant
  filtering, evidence projection, timeout partials, and graph-versus-RAG ADR.
- Copy-on-write repair with atomic snapshot activation and unrelated-region hash
  checks.

## Verification

```powershell
uv run ruff check src/policyops/graph tests/graph
uv run policyops verify ch07 --profile fixture --junit build/ch07/junit.xml --evidence build/ch07
uv run policyops fault ch07 --scenario all
```

The fixture gate checks route correctness, lineage resolution, tenant isolation,
temporal contradiction handling, repair correctness, and bounded timeout behavior.
