# Chapter 16 Design: PolicyOps Capstone Game Day

This implementation closes the project loop. It does not add a new pattern; it verifies that the accepted Chapter 1-15 checkpoints compose into one releaseable PolicyOps fixture system. The capstone verifier checks traceability, executes the ordered game-day model, proves a seeded mandatory failure returns `NO-GO`, signs the evidence bundle, and emits the final release decision.

## Reader-facing flow

1. Validate `capstone/traceability.yaml` and require one accepted row for every Chapter 1-15 handoff.
2. Confirm each row has a verification command, rollback path, `GO` decision, and accepted status.
3. Run the 16 ordered production game-day scenarios from the chapter.
4. Preserve scenario prerequisites, actions, expected/actual results, evidence references, and cleanup status.
5. Inject one mandatory failure and prove the decision engine returns `NO-GO`.
6. Build a signed evidence bundle from traceability, game-day, and governance decision hashes.
7. Emit `GO` only when traceability closes, all mandatory game-day steps pass, security/reliability/governance invariants hold, and the seeded failure test proves fail-closed behavior.

## Files

| Area | Path |
|---|---|
| Schemas | `src/policyops/capstone/schemas.py` |
| Runtime and verifier | `src/policyops/capstone/service.py` |
| Public API | `src/policyops/capstone/__init__.py` |
| Tests | `tests/capstone/test_capstone.py` |
| Lab guide | `labs/ch16/README.md` |
| Lab manifest | `labs/ch16/manifest.toml` |

## Key design decisions

- Treat Chapter 16 as a release verifier, not a second implementation of the earlier chapters.
- Keep the fixture path deterministic and credential-free.
- Use `capstone/traceability.yaml` as the chapter handoff closure source.
- Model the ordered game day as explicit scenario records with mandatory cleanup evidence.
- Require a seeded failure to prove the release gate can say `NO-GO`.

## Verification coverage

The Chapter 16 verifier covers:

- all 15 prior chapter traceability rows;
- verification command and rollback-path presence;
- 16 ordered game-day scenario results;
- seeded mandatory failure to `NO-GO`;
- signed release bundle hashes;
- duplicate-effect, unauthorized-effect, cross-tenant, secret, rights, and evidence-signature invariants;
- final `GO` release decision only when every mandatory gate passes.
