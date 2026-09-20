# BKTSTR research runbook

**Current release:** v0.6.0

BKTSTR tests trading hypotheses independently of any investment fund or portfolio.
Read [AGENTS.md](AGENTS.md) and the [system design](docs/BKTSTR_SYSTEM_MANUAL.md).
For planned Jev and paper workflows, follow the
[implementation plan](docs/IMPLEMENTATION_PLAN.md).

## Define an experiment

Record the hypothesis, instruments, session, signal timing, entry and exit rules,
position sizing, costs, data requirements, and rejection criteria. Separate
development dates from validation and final evaluation dates. State the search
budget before running variants. Example capital and sizing are simulation inputs,
not actual account values.

Use the current registered baseline only when it expresses the hypothesis.
Unsupported strategy behavior requires implementation; do not approximate a
different idea silently to fit the available endpoint.

For configurable numerical research in the local checkout, use the
[strategy document interface](docs/STRATEGY_CONFIGURATION.md). Save the normalized
manifest and digest with the result. This local interface does not submit an HTTP
experiment or automatically persist it in the service's experiment store.

## Connect to the current service

Use the [local credential helper](docs/development/local-credentials.md).
Verify `GET /health`, then authenticated `GET /api/v1/capabilities`.
Record the returned version and `git_commit`, rather than assuming a deployment
matches the checkout. Requests use `Authorization: Bearer <BKTSTR_API_KEY>`.

Use the [API reference](docs/API_REFERENCE.md) for complete payloads.
Submit `POST /api/v1/backtests` with a stable `Idempotency-Key` for retries.
Poll `GET /api/v1/experiments/{experiment_id}` until completed or failed.
Respect `Retry-After`; do not resubmit work because it is still queued.

Check provenance, date coverage, provider, evidence tiers, execution model,
degraded status, and errors before interpreting results. `stop_pct=1` means 1%.

## Compare hypotheses

Keep the technical trigger, market range, sizing, costs, and exit rules aligned.
Change one layer at a time:

1. Technical baseline.
2. Baseline plus numerical macro/market/sector conditions.
3. The same strategy plus a frozen Jev interpretation, once implemented.

Report opportunity counts before and after filters, trade counts, exposure,
net results, drawdown, cost sensitivity, and results by period and instrument.
Keep unavailable metrics explicitly unavailable. Small samples and zero-trade
variants are findings, not reasons to discard a run. Separate development results
from held-out results and record every inspection of final evaluation data.

For Jev, evaluate interpretation quality separately from trading performance.
Historical model knowledge can contaminate retrospective tests even when supplied
evidence is timestamp-correct; retain that limitation and validate prospectively.

## Paper sessions, once implemented

Freeze the configuration and set start/end times, instruments, simulation capital,
exposure limits, daily loss limit, model budget, and evidence freshness.
Use recorded model responses for replay and live acquisition only for forward
sessions. Prevent new entries on stale data, model failure, or budget exhaustion;
continue deterministic management of existing positions.

Keep the internal paper ledger separate from Clear Street demo records. A broker
sandbox validates connectivity and order handling; its simplified fills are not
strategy-performance evidence.

## Report and hand off

Return the experiment ID, frozen configuration digest, data and model lineage,
test periods, comparison, missing evidence, and reproducibility instructions.
Save research outputs as experiment artifacts, not permanent project doctrine.
Documentation must not accumulate account snapshots, portfolio metrics, or
session-specific troubleshooting stories.

For implementation changes, use a feature branch, GitHub CI, and the release
procedure. `scripts/production_acceptance.py` verifies deployment identity and
authenticated research behavior; it creates experiments and is not a health ping.
