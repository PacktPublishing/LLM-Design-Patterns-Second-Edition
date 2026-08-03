# LLM Design Patterns, Second Edition: Hands-On Implementation Plans

This package turns the approved book outline into build-ready specifications for the cumulative **PolicyOps** knowledge-and-action agent. It is intentionally separate from the publisher-facing outline. The files define what the implementation must deliver, how its components fit together, and how each chapter proves its result.

The sequence is cumulative. Chapters 1-15 add or validate one bounded capability. Chapter 16 is represented once, in [`chapters/ch16-policyops-capstone/`](./chapters/ch16-policyops-capstone/), and integrates the accepted checkpoints. It does not introduce a new pattern.

The implementation plans mirror the publisher-facing outline after the second review pass. Cost per successful outcome is introduced in Chapter 2, refined in Chapter 4, observed in Chapter 12, and integrated in the Chapter 16 capstone. Multimodal and scanned/OCR-aware retrieval appear in Chapter 6 and the capstone. Chapter 9 owns capability surfaces, including computer-use adapters; Chapter 10 owns browser/computer-use agent behavior through a fixture-based mock approval flow; Chapter 13 validates malicious document and web/tool observations.

## How to use this package

For each project, use the same four-stop path:

- The **PRD** defines users, scope, testable requirements, acceptance gates, risks, and delivery milestones.
- The **architecture** defines boundaries, interfaces, data, runtime flows, failure behavior, deployment, testing, and design decisions.
- The **design** file captures the implementation-facing shape of the fixture lab and its module/file layout.
- The **lab README** points to the current source implementation, the primary test proof, and the recorded verifier evidence.
- Requirement identifiers are stable within a chapter, such as `CH09-FR-003` and `CH09-SEC-002`. The capstone uses `CAP-*` identifiers.
- The fixture profile is the mandatory reference implementation. It must run from a clean checkout without paid credentials. Hosted models, remote protocols, GPUs, Kubernetes, and other integrations are optional profiles whose results cannot weaken the fixture gates.

## Project map

