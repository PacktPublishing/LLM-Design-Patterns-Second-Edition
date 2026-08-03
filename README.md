# LLM Design Patterns, Second Edition: Hands-On Projects

Private engineering workspace for the hands-on projects accompanying the proposed second edition of **LLM Design Patterns** by **Ken Huang**.

> **Status:** Chapters 1–16 fixture labs are implemented and verified. The capstone closes the cumulative design → implement → verify loop.

## About the book

The second edition updates the design-pattern approach of the first edition for production LLM and agentic AI systems. It retains the practical foundation of the original book while substantially revising and expanding the material for modern model integration, evaluation, multimodal retrieval, browser/computer-use agents, capability protocols, durable execution, operations, security, and governance. Current protocols and frameworks are treated as examples of durable architecture patterns rather than as the book's main dependency.

The planned book has 16 chapters and 480 instructional pages, with approximately 55% new or substantially revised content. Every chapter includes one executable hands-on project. The projects build a single cumulative application rather than a collection of disconnected demos.

The intended audience includes AI engineers, application engineers, platform engineers, architects, security engineers, and technical leaders who need to move LLM applications from prototypes into controlled production systems.

## The running project: PolicyOps

**PolicyOps** is a multi-tenant knowledge-and-action assistant. It answers questions from a versioned policy corpus with exact citations and, when the user has current authority and gives explicit approval, creates a policy-support ticket.

The application grows chapter by chapter:

- provider-neutral model and request contracts;
- evaluation-driven development, release gates, and cost per successful outcome;
- evidence-based adaptation and inference decisions;
- authority-ranked context planning;
- hybrid RAG with scanned/OCR-aware fixtures, Graph RAG, and governed memory;
- typed tools, MCP, Agent Skills, plugins, and lifecycle hooks;
- bounded orchestration, browser/computer-use fixtures, and durable agent execution;
- observability, trace-to-evaluation improvement, and behavior canaries;
- prompt-injection defenses for documents and web/tool observations, capability controls, and containment;
- deployment, load management, fault recovery, and rollback;
- governance, human oversight, user rights, and release evidence.

The Chapter 16 capstone integrates the accepted chapter checkpoints and runs a 16-step production game day. Any failed mandatory gate produces a documented **NO-GO** rather than a weakened release.

## Hands-on roadmap

| Chapter | Project | Specifications |
|---:|---|---|
| 1 | Build the PolicyOps foundation | [PRD](docs/implementation-plans/chapters/ch01-policyops-foundation/prd.md) · [Architecture](docs/implementation-plans/chapters/ch01-policyops-foundation/architecture.md) · [Design](docs/implementation-plans/chapters/ch01-policyops-foundation/design.md) · [Lab README](labs/ch01/README.md) |
| 2 | Create an evaluation-driven development suite | [PRD](docs/implementation-plans/chapters/ch02-evaluation-driven-development-suite/prd.md) · [Architecture](docs/implementation-plans/chapters/ch02-evaluation-driven-development-suite/architecture.md) · [Design](docs/implementation-plans/chapters/ch02-evaluation-driven-development-suite/design.md) · [Lab README](labs/ch02/README.md) |
| 3 | Choose the right adaptation strategy | [PRD](docs/implementation-plans/chapters/ch03-adaptation-strategy/prd.md) · [Architecture](docs/implementation-plans/chapters/ch03-adaptation-strategy/architecture.md) · [Design](docs/implementation-plans/chapters/ch03-adaptation-strategy/design.md) · [Lab README](labs/ch03/README.md) |
| 4 | Build an adaptive inference gateway | [PRD](docs/implementation-plans/chapters/ch04-adaptive-inference-gateway/prd.md) · [Architecture](docs/implementation-plans/chapters/ch04-adaptive-inference-gateway/architecture.md) · [Design](docs/implementation-plans/chapters/ch04-adaptive-inference-gateway/design.md) · [Lab README](labs/ch04/README.md) |
| 5 | Build a context planner | [PRD](docs/implementation-plans/chapters/ch05-context-planner/prd.md) · [Architecture](docs/implementation-plans/chapters/ch05-context-planner/architecture.md) · [Design](docs/implementation-plans/chapters/ch05-context-planner/design.md) · [Lab README](labs/ch05/README.md) |
| 6 | Build a citation-first hybrid RAG service | [PRD](docs/implementation-plans/chapters/ch06-citation-first-hybrid-rag/prd.md) · [Architecture](docs/implementation-plans/chapters/ch06-citation-first-hybrid-rag/architecture.md) · [Design](docs/implementation-plans/chapters/ch06-citation-first-hybrid-rag/design.md) · [Lab README](labs/ch06/README.md) |
| 7 | Add graph retrieval for multi-hop questions | [PRD](docs/implementation-plans/chapters/ch07-graph-retrieval/prd.md) · [Architecture](docs/implementation-plans/chapters/ch07-graph-retrieval/architecture.md) · [Design](docs/implementation-plans/chapters/ch07-graph-retrieval/design.md) · [Lab README](labs/ch07/README.md) |
| 8 | Add governed long-term memory | [PRD](docs/implementation-plans/chapters/ch08-governed-long-term-memory/prd.md) · [Architecture](docs/implementation-plans/chapters/ch08-governed-long-term-memory/architecture.md) · [Design](docs/implementation-plans/chapters/ch08-governed-long-term-memory/design.md) · [Lab README](labs/ch08/README.md) |
| 9 | Build a secure PolicyOps extension pack | [PRD](docs/implementation-plans/chapters/ch09-secure-extension-pack/prd.md) · [Architecture](docs/implementation-plans/chapters/ch09-secure-extension-pack/architecture.md) · [Design](docs/implementation-plans/chapters/ch09-secure-extension-pack/design.md) · [Lab README](labs/ch09/README.md) |
| 10 | Build a bounded orchestrator-worker flow | [PRD](docs/implementation-plans/chapters/ch10-bounded-orchestrator-worker/prd.md) · [Architecture](docs/implementation-plans/chapters/ch10-bounded-orchestrator-worker/architecture.md) · [Design](docs/implementation-plans/chapters/ch10-bounded-orchestrator-worker/design.md) · [Lab README](labs/ch10/README.md) |
| 11 | Make the agent loop resumable | [PRD](docs/implementation-plans/chapters/ch11-resumable-agent-loop/prd.md) · [Architecture](docs/implementation-plans/chapters/ch11-resumable-agent-loop/architecture.md) · [Design](docs/implementation-plans/chapters/ch11-resumable-agent-loop/design.md) · [Lab README](labs/ch11/README.md) |
| 12 | Turn a production trace into a safe improvement | [PRD](docs/implementation-plans/chapters/ch12-trace-to-safe-improvement/prd.md) · [Architecture](docs/implementation-plans/chapters/ch12-trace-to-safe-improvement/architecture.md) · [Design](docs/implementation-plans/chapters/ch12-trace-to-safe-improvement/design.md) · [Lab README](labs/ch12/README.md) |
| 13 | Defend against indirect prompt injection | [PRD](docs/implementation-plans/chapters/ch13-prompt-injection-defense/prd.md) · [Architecture](docs/implementation-plans/chapters/ch13-prompt-injection-defense/architecture.md) · [Design](docs/implementation-plans/chapters/ch13-prompt-injection-defense/design.md) · [Lab README](labs/ch13/README.md) |
| 14 | Deploy and recover the PolicyOps service | [PRD](docs/implementation-plans/chapters/ch14-policyops-deployment-recovery/prd.md) · [Architecture](docs/implementation-plans/chapters/ch14-policyops-deployment-recovery/architecture.md) · [Design](docs/implementation-plans/chapters/ch14-policyops-deployment-recovery/design.md) · [Lab README](labs/ch14/README.md) |
| 15 | Conduct a governance release review | [PRD](docs/implementation-plans/chapters/ch15-governance-release-review/prd.md) · [Architecture](docs/implementation-plans/chapters/ch15-governance-release-review/architecture.md) · [Design](docs/implementation-plans/chapters/ch15-governance-release-review/design.md) · [Lab README](labs/ch15/README.md) |
| 16 | Integrate and release the PolicyOps agent | [PRD](docs/implementation-plans/chapters/ch16-policyops-capstone/prd.md) · [Architecture](docs/implementation-plans/chapters/ch16-policyops-capstone/architecture.md) · [Design](docs/implementation-plans/chapters/ch16-policyops-capstone/design.md) · [Lab README](labs/ch16/README.md) |

