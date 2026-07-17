# Chapter 6 PRD: Build a Citation-First Hybrid RAG Service

This project implements the hands-on work for Chapter 6, **Advanced and Agentic RAG Patterns**. It extends the context planning and evaluation contracts established in [Chapter 5](../ch05-context-planner/prd.md) and produces the permission-aware `EvidencePack` consumed by [Chapter 7](../ch07-graph-retrieval/prd.md) and the final PolicyOps application. See the [architecture](./architecture.md).

## Problem

A naive vector-search demo can return plausible text while losing document structure, using stale versions, crossing tenant boundaries, or citing the wrong passage. PolicyOps needs a reproducible retrieval service that ingests structured and scanned policy material, combines lexical and semantic evidence, applies authorization before ranking, and either returns claim-ready citations or explicitly abstains. It must also prove that source updates and deletions reach the serving index.

## Goals

- Preserve source identity, version, headings, tables, OCR coordinates, permissions, and timestamps through ingestion and retrieval.
- Combine PostgreSQL full-text and vector search, then rerank and deduplicate results into a bounded `EvidencePack`.
- Resolve every citation to an exact source version and span.
- Enforce tenant and document authorization before any candidate can influence scores or model context.
- Support incremental replacement and deletion with measurable freshness.
- Evaluate retrieval separately from answer grounding using a credential-free fixture profile.

## Non-goals

- An open-ended autonomous search agent; the core permits only one bounded classification, decomposition, or reformulation attempt.
- Graph indexing and graph traversal, which Chapter 7 owns.
- Persistent user memory, orchestration, or model-provider optimization.
- A general document-management UI or production OCR pipeline; supplied OCR and page-coordinate fixtures are sufficient.

## Users

- **AI engineer:** integrates a stable evidence contract into an LLM application.
- **Knowledge operator:** ingests, supersedes, and deletes controlled documents.
- **Security engineer:** verifies authorization, provenance, and deletion behavior.
- **Evaluator:** maintains gold queries and compares retrieval and generation metrics.

## User stories

- As an AI engineer, I can request evidence under a tenant-scoped principal and receive ranked passages with resolvable citations.
- As a knowledge operator, I can replace or delete a source and obtain a receipt showing when the serving index changed.
- As a security engineer, I can prove that a cross-tenant query and a poisoned document cannot leak or override policy.
- As an evaluator, I can replay the same corpus and queries without paid credentials and receive machine-readable scores.

## Functional requirements

- **CH06-FR-001 — Structure-preserving ingestion:** Parse supplied HTML, PDF-derived text, tables, and OCR fixtures into versioned sources, sections, spans, and page regions while retaining hashes, timestamps, and ACL metadata.
- **CH06-FR-002 — Idempotent lifecycle:** An ingestion idempotency key must create one active source version. Replacement atomically activates the new version; deletion tombstones the source and removes searchable chunks.
- **CH06-FR-003 — Hybrid candidate generation:** Execute lexical and vector retrieval with configurable candidate limits and score normalization. The fixture profile uses supplied deterministic vectors and reranker replays.
- **CH06-FR-004 — Authorization-first filtering:** Apply tenant and document predicates inside both candidate queries, before fusion or reranking.
- **CH06-FR-005 — Evidence construction:** Fuse, rerank, deduplicate, and pack candidates under explicit passage and token budgets, retaining per-stage scores and exclusion reasons.
- **CH06-FR-006 — Exact citations:** Return source ID, immutable version ID, span offsets, section path, and page or table coordinates where available. A citation resolver must reproduce the cited text.
- **CH06-FR-007 — Sufficiency and abstention:** Classify evidence as sufficient, conflicting, or insufficient. Insufficient and unresolved-conflict cases return an abstention with reason codes rather than an unsupported answer.
- **CH06-FR-008 — Bounded query transformation:** A typed query classifier may select direct, thematic, multi-hop, visual, action-oriented, or `out_of_scope` handling and perform at most one decomposition or reformulation within call, token, and time budgets.
- **CH06-FR-009 — Scanned and tabular evidence:** At least one gold query must retrieve a supplied scanned page or table and preserve its OCR and coordinate lineage.
- **CH06-FR-010 — Evaluation and evidence:** Produce retrieval metrics, citation and abstention results, latency, cost estimates, freshness receipts, authorization tests, and a versioned index manifest.
- **CH06-FR-011 — Retrieval-stage bulkheads:** Bound lexical search, vector search, reranking, OCR/table processing, and optional embedding concurrency independently; on downstream throttle or saturation, cancel or degrade only through declared sufficiency rules and return a typed partial failure or abstention.

