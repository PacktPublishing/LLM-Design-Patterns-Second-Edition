# Chapter 7 PRD: Add Graph Retrieval for Multi-Hop Questions

This project implements the hands-on work for Chapter 7, **Graph RAG and Knowledge Integration Patterns**. It adds a measured graph route beside the [Chapter 6 hybrid retriever](../ch06-citation-first-hybrid-rag/prd.md), not in place of it, and emits source-linked evidence that later orchestration can consume. See the [architecture](./architecture.md).

## Problem

Hybrid passage retrieval works well for local facts but can miss questions whose answer depends on relationships, effective dates, corpus-wide patterns, or several source hops. A graph can help, but only if extraction lineage, tenant isolation, incremental repair, and operating cost are explicit. PolicyOps needs a router that sends only graph-suitable queries to a source-linked graph and can demonstrate whether that added system earns its cost.

## Goals

- Load a supplied, versioned graph snapshot of entities, relationships, events, and claims with immutable source spans.
- Support local neighborhood, bounded multi-hop, temporal, and corpus-level query routes.
- Combine graph candidates with Chapter 6 evidence without losing provenance or authorization.
- Retain contradictory claims and effective dates rather than silently collapsing them.
- Apply corrections, supersession, and deletion through an atomic incremental updater.
- Produce a graph-versus-standard-RAG decision record based on quality, latency, total cost, and cost per successful answer by query class.

## Non-goals

- Live model-based extraction in the core lab; extraction regeneration is an optional extension.
- Replacing Chapter 6 retrieval for simple factual queries.
- Persistent conversational memory, user profiling, or graph-derived authority.
- An external graph database or unbounded traversal.
- General ontology management tooling.

## Users

- **AI engineer:** adds relational retrieval behind the common evidence contract.
- **Knowledge engineer:** maintains schema, aliases, temporal claims, and repairs.
- **Security engineer:** validates tenant filtering and provenance through traversal.
- **Product/evaluation owner:** decides whether graph indexing produces measurable value.

## User stories

- As an AI engineer, I can ask a multi-hop policy question and receive the traversed claim chain with exact source citations.
- As a knowledge engineer, I can correct, supersede, or delete one source claim and atomically publish a repaired snapshot.
- As a security engineer, I can prove that traversal never crosses into a tenant or source the principal cannot access.
- As an evaluation owner, I can compare graph, Chapter 6, and hybrid routes by query class and record a justified no-graph decision if gains are absent.

## Functional requirements

- **CH07-FR-001 — Versioned graph snapshot:** Load typed entities, aliases, relationships, events, claims, communities, and source links from a hash-verified snapshot into the local adapter.
- **CH07-FR-002 — Provenance-complete records:** Every graph node or edge used for answering must reference source ID, immutable version, span, extraction version, confidence, tenant, and effective time where applicable.
- **CH07-FR-003 — Entity resolution:** Resolve aliases to canonical entity IDs while preserving merge evidence and permitting an ambiguous state instead of an unsafe merge.
- **CH07-FR-004 — Query classification:** Route queries among `standard_rag`, `local_graph`, `multi_hop_graph`, `temporal_graph`, `global_graph`, or `hybrid_graph_vector` using typed labels and declared limits. A `drift_graph` analytical route is optional and cannot become a required serving dependency without its own measured ADR.
- **CH07-FR-005 — Bounded traversal:** Enforce maximum hops, candidate fan-out, elapsed time, and allowed relation types; return an explicit partial or abstention when a budget is exhausted.
- **CH07-FR-006 — Temporal and contradictory claims:** Filter by effective date when requested, surface competing claims with provenance, and prohibit recency alone from silently overriding authoritative sources.
- **CH07-FR-007 — Evidence projection:** Convert a traversal result into the Chapter 6 `EvidencePack` shape plus a graph path that explains relationships without treating graph summaries as uncited facts.
- **CH07-FR-008 — Incremental repair:** Apply source correction, supersession, and deletion to a staged snapshot, validate affected lineage, and atomically swap the active snapshot.
- **CH07-FR-009 — Isolation:** Enforce tenant and document authorization during seed selection and every traversal expansion.
- **CH07-FR-010 — Comparative evaluation:** Report quality by query class, route-confusion matrix, indexing time/storage, query latency, token use, and graph-versus-RAG outcome.

