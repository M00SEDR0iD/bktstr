# Server research storage

Production is the authoritative research archive. GitHub stores code, documentation
and small synthetic examples. Use the authenticated server API for ongoing research;
local research is explicit development work.

| Record | Retention |
| --- | --- |
| Idea, strategy, modifier and application revisions | Permanent |
| Every attempt, failure, result, trade, equity series and metric definition | Permanent |
| Study events/labels, protocols, budgets and inspection history | Permanent |
| Dataset source, schedule, acquisition recipe and build | Permanent |
| Reacquirable input snapshots | 30 days unless pinned or protected by a protocol |
| Uploaded, synthetic or unknown-source snapshots | Pinned by default |
| HTML and Markdown | Rendered on request; explicit file exports still available |

## Retention controls

`GET /api/v1/research/storage` lists dataset bytes, availability, recipes and pins,
plus volume and backup status. `POST /api/v1/research/datasets/{digest}/pin` takes
`{"pinned": true}` or `false`. Unpinning an upload gives up retaining its unique
inputs; it does not invent a provider recipe.

`POST /api/v1/research/storage/cleanup` with `{}` previews expiry. With
`{"apply": true}` it deletes eligible snapshot files, retaining metadata and results.
Queued/running work blocks eviction. Frozen protocols protect their datasets.
Pin/eviction actions are logged. This policy covers research snapshots; the legacy
baseline raw/derived provider cache is separate and not used by fresh-data reruns.

## View versus rerun

`GET /api/v1/ideas/{id}/html`, `/markdown`, and
`GET /api/v1/experiments/{id}/markdown` render saved results without fetching data
or executing a strategy. They write no server report files. Viewing results records
research exposure. Input expiry does not erase historical reports.

`POST /api/v1/experiments/{id}/rerun` with `{}` and a new `Idempotency-Key` retrieves
fresh data using the saved acquisition recipe. It creates a linked exploratory
attempt; it never overwrites its parent or claims a new independent final test.
The same key returns the same attempt. Provider failure is a saved failed attempt.
The submitted application identifies the original binding; the result's application
and provenance identify the newly acquired snapshot and resolved application.
A restarted attempt resumes its acquired snapshot when available.

The acquisition provider is Massive, using adjusted one-minute bars. There is no
cache/provider fallback. Acquisition requires explicit session schedules, including
early closes. Missing bars are rejected by default; `missing_data: "record"` permits
incomplete exploratory data, never controlled use. Dates stay fixed unless the
caller supplies a new schedule and `start`/`end`. Automatic rolling-calendar
resolution is not implemented.

Acquire an initial dataset through `POST /api/v1/research/datasets/acquire`:

```json
{
  "provider": "massive",
  "symbols": ["NVDA"],
  "timeframe": "1m",
  "adjustment": "adjusted",
  "schedule_source": "explicit verified XNYS session schedule",
  "schedule": [{"date": "2026-08-17", "open": "2026-08-17T13:30:00Z", "close": "2026-08-17T20:00:00Z"}],
  "missing_data": "reject"
}
```

Register an application referencing the returned dataset, then submit studies or
configured policies. To rerun an old upload, supply this recipe as `acquisition`;
its provider origin cannot be inferred from synthetic data. Compare variants on one
acquired dataset. Record data/build differences before attributing changed EV to a
strategy change. Exact offline `replay_research` requires retained inputs and the
original numerical build; it never falls back to acquisition.

## Production and recovery

SQLite and research artifacts use the existing Railway persistent volume. Railway
startup rejects a missing volume or an experiment directory outside it. One process
owns the worker lease; multi-replica SQLite operation is outside this release.

Idle maintenance checks hourly and makes a compressed daily archive before cleanup.
Seven days of backups are retained on the volume. These protect against application
mistakes, not volume loss: download archives elsewhere and enable Railway volume
backups separately. `POST /api/v1/research/storage/backup` refreshes today's backup
and performs cleanup.

Authenticated archive export/import moves local records online without replacing
the server database. Imports are additive and reject conflicting immutable identities.
They preserve original builds and metrics. Use `python -m scripts.research_transfer
--help` for export, upload and download; run it through the
[credential helper](development/local-credentials.md), never with a key argument.

Acceptance must verify deployment identity, authenticated reports, fresh acquisition,
saved-result retrieval, persistent-volume status and restoration of a downloaded
archive into a separate store. Health alone is insufficient.

## Historical archives with conflicting identifiers

If older local archives reused revision IDs for different content, keep them as
separate immutable historical archives. `POST /api/v1/research/archives` preserves
a verified transfer bundle; `GET` lists preserved archives. Download one through
`GET /api/v1/research/archives/{digest}`, or view its saved card through
`GET /api/v1/research/archives/{digest}/ideas/{idea}/html`. Viewing/downloading
records exposure in the active catalog. No input retrieval or test execution occurs.

Historical budgets and attempts stay in their original archive; they are not active
campaigns or combined counters. Active-catalog JSON exports and daily JSON backups
exclude these separate bundles. Full `backup_research` and Railway volume backups
include the archive directory. Download each historical archive separately for
off-volume backup. Nothing in the vault is automatically culled.