| Chapter | Hands-on project | PRD | Architecture | Design | Lab README | Primary handoff |
|---:|---|---|---|---|---|---|
| 1 | Build the PolicyOps foundation | [PRD](./chapters/ch01-policyops-foundation/prd.md) | [Architecture](./chapters/ch01-policyops-foundation/architecture.md) | [Design](./chapters/ch01-policyops-foundation/design.md) | [Lab README](../labs/ch01/README.md) | Typed service and provider-neutral model boundary |
| 2 | Create an evaluation-driven development suite | [PRD](./chapters/ch02-evaluation-driven-development-suite/prd.md) | [Architecture](./chapters/ch02-evaluation-driven-development-suite/architecture.md) | [Design](./chapters/ch02-evaluation-driven-development-suite/design.md) | [Lab README](../labs/ch02/README.md) | Release gates and failure taxonomy |
| 3 | Choose the right adaptation strategy | [PRD](./chapters/ch03-adaptation-strategy/prd.md) | [Architecture](./chapters/ch03-adaptation-strategy/architecture.md) | [Design](./chapters/ch03-adaptation-strategy/design.md) | [Lab README](../labs/ch03/README.md) | Evidence-backed adapt-or-do-not-adapt decision |
| 4 | Build an adaptive inference gateway | [PRD](./chapters/ch04-adaptive-inference-gateway/prd.md) | [Architecture](./chapters/ch04-adaptive-inference-gateway/architecture.md) | [Design](./chapters/ch04-adaptive-inference-gateway/design.md) | [Lab README](../labs/ch04/README.md) | Bounded routing, verification, and safe caching |
| 5 | Build a context planner | [PRD](./chapters/ch05-context-planner/prd.md) | [Architecture](./chapters/ch05-context-planner/architecture.md) | [Design](./chapters/ch05-context-planner/design.md) | [Lab README](../labs/ch05/README.md) | Authority-ranked, budgeted context assembly |
| 6 | Build a citation-first hybrid RAG service | [PRD](./chapters/ch06-citation-first-hybrid-rag/prd.md) | [Architecture](./chapters/ch06-citation-first-hybrid-rag/architecture.md) | [Design](./chapters/ch06-citation-first-hybrid-rag/design.md) | [Lab README](../labs/ch06/README.md) | Versioned retrieval, exact citations, and abstention |
| 7 | Add graph retrieval for multi-hop questions | [PRD](./chapters/ch07-graph-retrieval/prd.md) | [Architecture](./chapters/ch07-graph-retrieval/architecture.md) | [Design](./chapters/ch07-graph-retrieval/design.md) | [Lab README](../labs/ch07/README.md) | Measured graph route or documented no-use decision |
| 8 | Add governed long-term memory | [PRD](./chapters/ch08-governed-long-term-memory/prd.md) | [Architecture](./chapters/ch08-governed-long-term-memory/architecture.md) | [Design](./chapters/ch08-governed-long-term-memory/design.md) | [Lab README](../labs/ch08/README.md) | Consented, correctable, deletable memory lifecycle |
| 9 | Build a secure PolicyOps extension pack | [PRD](./chapters/ch09-secure-extension-pack/prd.md) | [Architecture](./chapters/ch09-secure-extension-pack/architecture.md) | [Design](./chapters/ch09-secure-extension-pack/design.md) | [Lab README](../labs/ch09/README.md) | Typed tool, MCP, Agent Skill, plugin, hooks, and computer-use adapter boundary |
| 10 | Build a bounded orchestrator-worker flow | [PRD](./chapters/ch10-bounded-orchestrator-worker/prd.md) | [Architecture](./chapters/ch10-bounded-orchestrator-worker/architecture.md) | [Design](./chapters/ch10-bounded-orchestrator-worker/design.md) | [Lab README](../labs/ch10/README.md) | Topology comparison, scoped delegation, and fixture browser/computer-use behavior |
| 11 | Make the agent loop resumable | [PRD](./chapters/ch11-resumable-agent-loop/prd.md) | [Architecture](./chapters/ch11-resumable-agent-loop/architecture.md) | [Design](./chapters/ch11-resumable-agent-loop/design.md) | [Lab README](../labs/ch11/README.md) | Durable effects, replay, checkpoints, and delivery harness |
| 12 | Turn a production trace into a safe improvement | [PRD](./chapters/ch12-trace-to-safe-improvement/prd.md) | [Architecture](./chapters/ch12-trace-to-safe-improvement/architecture.md) | [Design](./chapters/ch12-trace-to-safe-improvement/design.md) | [Lab README](../labs/ch12/README.md) | Trace-to-eval learning with holdout and rollback |
| 13 | Defend against indirect prompt injection | [PRD](./chapters/ch13-prompt-injection-defense/prd.md) | [Architecture](./chapters/ch13-prompt-injection-defense/architecture.md) | [Design](./chapters/ch13-prompt-injection-defense/design.md) | [Lab README](../labs/ch13/README.md) | Containment, policy, and attack evidence |
| 14 | Deploy and recover the PolicyOps service | [PRD](./chapters/ch14-policyops-deployment-recovery/prd.md) | [Architecture](./chapters/ch14-policyops-deployment-recovery/architecture.md) | [Design](./chapters/ch14-policyops-deployment-recovery/design.md) | [Lab README](../labs/ch14/README.md) | Load, failure, rollback, and restore evidence |
| 15 | Conduct a governance release review | [PRD](./chapters/ch15-governance-release-review/prd.md) | [Architecture](./chapters/ch15-governance-release-review/architecture.md) | [Design](./chapters/ch15-governance-release-review/design.md) | [Lab README](../labs/ch15/README.md) | Machine-readable control-to-evidence decision |
| 16 | Integrate and release the PolicyOps agent | [PRD](./chapters/ch16-policyops-capstone/prd.md) | [Architecture](./chapters/ch16-policyops-capstone/architecture.md) | [Design](./chapters/ch16-policyops-capstone/design.md) | [Lab README](../labs/ch16/README.md) | Signed release or no-go evidence bundle |

