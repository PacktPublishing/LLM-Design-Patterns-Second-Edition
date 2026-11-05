# Repository Guidelines: LLM Design Patterns, Second Edition

## Dual Remote Synchronization (Mandatory)
This repository has two authoritative remotes that MUST ALWAYS be kept in 100% lockstep on `main`:
1. **Personal remote (`origin`):** `https://github.com/kenhuangus/llm-design-patterns-hands-on.git`
2. **Packt official remote (`packt`):** `https://github.com/PacktPublishing/LLM-Design-Patterns-Second-Edition.git`

Both remotes are configured with dual `pushurl` entries in `.git/config`. Any `git push` or `git push origin main` command automatically deploys to both destinations.

To verify or repair remote synchronization at any time, run:
```bash
python scripts/sync_remotes.py
```

## Commit Author Policy
- Author and committer MUST ALWAYS be `kenhuangus <kenhuangus@gmail.com>`.
- Never set Cursor, Claude, Copilot, or any coding agent as author, committer, or `Co-authored-by` / `Signed-off-by` contributor.

## Testing and Packaging Standards
- Python dependencies are managed with `uv`.
- Development dependencies (`pytest`, `pytest-asyncio`, `ruff`) must reside under `[dependency-groups] dev` in `pyproject.toml` (PEP 735) so that `uv sync --frozen` preserves them for lab readers.
- All 325 test items and 16 chapter verifiers (`policyops verify ch01` .. `ch16`) must pass before merging or pushing changes to `main`.
