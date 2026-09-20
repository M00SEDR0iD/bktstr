# BKTSTR

**Current release: v0.6.0**

BKTSTR is an independent trading research system for turning ideas into explicit,
versioned strategies and testing them against market evidence. It is separate
from the Bailey Fund: it does not inherit fund holdings, allocations, objectives,
account balances, or investment mandates.

The direction is a configurable deterministic engine with optional Jev macro
judgments through OpenRouter. Strategies stay fixed during each experiment.
Most new theories should change configuration; new data sources, measurements,
and execution behaviors require code.

## Current capability and planned work

The existing application runs historical equity/ETF research. It provides typed
backtests, parameter sweeps, comparisons, durable experiments, market-data
inspection, deterministic caches, and evidence provenance. Its registered
strategy is `bktstr.bearish-regime-scalp` version `1.0.0`, using one-minute bars.
That strategy is a supported baseline, not the identity of the project.

Local [strategy documents](docs/STRATEGY_CONFIGURATION.md) now compile to frozen,
fingerprinted configurations and run through the existing engine. Numerical entry
and daily regime gates are supported without changing trading code.

Local [macro evidence](docs/MACRO_EVIDENCE.md) now supports publication/receipt
cutoffs, revision selection, immutable packets, and offline source replay.
The first BLS CPI adapter supports prospective collection; it cannot reconstruct
historical release vintages or drive strategy gates yet.

Jev integration, historical macro release ingestion,
continuous paper testing, and Clear Street connectivity are planned and are not implemented.
The current application places no
brokerage orders. Live-money trading is outside the next implementation scope.

## Intended workflow

The next priority is [reusable trade ideas and controlled research](docs/TRADE_IDEA_CONTAINERS.md):
document a thesis once, organize variations beneath it, apply the recipe to explicit
stocks, and preserve controlled comparisons. This foundation comes before Jev.

1. State a hypothesis and specify what would count as evidence against it.
2. Freeze the strategy, data requirements, costs, test periods, and search budget.
3. Compare a technical baseline, numerical context filters, and optional Jev judgments.
4. Replay saved evidence and evaluate periods excluded from strategy development.
5. Run a bounded paper session using the same decision rules.
6. Review results and create a new strategy version for any revision.

## Start here

- [Documentation index](docs/README.md)
- [Agent instructions](AGENTS.md) and [research runbook](AGENT_BACKTEST_RUNBOOK.md)
- [Architecture and research design](docs/BKTSTR_SYSTEM_MANUAL.md)
- [Implementation plan](docs/IMPLEMENTATION_PLAN.md)
- [Current API reference](docs/API_REFERENCE.md)
- [Local credentials](docs/development/local-credentials.md)
- [Contribution and verification](CONTRIBUTING.md)

## Local development

Use Python 3.12.

```powershell
python -m pip install -r requirements-dev.txt
python -m bktstr.server
python -m pytest -q
python scripts/check_release_consistency.py
```

Historical market access uses `MASSIVE_API_KEY`; the research service uses
`BKTSTR_API_KEY`. Do not put either value in documentation or experiment records.
The limited Yahoo fallback is described in the API reference.

The configured production address is
[the BKTSTR service](https://bktstr-production.up.railway.app).
Verify authenticated capabilities and deployment identity before using it.
A documented address is not a claim of current deployment health.

GitHub Actions performs delivery checks. Railway's `RAILWAY_GIT_COMMIT_SHA`
is exposed as `git_commit` for deployment verification. See the
[release procedure](docs/development/releases.md).
