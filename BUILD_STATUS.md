# Build Status — v0.3.5

## Baseline

- v0.3.4 production behavior was verified before this release.
- Local untouched v0.3.4 baseline: **49/49 tests passed**.
- Locked NVDA Jun-Aug 2026 production anchor remained 7 trades / 6 wins / +$42.604714 total P/L / +$6.086388 EV per trade under v0.3.4.

## v0.3.5 completed work

- Runtime build identity through `/health`: version, `git_commit`, branch/repository, Railway deployment ID, optional build time.
- `/api/v1/capabilities.release` publishes build identity, formula versions, and derived-cache format version.
- GitHub Actions CI for pull requests and `main` pushes using Python 3.12.
- CI runs pytest, compileall, cache benchmark, and rejects tracked `__pycache__` / `.pyc/.pyo` / `.pytest_cache` artifacts.
- `scripts/production_acceptance.py` automates the frozen NVDA production regression and derived-cache warm-hit check.
- Supabase GitHub recovery bridge migration and runbook under `ops/supabase/`.
- Live bridge smoke test recovered 56 eligible source files with 56/56 HTTP 200 responses and 56/56 Git blob SHA integrity matches after moving file-body retrieval to `raw.githubusercontent.com`.

## Behavioral claim

v0.3.5 is an infrastructure/reproducibility release. It does **not** intentionally change entry rules, regime formulas, sentiment formulas, execution semantics, slippage, stops, targets, position sizing, or strategy-decision caching.

## Deployment gate

Run the full local verification suite and package integrity checks, push through a feature branch/CI workflow, merge to `main`, allow Railway to deploy, then run `scripts/production_acceptance.py` against production before tagging v0.3.5.

## Final local verification

- Full test suite: **63/63 passed**.
- `compileall`: passed for application, cache, integration, scripts, benchmarks, and tests.
- Controlled cache benchmark (120,000 rows): cold miss `0.9637s`, warm hit `0.0310s`, compute callback invoked once.
- Secret-like credential scan: no matches.
- Supabase recovery bridge live validation: 56/56 eligible source files fetched with HTTP 200 and 56/56 Git blob SHA matches.
- Supabase performance advisor: no performance lints after v0.3.5 bridge migration.
