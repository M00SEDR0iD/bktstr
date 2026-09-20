# Point-in-time macro evidence

Task 2 provides a local evidence interface. It does not enable macro gates in
strategy documents, call Jev, run a scheduler, or place trades. Those consumers
belong to later tasks in the [implementation plan](IMPLEMENTATION_PLAN.md).

## Selection and replay

`EvidenceSnapshot` preserves source and series identity, numerical value and units,
observation time, publication time, ingestion time, earliest availability, vintage,
source payload, trust tier, content digest, and record ID. Times must have explicit
UTC offsets and are normalized to UTC. A monthly observation time identifies the
reference period; it is not its release time.

`select_as_of(snapshots, cutoff, mode)` selects the latest usable version for each
source/series/observation. The two modes are deliberately distinct:

| Mode | Earliest use | Required historical evidence |
| --- | --- | --- |
| `historical_publication` | Publication and declared availability | Publication timestamp and an explicit vintage |
| `prospective_receipt` | Receipt, declared availability, and publication if known | A record actually received by the cutoff |

A late-arriving older revision cannot overwrite a newer published revision.
Exact duplicate deliveries are idempotent; conflicting records for the same
vintage fail. Missing latest values remain missing rather than falling back to
the previous release. Events are compared as absolute timestamps, including
weekends and daylight-saving transitions; selection does not shift a release
onto a trading session.

The domain validates supplied provenance, but cannot prove a caller's claimed
publication timestamp or vintage. Each provider must establish those guarantees.
Do not manufacture a vintage or infer publication from a release schedule.

`build_packet` requires an explicit positive `max_age`. It freezes selected source
records, normalized values, deterministic changes, and optional actual-minus-
expectation differences. Missing expectations produce null surprise. An expectation
must match the observation and have been usable before an explicitly identified
initial release (`release_kind="initial"`). Later actual or forecast revisions
cannot move this deadline. Without the initial-release record, surprise remains
unavailable. For a revised actual, the difference is revised-actual minus the
original forecast, not the surprise observed at the initial announcement.
Percent, basis-point, and fraction values normalize to percentage points; indexes,
USD, and counts retain their units. Incompatible comparisons fail. Numerical
context has a Tier B floor and inherits any lower trust from its inputs.

Freshness uses publication time when known, otherwise observation time. This is
conservative for prospective-only sources and prevents repeated downloads from
making old observations fresh. Missing, stale, or ambiguous supplied series fail
packet construction. Limit inputs to the context the strategy actually needs.
The prior observation used for a change can be older than `max_age`; the current
observation must be fresh. Both source records remain in packet provenance.

`EvidenceStore` appends immutable records to an explicit SQLite path, separately
from bar and feature caches. Batch writes are atomic; reads verify record hashes.
Packets can be rebuilt offline with the same snapshots, cutoff, mode, freshness
policy, and expectation mapping. The caller owns the persistent directory and
backup policy. No background collection is started automatically.

## First provider: BLS public API v1

Verified September 20, 2026: an unauthenticated request returned `REQUEST_SUCCEEDED`
for `CUUR0000SA0`, CPI-U all items, U.S. city average, not seasonally adjusted,
index base 1982-84 = 100. The adapter accepts only this series. The recorded
response contains 32 monthly observations and two annual-average rows; annual
averages are excluded. This is a current-vintage download, not a historical
release archive.

| Check | Verified coverage and limitation |
| --- | --- |
| Access | API v1 requires no registration; single-series GET supplies its default three-year window. One live request and fixture parsing were verified. |
| Retention | BLS publishes its data as public-domain material and asks for attribution. Source rows may be retained in the evidence store. |
| Publication timestamps | The time-series response contains year, period, value, and footnotes, without a per-observation release timestamp. The adapter records publication as unavailable. |
| Revision history | The response has no as-of vintage selector/history. CPI-U is generally final when issued, but BLS can correct errors; that does not establish archived intraday vintages. The adapter records vintage as unavailable. |
| Canonical historical use | Rejected. This adapter is prospective-only, usable after receipt. |
| Unsupported | Consensus forecasts, seasonally adjusted CPI, other datasets, event streaming, historical release reconstruction, and latency guarantees. |

The live response is preserved in
[the recorded fixture](../tests/fixtures/macro/bls_cpi_recorded.json). Release,
revision, and delayed-receipt boundary tests use
[explicitly synthetic records](../tests/fixtures/macro/revisions.json).

Sources checked: [BLS API getting started](https://www.bls.gov/developers/),
[v1 signatures](https://www.bls.gov/developers/api_signature.htm),
[Python response schema](https://www.bls.gov/developers/api_python.htm),
[copyright and reuse](https://www.bls.gov/bls/linksite.htm), and
[CPI corrections policy](https://www.bls.gov/cpi/questions-and-answers.htm).

## Local use

```python
import asyncio
from datetime import datetime, timedelta, timezone
from bktstr.providers import BLSMacroProvider
from bktstr.variable_store import EvidenceStore
from bktstr.evidence_packets import build_packet

async def collect():
    snapshots = await BLSMacroProvider().fetch_snapshots("CUUR0000SA0")
    store = EvidenceStore("research-data/macro.sqlite3")
    store.put_many(snapshots)
    return build_packet(
        store.load(), datetime.now(timezone.utc), "prospective_receipt",
        max_age=timedelta(days=60),
        required_series=("macro.bls.cpi_u_all_items_nsa",),
    )

packet = asyncio.run(collect())
```

The example's 60-day freshness limit is an explicit illustrative policy for a
monthly series. It is not a recommended trading threshold. Preserve the packet's
cutoff and inputs for replay. Wiring packets into registered strategy filters
and durable experiments is still pending.