The [implementation-plan index](docs/implementation-plans/README.md) explains shared contracts, chapter ownership, cumulative handoffs, and the definition of done.

## Engineering principles

The implementation is designed around these constraints:

1. **Runnable without paid credentials.** Every mandatory chapter path uses deterministic fixtures and replay adapters. Hosted models and cloud profiles are optional extensions.
2. **One canonical contract set.** Later chapters import the model, context, retrieval, memory, capability, orchestration, and durable-execution types established earlier.
3. **Models propose; deterministic code controls.** Identity, authorization, policy, budgets, joins, approval, idempotency, effects, and release decisions remain outside model authority.
4. **Evidence before release.** Every requirement maps to an architecture component and a testable acceptance criterion. Chapter artifacts feed a machine-readable capstone traceability manifest.
5. **Failure is part of the lab.** Each project includes adversarial or degraded scenarios, verification commands, cleanup, and rollback or recovery evidence.
6. **Security and privacy are system properties.** Tenant isolation, instruction/data separation, exact-effect approval, revocation, sandboxing, browser/profile isolation, egress control, provenance, correction, export, and deletion cross component boundaries.

## Implementation profile

The specifications assume Python 3.12+, `uv`, FastAPI, Pydantic, pytest, OpenTelemetry-compatible instrumentation, PostgreSQL/pgvector where durable data or retrieval requires them, and Docker Compose for the mandatory local system profile. Exact dependency and image versions will be selected, pinned, hashed, and recorded when implementation begins.

Each chapter exposes one verification entry point:

```text
uv run policyops verify chNN --profile fixture
```

The capstone will run the complete suite through:

```text
uv run policyops verify ch16 --profile fixture --all
```

## Repository structure

```text
README.md
docs/
  implementation-plans/
    README.md
    chapters/
      ch01-.../prd.md
      ch01-.../architecture.md
      ...
      ch15-.../prd.md
      ch15-.../architecture.md
      ch16-policyops-capstone/prd.md
      ch16-policyops-capstone/architecture.md
```

Chapter 1, Chapter 2, Chapter 3, Chapter 4, Chapter 5, Chapter 6, Chapter 7, Chapter 8, Chapter 9, Chapter 10, Chapter 11, Chapter 12, Chapter 13, Chapter 14, Chapter 15, and Chapter 16 source code, fixtures, tests, Dockerfile, and executable verification workflows are included.

## Rights and repository scope

This is a private working repository for the author and authorized collaborators. No public license is granted at this stage. The first-edition Packt PDF, publisher templates, manuscript production files, correspondence, credentials, and other third-party assets are intentionally excluded.

Copyright © Ken Huang. All rights reserved.