## Non-functional requirements

- **CH07-NFR-001:** The required fixture profile uses a persisted NetworkX/SQLite adapter, supplied snapshot, and no external graph service or paid credential.
- **CH07-NFR-002:** Replaying the same snapshot, queries, and configuration produces the same routes, paths, and metrics.
- **CH07-NFR-003:** The router adds no more than 50 ms p95 overhead on the reference fixture hardware; graph query p95 is at most 1.5 seconds under declared traversal limits.
- **CH07-NFR-004:** Snapshot publication is atomic and rollback to the prior verified snapshot takes one administrative operation.
- **CH07-NFR-005:** Schemas and evidence projections are versioned and checked against the Chapter 6 contract in CI.

## Security and privacy requirements

- **CH07-SEC-001:** Trusted tenant scope is derived from authenticated context and included in every graph lookup; no unrestricted traversal API is exposed.
- **CH07-SEC-002:** A path is servable only when each source-backed claim in it is authorized; summaries cannot launder a forbidden source.
- **CH07-SEC-003:** Snapshot hashes, extraction versions, and lineage are verified before activation; invalid or tampered snapshots fail closed.
- **CH07-SEC-004:** Deleted claims and their derived summaries are absent from the active snapshot and query caches, with content-free repair receipts retained.
- **CH07-SEC-005:** Graph text, labels, and community summaries are untrusted evidence and cannot grant tool, memory, or workflow authority.

## Fixtures and data

The fixture contains two tenants, entities with aliases, effective-dated relationships, events, contradictory claims, community assignments, and source links into the Chapter 6 corpus. Query labels distinguish local, multi-hop, temporal, global, and ordinary retrieval cases. Repair fixtures correct one claim, supersede another, and delete a third. An optional extraction profile may regenerate the graph through a provider-neutral `ModelClient`, but comparison always uses the supplied snapshot as the reproducible baseline.

## External behavior

- `POST /v1/graph/query` accepts query, principal, as-of time, route limits, and correlation ID; it returns route, graph paths, projected evidence, and typed warnings.
- `POST /v1/graph/snapshots` stages a snapshot and returns validation results; `POST /v1/graph/snapshots/{id}/activate` performs a version-checked atomic swap.
- `POST /v1/graph/repairs` accepts source lifecycle events and emits affected-record counts and a repair receipt.
- `GET /v1/graph/paths/{query_id}` returns an authorized, redacted explanation of a prior path.
- `uv run policyops verify ch07 --profile fixture --junit build/ch07/junit.xml --evidence build/ch07` runs evaluation and fault drills.

## Acceptance criteria and traceability

1. Given any returned graph record or answer claim, its complete lineage resolves to authorized source text (`CH07-FR-002`, `CH07-FR-007`).
2. Given a cross-tenant seed or an authorized seed adjacent to a forbidden node, traversal reveals no forbidden identifier, summary, or fact (`CH07-FR-009`, `CH07-SEC-001`, `CH07-SEC-002`).
3. Given temporal contradictions, both valid claims retain dates and provenance and the result reports the unresolved conflict (`CH07-FR-006`).
4. Given correction, supersession, and deletion events, a validated snapshot swaps atomically and unrelated graph regions remain byte-identical (`CH07-FR-008`, `CH07-NFR-004`).
5. On graph-suitable gold queries, the graph or hybrid route improves exact task success by at least 15 percentage points over Chapter 6 alone without routing ordinary queries to the graph. If it does not, a measured no-graph ADR is the accepted outcome (`CH07-FR-010`).
6. Given invalid schema, missing lineage, or a tampered hash, activation fails and the prior snapshot remains active (`CH07-SEC-003`).
7. Given the supplied snapshot and labeled query set, loading preserves every typed record and source link, ambiguous aliases remain unresolved rather than incorrectly merged, the typed router selects the declared route, and traversal stops at its hop/fan-out/time limits with a partial result or abstention (`CH07-FR-001`, `CH07-FR-003`, `CH07-FR-004`, `CH07-FR-005`).

