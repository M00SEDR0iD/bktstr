# BKTSTR v0.3.5 Development Infrastructure Design

## Goal
Make BKTSTR releases faster to develop, easier to identify in production, and reproducible when direct GitHub access from an agent is unavailable, without changing any trading-model behavior.

## Scope
v0.3.5 is an infrastructure/reproducibility release. It must not change entry rules, regime formulas, sentiment formulas, fills, slippage, stops, targets, sizing, look-ahead behavior, or cached strategy decisions.

## Release identity
Add a small build-info boundary that reads deployment identity from environment variables. Railway GitHub deployments provide `RAILWAY_GIT_COMMIT_SHA`, `RAILWAY_GIT_BRANCH`, `RAILWAY_GIT_REPO_NAME`, `RAILWAY_GIT_REPO_OWNER`, and `RAILWAY_DEPLOYMENT_ID`. Local/test deployments may override commit/build metadata with `BKTSTR_GIT_COMMIT` and `BKTSTR_BUILD_TIME`.

`/health` will expose:
- service status/name/version
- git commit SHA when available
- git branch/repository/deployment ID when available
- optional build time when explicitly supplied

`/api/v1/capabilities` will expose a stable `release` section containing the same build identity plus deterministic research compatibility identifiers:
- intraday feature formula version
- regime formula version
- sentiment formula version
- derived cache format version

Missing optional metadata is represented as `null`; it must never prevent the service from starting.

## Continuous integration
Add `.github/workflows/ci.yml` for pushes and pull requests. CI uses Python 3.12, installs `requirements-dev.txt`, runs the complete pytest suite, compiles application/scripts, and runs the cache benchmark as a smoke test. CI is read-only and requires no API secrets.

## Production acceptance
Add a deterministic CLI acceptance script that:
1. checks `/health` and requires the expected release version;
2. checks `/api/v1/capabilities` and requires the derived-cache contract;
3. runs the locked NVDA Jun 1-Aug 21 2026 anchor twice;
4. requires identical request-independent trading output between runs;
5. requires all second-run derived cache namespaces to report hits;
6. requires the known anchor summary: 7 trades, 6 wins, 1 loss, total P/L 42.604714, EV/trade 6.086388.

Timing values and cache hit/miss metadata are excluded from equality comparison. The script never places trades and uses only the public BKTSTR read API.

## GitHub-through-Supabase recovery bridge
Preserve Supabase `pg_net` as an emergency source-recovery plane. Add a migration defining durable staging tables and helper functions so an agent can recover an exact public GitHub commit in four phases:
1. enqueue commit metadata request;
2. enqueue recursive tree request from the resolved commit;
3. enqueue all text blob requests and map each request ID to path/SHA;
4. collect completed blob responses into a snapshot table.

The bridge stores only repository source from the public BKTSTR repo. It does not store GitHub credentials, Railway secrets, Massive keys, or strategy results. It is not part of the runtime BKTSTR request path.

## Documentation and development workflow
Document the standard release flow:
feature branch -> GitHub CI -> merge main -> Railway auto-deploy -> Supabase/Railway acceptance -> tag release.

Document the Supabase recovery bridge as an emergency fallback, not the primary Git development method.

## Testing
- Existing v0.3.4 suite must remain green.
- New unit tests cover environment-to-build-info normalization and API metadata.
- New acceptance-script tests use an injected HTTP transport and verify equality/caching/anchor checks.
- Static ops tests verify CI and Supabase migration assets are present and versioned.
- Live Supabase bridge functions are smoke-tested after migration.
- Final full suite, compileall, benchmark, and package integrity checks are required.

## Release gate
v0.3.5 may be called deploy-ready only if:
- all local tests pass;
- no strategy regression tests change expected values;
- `/health` and capabilities tests identify 0.3.5;
- the Supabase bridge migration applies cleanly and can recover a GitHub commit/tree/blob snapshot;
- the deployment package contains the full repository tree needed by GitHub/Railway.
