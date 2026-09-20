# BKTSTR agent instructions

## Purpose and scope

BKTSTR is an independent research engine, separate from the Bailey Fund.
Do not import fund-specific holdings, portfolio metrics, allocations, mandates,
or account assumptions into defaults, documentation, examples, or evaluations.

Build toward configurable deterministic strategies, optional Jev macro
classification through OpenRouter, reproducible comparisons, and bounded paper
testing. Prioritize minute bars and holding periods of minutes to hours.
The existing bearish-regime strategy is one baseline, not a required worldview.

## Read in this order

1. [Documentation index](docs/README.md)
2. [System design](docs/BKTSTR_SYSTEM_MANUAL.md)
3. [Implementation plan](docs/IMPLEMENTATION_PLAN.md)
4. [Research runbook](AGENT_BACKTEST_RUNBOOK.md)
5. [Current API](docs/API_REFERENCE.md) when making requests

The design describes intended behavior; the API reference describes implemented
behavior. Inspect source and authenticated capabilities before assuming a feature
exists. No Jev, macro-feed, paper-runner, or Clear Street feature is currently
implemented. This documentation pass does not authorize live-money trading.

Local numerical strategy documents are implemented through
[strategy configuration](docs/STRATEGY_CONFIGURATION.md). Keep their runtime on
the shared orchestrator; the HTTP baseline registry remains a separate public
contract. Model/question metadata in a disabled policy is not executed.

## Research invariants

- Freeze strategy configuration, question definitions, data versions, and execution
  assumptions for a run. Revisions create new versions and experiments.
- Compute numerical indicators in code. Use Jev only for explicitly defined
  judgments with supplied evidence and bounded answer choices.
- Preserve publication, availability, revision, and observation timestamps.
  Later data and later model responses must not influence earlier decisions.
- Model outputs are lower-trust evidence. Confidence is not a win probability.
  Do not promote model-derived values into trusted deterministic measurements.
- Replay persisted Jev responses without network calls. Fresh inference is a
  separate acquisition run, even when a model identifier is unchanged.
- Log accepted and rejected signals with evidence and reasons.
- Keep risk, sizing, exits, costs, and execution in deterministic code.
  Missing/stale evidence blocks new entries; protective management continues.
- Compare each added filter against a baseline on aligned inputs and held-out
  periods. Record all attempted variants, not only winners.
- Keep feature caches separate from model-response records and decision logs.

## Working rules

Use the existing FastAPI, Python, SQLite, worker, and cache architecture unless
a measured requirement warrants a change. Preserve public contracts and baseline
behavior unless a versioned change is explicitly part of the task.

Use the credential helper documented in
[local credentials](docs/development/local-credentials.md). Never print secrets
or put them in prompts, logs, URLs, artifacts, or committed files. The helper
currently handles BKTSTR credentials only, not OpenRouter or broker secrets.

Follow [CONTRIBUTING.md](CONTRIBUTING.md). Inspect scoped changes before editing;
do not clean unrelated generated files or user work. Do not treat old Git history
as an active roadmap. Update the relevant current reference when behavior changes.