## Success metrics

Report task success and evidence recall by query class, path precision, lineage completeness, temporal/contradiction accuracy, router precision/recall, tenant violations, repair correctness, snapshot downtime, index time and size, p50/p95 latency, and token/cost estimates. The hard gates are zero unauthorized traversal, 100% lineage resolution for served claims, and atomic repair with no unrelated contamination.

## Prerequisites and dependencies

Use Python 3.12+, `uv`, FastAPI, Pydantic, pytest, OpenTelemetry, Docker Compose, the Chapter 6 source/version and `EvidencePack` contracts, a supplied graph snapshot, and a persisted NetworkX/SQLite adapter. PostgreSQL remains available for source authorization; no external graph service or Redis is required. Lock exact dependencies and snapshot hashes at implementation kickoff.

## Risks and mitigations

- **Graph cost without quality gain:** gate adoption by query class and preserve a no-graph outcome.
- **Entity over-merging:** retain ambiguous aliases and require evidence for canonical merges.
- **Provenance lost in summaries:** summaries store the union of underlying claim IDs and are never independently citable.
- **ACL leaks through topology:** filter every expansion and redact counts that could expose forbidden neighbors.
- **Repair blast radius:** compute and validate an affected subgraph before atomic publication.

## Delivery milestones

1. Define graph schema, adapter, snapshot manifest, and source-link validator.
2. Implement entity resolution and local, multi-hop, temporal, and corpus routes.
3. Add Chapter 6 evidence projection, authorization, router, and traversal budgets.
4. Implement staged incremental repair, validation, atomic swap, and rollback.
5. Add comparative evaluation, fault drills, telemetry, ADR, and capstone evidence registration.

## Future extensions

Regenerate the extraction snapshot with an optional local or hosted model and compare extraction precision, lineage, cost, and repair behavior with the supplied version. A production graph database may replace the adapter only after passing the same contracts and tenant tests.

## Lab delivery contract

- **Starter:** `ed2-v1.0-ch07-start` with source-linked extraction snapshot and local property-graph schema.
- **Task:** load entity, relationship, event, and claim fixtures; implement local, multi-hop, and corpus routes; handle dates and contradictions; compare with Chapter 6.
- **Drill:** correct one source claim, supersede another, delete a third, and prove unrelated regions remain uncontaminated.
- **Artifact:** versioned snapshot, schema, lineage records, incremental updater, query router, cost report, and graph-versus-RAG ADR.
- **Acceptance:** source traceability, tenant filtering, atomic swap, contradiction provenance, and measured graph gain—or a justified no-graph ADR.
- **Verify:** `uv run policyops verify ch07 --profile fixture --junit build/ch07/junit.xml --evidence build/ch07`.
- **Handoff:** create `work/ch07`, compare it with `ed2-v1.0-ch07-solution`, and register snapshot, lineage, updater, router, cost report, repair tests, and ADR in `capstone/traceability.yaml`; Chapter 8 adds managed memory.
- **Execution:** 3–4 hours using the Chapter 6 solution, supplied snapshot, and NetworkX/SQLite; no external graph or paid credential.
- **Repository/CI:** `labs/ch07/manifest.toml`, base tag `ed2-v1.0-ch07-start`, and `src/policyops/graph`, `fixtures/graph`, `tests/graph`, `docs/adrs`; `verify-ch07` runs all earlier gates.
- **Run/cleanup:** `uv sync --frozen`; `uv run policyops env up --lab ch07 --profile fixture`; `uv run policyops verify ch07 --profile fixture --junit build/ch07/junit.xml --evidence build/ch07`; `uv run policyops fault ch07 --scenario all`; `uv run policyops env down --lab ch07`.
- **Proposal:** route suitable temporal and multi-hop questions through a supplied source-linked graph and compare them with the standard Chapter 6 path.
