"""Local runtime process used by the Chapter 1 optional local adapter."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_policy(policy_root: Path) -> dict[str, str]:
    path = policy_root / "remote_work_v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "policy_id": payload["policy_id"],
        "title": payload["title"],
        "version": payload["version"],
        "excerpt": payload["excerpt"],
    }


def _answer_for(question: str, policy: dict[str, str]) -> dict[str, object]:
    lower = question.lower()
    if "remote" in lower and "day" in lower:
        text = "Employees may work remotely up to three days per week with manager approval."
        locator = "section:remote-days"
        excerpt = text
    elif "equipment" in lower or "stipend" in lower or "finance" in lower:
        text = "Equipment stipends require Finance sign-off."
        locator = "section:stipend"
        excerpt = text
    else:
        text = "I cannot answer that from the Chapter 1 local policy excerpt."
        locator = "section:abstain"
        excerpt = policy["excerpt"]
        return {
            "schema_version": "1.0",
            "answer_type": "abstain",
            "text": text,
            "abstention_reason": "policy_excerpt_missing_fact",
            "citations": [
                {
                    "schema_version": "1.0",
                    "source_id": policy["policy_id"],
                    "title": policy["title"],
                    "locator": locator,
                    "excerpt": excerpt,
                }
            ],
        }

    return {
        "schema_version": "1.0",
        "answer_type": "direct",
        "text": text,
        "citations": [
            {
                "schema_version": "1.0",
                "source_id": policy["policy_id"],
                "title": policy["title"],
                "locator": locator,
                "excerpt": excerpt,
            }
        ],
    }


def _usage_for(question: str) -> dict[str, object]:
    input_tokens = max(8, len(question.split()) * 5)
    output_tokens = 20 if "remote" in question.lower() else 16
    return {
        "schema_version": "1.0",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "adapter": "local",
    }


def _failure(code: str, retry_class: str, message: str, correlation_token: str | None) -> dict[str, object]:
    return {
        "kind": "failure",
        "failure": {
            "schema_version": "1.0",
            "code": code,
            "retry_class": retry_class,
            "message": message,
            "correlation_token": correlation_token,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy-root", required=True)
    parser.add_argument("--health", action="store_true")
    args = parser.parse_args(argv)

    policy_root = Path(args.policy_root)
    if args.health:
        if (policy_root / "remote_work_v1.json").exists():
            sys.stdout.write("ok")
            return 0
        return 1

    policy = _load_policy(policy_root)
    payload = json.loads(sys.stdin.read() or "{}")
    request = payload.get("request", {})
    context = payload.get("context", {})
    fault_scenario = payload.get("fault_scenario")
    correlation_token = context.get("request_id")

    if fault_scenario == "upstream_error":
        sys.stdout.write(
            json.dumps(
                _failure(
                    "MODEL_CAPACITY",
                    "upstream",
                    "local runtime capacity unavailable",
                    correlation_token,
                )
            )
        )
        return 0
    if fault_scenario == "invalid_json":
        sys.stdout.write("{not-json")
        return 0
    if fault_scenario == "schema_invalid":
        sys.stdout.write(
            json.dumps(
                {
                    "kind": "success",
                    "answer": {"schema_version": "1.0", "answer_type": "direct"},
                    "usage": _usage_for(request.get("question", "")),
                }
            )
        )
        return 0

    question = str(request.get("question", ""))
    response = {
        "kind": "success",
        "answer": _answer_for(question, policy),
        "usage": _usage_for(question),
    }
    sys.stdout.write(json.dumps(response))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