## Shared implementation contract

The specifications assume a Python 3.12+ repository managed with `uv`, a FastAPI service boundary, Pydantic data contracts, pytest-based verification, OpenTelemetry-compatible signals, and Docker Compose for the mandatory local system profile. PostgreSQL and pgvector are introduced when persistent retrieval, memory, and durable execution require them. Redis or an equivalent cache is optional and must not become a correctness dependency. Exact dependency and image versions are selected, pinned, hashed, and recorded at implementation kickoff.

All model, embedding, reranking, and protocol dependencies sit behind typed ports. Deterministic replay fixtures provide the mandatory path. A local or hosted adapter may be enabled by configuration, but credentials must not be necessary for the core checks and provider-specific types must not cross their adapter boundary.

The repository uses one canonical shared-contract registry. Chapter 1 owns `RunContext`, model request/result, answer, error, and health contracts; Chapter 5 owns `ContextSource`/`ContextItem`; Chapter 6 owns `Citation`/`EvidencePack` plus separate embedding and reranking ports; Chapter 8 owns memory records and lifecycle decisions; Chapter 9 owns `TicketEffect`, `EffectPreview`, `ApprovalClaims`, `ToolPort`, extension/revocation/approval-store ports; Chapter 10 owns topology-neutral task/delegation state; and Chapter 11 owns session events, checkpoints, outbox intents, and effect receipts. Later chapters import these types. A compatible extension must bump its schema version and pass the originating chapter's contract suite; silent renaming or structurally similar duplicate types is not allowed.

Every project follows the same repository contract:

1. A chapter manifest declares fixtures, services, hardware, network access, credentials, commands, cleanup, output artifacts, gates, and injected faults.
2. `uv run policyops verify chNN --profile fixture` is the single chapter verification entry point. It returns non-zero when a mandatory gate fails and writes machine-readable evidence plus JUnit output.
3. Each accepted chapter registers its artifacts, versions, tests, rollback path, and decision in `capstone/traceability.yaml`.
4. Tests distinguish deterministic pull-request gates from hardware-, provider-, or long-running system evidence. Optional evidence is labeled and cannot replace a deterministic gate.
5. Containers run as non-root, secrets remain outside source and model-visible context, tenant and actor identity travel in every request, and mutating actions default to denial without current authorization and approval.

## Cumulative boundaries

The project advances by composing owned boundaries instead of reimplementing the same concern in multiple chapters:

- Chapter 2 owns evaluation schemas, release thresholds, and cost-per-successful-outcome measurement; later chapters add cases to that suite.
- Chapter 4 owns model routing and inference budgets; Chapter 14 operates that gateway under fleet failure.
- Chapter 5 owns context authority and budgeting; retrieval, memory, and capabilities supply typed inputs.
- Chapters 6 and 7 own knowledge retrieval; Chapter 8 owns user/task memory and never grants authority.
- Chapter 9 owns capability packaging, lifecycle controls, and computer-use adapter boundaries; Chapter 10 owns control topology and browser/computer-use agent behavior; Chapter 11 owns durable execution.
- Chapter 12 owns telemetry, trace-to-eval change, behavior canaries, and production outcome-cost signals; Chapter 13 validates security controls against documents, extensions, and web/tool observations; Chapter 14 owns deployment and recovery; Chapter 15 owns accountable release evidence.
- The capstone wires those outputs together and may omit an optional pattern only through a measured, evidence-linked architecture decision.

## Definition of done

A project is complete only when a clean checkout can start its fixture profile, run its documented verification command, execute every required fault drill, shut down cleanly, and produce the named evidence. Acceptance criteria must be automated where practical. Any manual judgment must identify the reviewer, rubric, input evidence, and decision. These files remain the contract the implementation must satisfy, while the linked lab READMEs and recorded build evidence show the current code path that satisfies that contract.

The final capstone is complete only when all 15 chapter rows in the traceability manifest close, the ordered production game day runs, and the release policy produces an explicit **GO** or **NO-GO**. A failed mandatory gate always yields **NO-GO**.
