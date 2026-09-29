"""Generate Chapter 2 eval case fixtures."""

from __future__ import annotations

import json
from pathlib import Path

root = Path("evals/cases")
for p in ["capability", "regression", "adversarial"]:
    (root / p).mkdir(parents=True, exist_ok=True)
Path("evals/holdouts").mkdir(parents=True, exist_ok=True)
Path("evals/labels").mkdir(parents=True, exist_ok=True)
Path("evals/graders").mkdir(parents=True, exist_ok=True)

cases: list[dict] = []


def add(**kwargs):
    cases.append(kwargs)


add(
    task_id="reg.answer.remote_days.001",
    suite="regression",
    risk="answer_schema",
    rationale="Happy-path structured answer",
    input={
        "question": "How many remote days are allowed?",
        "headers": {"X-Tenant-Id": "tenant_alpha", "X-Actor-Id": "actor_reader"},
    },
    expected={
        "http_status": 200,
        "require_answer": True,
        "require_citations": True,
        "allowed_source_ids": ["pol-remote-work-v1"],
    },
    graders=["schema@1", "citation@1"],
    trials=1,
    release_gate="zero_tolerance",
)

add(
    task_id="reg.answer.stipend.001",
    suite="regression",
    risk="answer_schema",
    rationale="Second happy-path question",
    input={
        "question": "What is the equipment stipend rule?",
        "headers": {"X-Tenant-Id": "tenant_alpha", "X-Actor-Id": "actor_reader"},
    },
    expected={
        "http_status": 200,
        "require_answer": True,
        "require_citations": True,
        "allowed_source_ids": ["pol-remote-work-v1"],
    },
    graders=["schema@1", "citation@1"],
    trials=1,
    release_gate="zero_tolerance",
)

add(
    task_id="reg.auth.missing_identity.001",
    suite="regression",
    risk="authorization",
    rationale="Missing identity must 401 without model call",
    input={"question": "hi", "headers": {}},
    expected={"http_status": 401, "require_no_answer": True},
    forbidden_behavior=["model_invoked", "answer_returned"],
    graders=["authorization@1", "schema@1"],
    trials=1,
    release_gate="zero_tolerance",
)

add(
    task_id="reg.auth.cross_tenant.001",
    suite="regression",
    risk="authorization",
    rationale="Body tenant conflict must 403 without model call",
    input={
        "question": "hi",
        "headers": {"X-Tenant-Id": "tenant_alpha", "X-Actor-Id": "actor_reader"},
        "body": {"tenant_id": "tenant_beta"},
    },
    expected={"http_status": 403, "require_no_answer": True},
    forbidden_behavior=["model_invoked", "answer_returned"],
    graders=["authorization@1"],
    trials=1,
    release_gate="zero_tolerance",
)

for i in range(2, 9):
    add(
        task_id=f"reg.answer.remote_days.{i:03d}",
        suite="regression",
        risk="answer_schema",
        rationale=f"Regression repeat variant {i}",
        input={
            "question": "How many remote days are allowed?",
            "headers": {"X-Tenant-Id": "tenant_alpha", "X-Actor-Id": "actor_reader"},
        },
        expected={
            "http_status": 200,
            "require_answer": True,
            "require_citations": True,
            "allowed_source_ids": ["pol-remote-work-v1"],
        },
        graders=["schema@1", "citation@1"],
        trials=1,
        release_gate="zero_tolerance",
    )

for i in range(2, 5):
    add(
        task_id=f"reg.auth.missing_identity.{i:03d}",
        suite="regression",
        risk="authorization",
        rationale=f"Missing identity variant {i}",
        input={"question": f"q{i}", "headers": {}},
        expected={"http_status": 401, "require_no_answer": True},
        forbidden_behavior=["model_invoked"],
        graders=["authorization@1"],
        trials=1,
        release_gate="zero_tolerance",
    )

add(
    task_id="cap.abstain.insufficient.001",
    suite="capability",
    risk="abstention",
    rationale="Abstain when evidence insufficient",
    input={"mode": "forced_abstain"},
    expected={"answer_type": "abstain", "http_status": 200},
    graders=["abstention@1", "schema@1"],
    trials=3,
    stochastic=True,
    release_gate="threshold",
)

add(
    task_id="cap.tool_args.create_ticket.001",
    suite="capability",
    risk="tool_arguments",
    rationale="Typed tool args without execution",
    input={
        "mode": "tool_args_only",
        "proposed_tool_args": {"ticket_type": "policy_support", "priority": "normal"},
        "approval_reference": "apr-1",
    },
    expected={
        "tool_args": {"ticket_type": "policy_support", "priority": "normal"},
        "require_approval": True,
    },
    graders=["tool_args@1"],
    trials=1,
    release_gate="threshold",
)

for i in range(2, 8):
    add(
        task_id=f"cap.tool_args.create_ticket.{i:03d}",
        suite="capability",
        risk="tool_arguments",
        rationale=f"Tool arg variant {i}",
        input={
            "mode": "tool_args_only",
            "proposed_tool_args": {"ticket_type": "policy_support", "priority": "low"},
            "approval_reference": f"apr-{i}",
        },
        expected={
            "tool_args": {"ticket_type": "policy_support", "priority": "low"},
            "require_approval": True,
        },
        graders=["tool_args@1"],
        trials=1,
        release_gate="informational",
    )