## Non-functional requirements

- **CH06-NFR-001:** The required fixture run is deterministic, repeatable offline after dependency installation, and needs no model or API credential.
- **CH06-NFR-002:** All schemas are typed and versioned; incompatible evidence-contract changes fail CI.
- **CH06-NFR-003:** On the supplied corpus, warm-query p95 retrieval latency must be at most 1.5 seconds on the declared reference hardware.
- **CH06-NFR-004:** Replacement and deletion become visible within a 60-second fixture freshness SLO and produce auditable receipts.
- **CH06-NFR-005:** Service logs and traces must not contain raw document bodies, embeddings, authorization tokens, or model-visible secrets.

## Security and privacy requirements

- **CH06-SEC-001:** Authenticate the caller and derive tenant scope server-side; ignore client attempts to widen the scope.
- **CH06-SEC-002:** Treat document text, metadata, OCR, and retrieved passages as untrusted data, never as system instructions or authority.
- **CH06-SEC-003:** Use parameterized queries and mandatory row predicates; a missing principal or ACL fails closed.
- **CH06-SEC-004:** Deletion removes chunks, vectors, cached evidence, and active manifests while retaining only a minimal non-content audit receipt.
- **CH06-SEC-005:** Record provenance and content hashes for every served span so poisoned or superseded material can be isolated.

## Fixtures and data

`fixtures/policyops-v1` contains two tenants, structured policies, superseded versions, a deleted source, one poisoned passage, tables, and scanned-page OCR with coordinates. `gold_queries.jsonl` labels query class, allowed tenant, relevant spans, expected abstention, and citation targets. Supplied vector and reranker replay files make the core evaluation deterministic. Optional profiles may use a local or hosted `EmbeddingClient` and `Reranker` configured outside the repository; `ModelClient` remains generation-only.

## External behavior

- `POST /v1/ingestion/jobs` accepts a manifest and idempotency key; `GET /v1/ingestion/jobs/{id}` returns state and receipts.
- `DELETE /v1/sources/{source_id}` requires the expected active version and returns a deletion receipt.
- `POST /v1/evidence/query` accepts query, principal context, budgets, and optional correlation ID; it returns an `EvidencePack`, sufficiency decision, or typed abstention.
- `GET /v1/citations/{version_id}/{span_id}` resolves authorized citation text and coordinates.
- `uv run policyops verify ch06 --profile fixture --junit build/ch06/junit.xml --evidence build/ch06` executes the complete gate.

Errors use stable codes such as `AUTH_SCOPE_REQUIRED`, `SOURCE_VERSION_CONFLICT`, `RETRIEVAL_TIMEOUT`, and `EVIDENCE_INSUFFICIENT`; they never fall back to an ungrounded answer.

## Acceptance criteria and traceability

1. Given the gold corpus, when the fixture suite runs, recall@10 is at least 0.85 and nDCG@10 at least 0.75 (`CH06-FR-003`, `CH06-FR-010`).
2. Given every grounded expected claim, each returned citation resolves byte-for-byte to the correct active version and labeled span (`CH06-FR-006`).
3. Given cross-tenant and protected-source queries, no forbidden source ID, text, score, or timing-dependent result appears (`CH06-FR-004`, `CH06-SEC-001`).
4. Given a superseded or deleted source, it disappears within the freshness SLO and a repeat deletion is safe (`CH06-FR-002`, `CH06-NFR-004`).
5. Given poisoned, conflicting, or unanswerable cases, the service abstains or excludes the passage and records a reason (`CH06-FR-007`, `CH06-SEC-002`).
6. Given a retrieval timeout, the request returns a typed partial-failure or abstention and never silently generates (`CH06-FR-011`).
7. Given the scanned-page and table queries, citations include exact page-region or table-cell lineage (`CH06-FR-009`).
8. Given mixed source fixtures and a fixed context budget, ingestion preserves structure, version, ACL, and coordinate lineage, and the resulting evidence pack records included/excluded candidates plus per-stage scores without exceeding its passage or token limit (`CH06-FR-001`, `CH06-FR-005`).
9. Given the Chapter 5 planner, the evidence adapter passes the shared `ContextSource` contract suite, exposes only authorized summaries, lazily materializes selected items, and preserves authority, trust, provenance, tenant, sensitivity, freshness, placement, and token-budget metadata (`CH06-FR-004`, `CH06-FR-005`, `CH06-NFR-002`).
10. Given a saturated or throttled retrieval stage, its bulkhead stays within the configured bound, unrelated stages remain available, retry behavior stays inside the original deadline, and the response is sufficient under an explicit degraded rule or a typed abstention (`CH06-FR-011`).

