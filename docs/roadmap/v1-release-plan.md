# BKTSTR v1 Release Plan

This outcome-driven plan maps the standalone web-application roadmap to production versions. GitHub Project owns live status; this document owns stable outcomes, order, and exit criteria.

| Version | State | Milestone | Production outcome |
| --- | --- | --- | --- |
| v0.4.0 | Active planning | Baseline and documentation repair | Trustworthy docs, executable examples, professional delivery governance, and a frozen v0.3.5 baseline |
| v0.5.0 | Planned | Strategy-neutral core | Stable domain contracts with equal normalized trading output |
| v0.6.0 | Planned | FastAPI application foundation | Typed API, OpenAPI, compatibility routing, structured errors, and health contracts |
| v0.7.0 | Planned | Persistence and single-owner authentication | Private owner access and durable research records |
| v0.8.0 | Planned | Durable execution jobs | Worker jobs with idempotency, retries, cancellation, heartbeat, and recovery |
| v0.9.0 | Planned | React research workspace | Complete browser research workflow |
| v1.0.0 | Planned | Railway production cutover | Stable private web application as the normal BKTSTR interface |

## Release rules

- A release ships when its outcome and exit criteria pass, not on a fixed date.
- Minor versions represent roadmap capability milestones; patch versions contain compatible production fixes.
- Incomplete merged work must remain inactive, backward-compatible, or production-safe.
- Every release uses a final version-preparation pull request, exact-SHA Railway verification, production acceptance, an annotated tag, and a GitHub Release.
- Published tags are never moved or reused.

## Exit criteria

### v0.4.0

Current tests and production acceptance pass; published examples execute in CI; documentation has one entry point; the v0.3.5 baseline is versioned and reproducible; GitHub governance is active.

### v0.5.0

The migrated baseline produces byte-equivalent normalized trades and equal summaries with caches enabled and disabled.

### v0.6.0

API contract, legacy compatibility, structured-error, and production baseline tests pass through FastAPI.

### v0.7.0

Authentication, authorization, migration, immutability, and backup/restore checks pass from empty and previous database states.

### v0.8.0

Runs survive web restarts; worker interruption cannot duplicate results; cancellation, retry, heartbeat, and recovery match the state machine.

### v0.9.0

Browser tests cover login, strategy versioning, submission, completion, failure, rerun, notes, tags, comparison, and logout.

### v1.0.0

Production is owner-only; deployed identity matches the released commit; frozen baseline and durable saved-state checks pass across web and worker redeployments.
