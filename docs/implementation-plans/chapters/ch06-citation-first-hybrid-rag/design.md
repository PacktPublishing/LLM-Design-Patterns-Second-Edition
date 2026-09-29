# Chapter 6 Design: Citation-First Hybrid RAG

The implemented lab adds `policyops.retrieval`, a deterministic hybrid retrieval
service that produces citation-ready evidence packs for PolicyOps. The mandatory
fixture path keeps the production contracts visible without requiring a database,
hosted embedding model, reranker, or external credential.

## Implemented components

- Versioned source, span, citation, candidate, evidence-pack, principal, budget,
  lifecycle-receipt, and scorecard schemas.
- Fixture corpus with two tenants, active and deleted sources, poisoned content,
  structured spans, table-cell lineage, and scanned-page OCR coordinates.
- Authorization-first lexical and vector retrieval, reciprocal-rank fusion,
  deterministic reranking, deduplication, evidence-pack budgeting, sufficiency,
  and typed abstention.
- Citation resolver that requires active source version, tenant authorization,
  and content-hash match.
- Replacement and deletion receipts with fixture freshness SLO evidence.
- `EvidenceContextSource`, which exposes retrieval results through the Chapter 5
  context-source contract.

## Verification

```powershell
uv run ruff check src/policyops/retrieval tests/retrieval
uv run policyops verify ch06 --profile fixture --junit build/ch06/junit.xml --evidence build/ch06
uv run policyops fault ch06 --scenario all
```

The fixture scorecard checks recall, nDCG, citation resolution, abstention,
authorization isolation, deletion visibility, and retrieval timeout behavior.
