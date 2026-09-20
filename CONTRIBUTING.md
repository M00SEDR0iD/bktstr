# Contributing to BKTSTR

Read [agent instructions](AGENTS.md), the [system design](docs/BKTSTR_SYSTEM_MANUAL.md),
and the [implementation plan](docs/IMPLEMENTATION_PLAN.md). BKTSTR is independent
of fund-specific strategies, portfolios, and accounts.

## Scope changes

Use a focused `codex/<topic>` branch unless the task specifies another name.
Keep public API changes, execution-semantic changes, and unrelated refactors
separate. Preserve other work in the checkout. Do not commit credentials,
generated experiment artifacts, caches, or local environments.

Strategy revisions normally change versioned configuration. Code changes are
needed for new providers, measurements, execution behaviors, or unsupported
strategy structures. Freeze inputs and expected behavior before implementation.

## Verification

For code changes, run focused behavioral tests followed by the relevant suite.
Tests should establish causality, replay fidelity, API behavior, and recovery,
rather than freeze incidental prose or old research results.

```powershell
python -m pytest -q
python scripts/check_release_consistency.py
python -m compileall -q bktstr bktstr_cache integration scripts
python benchmarks/benchmark_cache.py
```

For documentation-only edits, verify links, runtime-versus-plan wording, current
API examples, and release consistency. Do not claim that a documentation review
validates trading behavior or deployment.

Documentation checks cover active entry points, local links, release identity,
API contracts, and the distinction between current and planned capabilities.
Keep those checks aligned with the current references rather than old snapshots.

## Review and delivery

Describe the concrete change, its motivation, checks performed, and remaining
limitations. Link an issue when one exists. Required repository checks must pass
before merge; a known obsolete test is not permission to bypass CI.

Keep `main` deployable. Do not rewrite published history or move release tags.
Follow [the release procedure](docs/development/releases.md) when shipping.
