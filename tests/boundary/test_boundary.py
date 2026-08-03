"""Boundary tests — no provider leakage; no secrets in evidence paths."""

from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_IMPORTS = {
    "openai",
    "anthropic",
    "google.generativeai",
    "google.genai",
    "cohere",
    "bedrock",
}

SRC = Path("src/policyops")
ALLOWED_PROVIDER_ROOTS = {SRC / "adapters"}


def _is_under_adapters(path: Path) -> bool:
    try:
        path.relative_to(SRC / "adapters")
        return True
    except ValueError:
        return False


def test_no_provider_imports_outside_adapters() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        if _is_under_adapters(path):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if alias.name in FORBIDDEN_IMPORTS or root in FORBIDDEN_IMPORTS:
                        offenders.append(f"{path}:{alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module in FORBIDDEN_IMPORTS or node.module.split(".")[0] in {
                    "openai",
                    "anthropic",
                    "cohere",
                }:
                    offenders.append(f"{path}:{node.module}")
    assert offenders == []


def test_env_example_has_no_real_secrets() -> None:
    path = Path(".env.example")
    assert path.exists()
    text = path.read_text(encoding="utf-8").lower()
    assert "sk-" not in text
    assert "begin private" not in text


def test_local_adapter_does_not_delegate_to_replay_adapter() -> None:
    path = SRC / "adapters" / "local" / "__init__.py"
    text = path.read_text(encoding="utf-8")
    assert "policyops.adapters.replay" not in text
    assert "ReplayModelClient" not in text
