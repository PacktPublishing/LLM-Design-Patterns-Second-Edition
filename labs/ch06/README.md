# Chapter 6 Lab: Citation-First Hybrid RAG

This lab implements a deterministic, fixture-runnable hybrid retrieval service.
It models versioned source ingestion, authorization-first candidate generation,
lexical/vector fusion, replay reranking, exact citation resolution, evidence-pack
budgeting, deletion/replacement receipts, scanned/table lineage, poison exclusion,
and typed abstention.

Run it with:

```powershell
uv run policyops verify ch06 --profile fixture --junit build/ch06/junit.xml --evidence build/ch06
uv run policyops fault ch06 --scenario all
```

The mandatory profile runs offline. It does not require a hosted embedding model,
reranker, PostgreSQL instance, or vector database, but the code keeps the same
contracts that a production-backed implementation would need to preserve.

## GitHub evidence

- Source implementation: [src/policyops/retrieval](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/src/policyops/retrieval)
- Primary tests: [tests/retrieval/test_hybrid_retrieval.py](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/tests/retrieval/test_hybrid_retrieval.py)
- Recorded verification evidence: [build/ch06](https://github.com/kenhuangus/llm-design-patterns-hands-on/tree/main/build/ch06) | [junit.xml](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch06/junit.xml) | [result.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch06/result.json) | [scorecard.json](https://github.com/kenhuangus/llm-design-patterns-hands-on/blob/main/build/ch06/scorecard.json)

Specs: [PRD](../../docs/implementation-plans/chapters/ch06-citation-first-hybrid-rag/prd.md) · [Architecture](../../docs/implementation-plans/chapters/ch06-citation-first-hybrid-rag/architecture.md) · [Design](../../docs/implementation-plans/chapters/ch06-citation-first-hybrid-rag/design.md)