## Success metrics

Required metrics are recall@k, nDCG@k, evidence sufficiency accuracy, citation precision and resolution rate, abstention precision/recall, authorization violations, freshness lag, p50/p95 latency, and estimated per-query cost. The release gate requires zero authorization or citation-version failures and 100% expected abstention on the supplied unsafe cases.

## Prerequisites and dependencies

Use Python 3.12+, `uv`, FastAPI, Pydantic, pytest, OpenTelemetry, a pinned PostgreSQL image with full-text search and pgvector, migrations, and Docker Compose. Consume Chapter 5's query/context budget types. Pin exact dependency and fixture hashes at implementation kickoff. Redis is not required for this lab.

## Risks and mitigations

- **Score fusion hides weak retrieval:** report lexical, vector, fusion, and reranker metrics separately.
- **ACL applied too late:** enforce it in repository queries and test absence from intermediate traces.
- **Citation offsets drift after parsing:** address spans by immutable version and normalized-content hash.
- **Deletion races with queries:** use transactional manifest activation and version checks.
- **Fixture overfitting:** retain a hidden query split and compare optional local-model runs.
- **One retrieval stage exhausts the service:** isolate stage concurrency, propagate cancellation and deadlines, and defer fleet admission, tenant fairness, service-entry `429`, and provider quota operations to Chapter 14.

## Delivery milestones

1. Define schemas, migrations, fixture loader, and index manifest.
2. Implement lexical/vector retrieval, tenant filters, fusion, and deterministic reranking.
3. Add EvidencePack budgeting, citation resolution, sufficiency, and abstention.
4. Implement replacement/deletion lifecycle and scanned/table cases.
5. Add retrieval-stage bulkheads, throttle/timeout drills, telemetry, evaluation scorecard, CI gate, and capstone evidence registration.

## Future extensions

After Chapters 10 and 11 establish orchestration and durable loop controls, add bounded multi-step decomposition and one evidence-driven reformulation. The core direct path and its evaluation baseline must remain available for comparison.

## Lab delivery contract

- **Starter:** `ed2-v1.0-ch06-start`, supplied ingestion scaffold, and PostgreSQL full-text plus vector indexes.
- **Task:** preserve structure and versions; add hybrid retrieval, reranking, exact-span citations, sufficiency checks, tenant filtering, incremental update, deletion, abstention, and one scanned-page or table query.
- **Drill:** poisoned document, cross-tenant query, superseded policy, deleted source, and retrieval timeout.
- **Artifact:** ingestion job, migrations, index manifest, RAG API, gold queries, authorization tests, freshness report, and scorecard.
- **Acceptance:** declared recall/nDCG gates, correct versioned spans, no tenant crossing, deletion within SLO, and abstention for unanswerable cases.
- **Verify:** `uv run policyops verify ch06 --profile fixture --junit build/ch06/junit.xml --evidence build/ch06`.
- **Handoff:** create `work/ch06`, compare it with `ed2-v1.0-ch06-solution`, and register ingestion, index, retrieval, citation, authorization, freshness, deletion, context-adapter tests, and bounded-state-machine evidence in `capstone/traceability.yaml`; Chapter 7 evaluates graph routing.
- **Execution:** 4–6 hours with pinned PostgreSQL, migrations, supplied vectors/reranker replays, structured and scanned fixtures; no paid credential.
- **Repository/CI:** `labs/ch06/manifest.toml`, base tag `ed2-v1.0-ch06-start`, and primary paths `src/policyops/retrieval`, `db/migrations`, `fixtures/policyops-v1`, `tests/retrieval`, and `tests/integration`; `verify-ch06` runs this and all earlier gates.
- **Run/cleanup:** `uv sync --frozen`; `uv run policyops env up --lab ch06 --profile fixture`; `uv run policyops verify ch06 --profile fixture --junit build/ch06/junit.xml --evidence build/ch06`; `uv run policyops fault ch06 --scenario all`; `uv run policyops env down --lab ch06`.
- **Proposal:** ingest the supplied policy collection and expose a working PolicyOps answer-evidence endpoint with hybrid retrieval, access filtering, exact citations, freshness handling, and abstention.