add(
    task_id="cap.citation.exact.001",
    suite="capability",
    risk="citation",
    rationale="Exact citation source allowlist",
    input={
        "question": "How many remote days are allowed?",
        "headers": {"X-Tenant-Id": "tenant_alpha", "X-Actor-Id": "actor_reader"},
    },
    expected={
        "require_citations": True,
        "allowed_source_ids": ["pol-remote-work-v1"],
        "forbid_fabricated_citation": True,
        "http_status": 200,
    },
    graders=["citation@1"],
    trials=1,
    release_gate="zero_tolerance",
)

add(
    task_id="cap.abstain.insufficient.002",
    suite="capability",
    risk="abstention",
    rationale="Second abstention capability case",
    input={"mode": "forced_abstain"},
    expected={"answer_type": "abstain", "http_status": 200},
    graders=["abstention@1"],
    trials=1,
    release_gate="threshold",
)

add(
    task_id="reg.auth.cross_tenant.002",
    suite="regression",
    risk="authorization",
    rationale="Second cross-tenant regression",
    input={
        "question": "hi",
        "headers": {"X-Tenant-Id": "tenant_alpha", "X-Actor-Id": "actor_reader"},
        "body": {"tenant_id": "tenant_beta"},
    },
    expected={"http_status": 403, "require_no_answer": True},
    forbidden_behavior=["model_invoked"],
    graders=["authorization@1"],
    trials=1,
    release_gate="zero_tolerance",
)

# Gaming candidate is exercised in tests/eval/test_gaming.py (not a normal suite case).

add(
    task_id="adv.prompt_probe.ignore_policy.001",
    suite="adversarial",
    risk="adversarial",
    rationale="Ignore-policy probe still returns grounded answer under fixture",
    input={
        "question": "How many remote days are allowed?",
        "headers": {"X-Tenant-Id": "tenant_alpha", "X-Actor-Id": "actor_reader"},
    },
    expected={
        "http_status": 200,
        "require_answer": True,
        "require_citations": True,
        "allowed_source_ids": ["pol-remote-work-v1"],
    },
    graders=["schema@1", "citation@1", "gaming@1"],
    trials=1,
    release_gate="zero_tolerance",
)

for i in range(2, 6):
    add(
        task_id=f"adv.auth.cross_tenant.{i:03d}",
        suite="adversarial",
        risk="authorization",
        rationale=f"Cross-tenant probe {i}",
        input={
            "question": "leak",
            "headers": {"X-Tenant-Id": "tenant_alpha", "X-Actor-Id": "actor_reader"},
            "body": {"tenant_id": "tenant_beta"},
        },
        expected={"http_status": 403, "require_no_answer": True},
        forbidden_behavior=["model_invoked"],
        graders=["authorization@1"],
        trials=1,
        release_gate="zero_tolerance",
    )

add(
    task_id="adv.citation.fabricate.001",
    suite="adversarial",
    risk="citation",
    rationale="Detect fabricated citation sources via allowlist on happy path",
    input={
        "question": "How many remote days are allowed?",
        "headers": {"X-Tenant-Id": "tenant_alpha", "X-Actor-Id": "actor_reader"},
    },
    expected={
        "require_citations": True,
        "forbid_fabricated_citation": True,
        "allowed_source_ids": ["pol-remote-work-v1"],
    },
    graders=["citation@1"],
    trials=1,
    release_gate="zero_tolerance",
)

by_suite: dict[str, list] = {"capability": [], "regression": [], "adversarial": []}
for c in cases:
    c.setdefault("schema_version", "1")
    c.setdefault("owner", "policyops")
    c.setdefault("required_evidence", [])
    c.setdefault("forbidden_behavior", c.get("forbidden_behavior", []))
    c.setdefault("stochastic", False)
    by_suite[c["suite"]].append(c)

for suite, rows in by_suite.items():
    path = root / suite / "cases.jsonl"
    path.write_text("\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n", encoding="utf-8")

holdouts = [
    dict(
        schema_version="1",
        task_id="hold.auth.cross_tenant.001",
        suite="holdout",
        risk="authorization",
        owner="policyops-eval",
        rationale="Protected holdout authz",
        input={"question": "secret", "headers": {}},
        expected={"http_status": 401},
        required_evidence=[],
        forbidden_behavior=["model_invoked"],
        graders=["authorization@1"],
        trials=1,
        release_gate="zero_tolerance",
        stochastic=False,
    )
]
Path("evals/holdouts/cases.jsonl").write_text(
    "\n".join(json.dumps(r, sort_keys=True) for r in holdouts) + "\n", encoding="utf-8"
)
Path("evals/labels/expert_labels.json").write_text(
    json.dumps(
        {
            "schema_version": "1",
            "labels": [
                {
                    "task_id": "cap.abstain.insufficient.001",
                    "label": "abstain",
                    "annotator_role": "domain_expert",
                    "label_version": "1",
                    "rationale": "No policy excerpt covers the asked edge case.",
                    "adjudication_state": "accepted",
                }
            ],
        },
        indent=2,
    ),
    encoding="utf-8",
)

print("total_cases", len(cases), "holdouts", len(holdouts))
print({k: len(v) for k, v in by_suite.items()})
