# Server research storage implementation plan

Approved design: recipes and structured results live on the server; HTML and
Markdown are generated on request without market data or execution. Fresh-data
reruns create linked experiments. Exact offline replay is optional and requires
retained inputs and the original numerical build.

Architecture: keep FastAPI, SQLite, the existing worker and a persistent Railway
volume. Keep dataset metadata and acquisition recipes in SQLite independently of
temporary snapshot files. Retain study artifacts and policy trade/equity results.
No object store or database migration is necessary for the present workload.

## Tasks

- [x] Separate report rendering from optional file export. Remove automatic worker
  publication. Test rendering after snapshot eviction and absence of report files.
- [x] Add dataset inventory, source metadata, pin/unpin, retention preview/apply,
  and scheduled maintenance. Protect pending work, protocols, uploads, backups,
  and active acquisitions; never delete results or research history.
- [x] Add explicit Massive acquisition recipes and fresh reruns that bypass raw
  cache, retain parent lineage and resolve a new immutable application. Keep
  original protocols visible but classify fresh reruns as exploratory, not new
  independent final evidence. Test idempotency, fetch failures and fresh results.
- [x] Provide authenticated storage and acquisition/rerun APIs, server persistence
  checks, backup/export and merge-safe import of local research archives.
- [x] Update current docs, version contracts and production acceptance. Run full
  tests, release checks, compile and benchmark; obtain independent code review.
- [ ] Push a focused PR, pass CI, merge, verify deployed commit and authenticated
  acceptance, migrate local research without replacing existing server records,
  verify reports and backup restoration, then publish the release.

## Constraints and verification

Preserve immutable revisions, all attempts, budgets and exposure records. No raw
credentials in artifacts. Retention defaults to 30 days for explicitly reacquirable
datasets; uploaded/unknown sources remain pinned. Dry-run cleanup precedes apply.
Keep a SQLite metadata tombstone after eviction. All destructive file actions
must remain within the research dataset/report directory and reject symlinks.
Reports must work without provider access or input snapshots. Acquisition failure
must be durable; retries with one idempotency key must not fetch twice. Frozen
controlled campaigns continue to share one dataset; rolling research needs a new
explicit session schedule, never inferred weekdays or approximate market hours.

## Progress

Implementation starts from e29b089d on the existing dedicated feature branch.
Unrelated tracked temporary-file deletions in the checkout are outside this work.
The user authorized implementation, push, merge and production publication.

Review fixes: acquisition application/checkpoint commit together; internal backups
are independent of transfer size limits; public archive access records exposure;
rerun reports check resolved inputs. Older conflicting archives are preserved
separately with exposure history, rather than overwriting immutable identities.

Verification: 619 full-suite tests passed before final vault fault fixes; the final
39 focused storage/report/archive tests passed. Release consistency, compilation,
and 120,000-row cache benchmark passed. Independent review findings have regression
coverage. All seven GitHub CI jobs passed before PR #19 merged.

Production acceptance on merge b647b932 passed: authenticated baseline backtest
and comparison, fresh Massive acquisition and linked rerun, configured backtest,
unchanged original results, saved HTML/Markdown reports and application backup.
The persistent Railway volume was verified. Fourteen current runs were imported
and fourteen historical runs preserved separately; every imported result matched
its original. Both server archives downloaded and restored into isolated stores.

Railway currently requires a manual upstream update; auto deploy is unavailable.
Its UI reported one day or $2.46 remaining on the trial. Provider-managed backups
require Pro; application backups share the attached volume. Billing and an
independent scheduled backup destination remain operational follow-ups.

A final migration CLI correction accepts the historical archive endpoint's
201 Created response. Its regression and archive tests passed (24 tests).
