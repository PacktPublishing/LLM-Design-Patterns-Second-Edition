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
