# Test results: exp_81ab6a3083ef4d81bf8453e1a8ba75fd

Status: **completed**

Operation: event_study

Idea: vwap-reclaim

Period: 2026-08-03T13:30:00+00:00 to 2026-08-10T14:05:00+00:00

## What was tested

Specification: study-participation at 1.0.0

Application: qqq

Protocol: id: demo-event-study; replication: once; split: development; stage: development

## Observations

Forward observations, not executable trading profit.

Eligible events: 21

| Measure | Result |
| --- | --- |
| Primary label | return_5m |
| Usable | 16 |
| Sessions | 6 |
| Blocks | 6 |
| Mean (%) | 0.129504 |
| Median (%) | 0.139052 |
| Mean interval (%) | 0.120671, 0.132497 |
| Uncertainty status | estimated |
| Context difference | description: Highest context group minus lowest; association, not causal effect.; estimate: Unavailable; interval: Unavailable |
| Censored | session boundary: 5 |

Percent outcomes use the event close as reference. Confidence intervals do not establish profitability.

### Exact study definition

```json
{
  "component_version": "1.0.0",
  "contexts": [
    "volume_ratio20",
    "rsi14"
  ],
  "event_rules": "close.cross_above:vwap,volume_ratio20.gt:1",
  "id": "vwap-study",
  "labels": [
    {
      "boundary": "censor",
      "id": "return_5m",
      "kind": "return",
      "minutes": 5,
      "reference": "event_close"
    },
    {
      "boundary": "censor",
      "id": "mfe_5m",
      "kind": "mfe",
      "minutes": 5,
      "reference": "event_close"
    },
    {
      "boundary": "censor",
      "id": "mae_5m",
      "kind": "mae",
      "minutes": 5,
      "reference": "event_close"
    }
  ],
  "macro_mode": "none",
  "sampling": "all",
  "version": "1.0.0"
}
```

## Limitations

- Session-block resampling assumes the declared block length captures dependence.
- Exploratory intervals do not adjust for the number of hypotheses searched.
- Forward observations do not include executable entry prices or trading costs.
- Synthetic demonstrations verify behavior; they are not market evidence.
- All inspected results remain in the archive. Repeated tuning does not create a fresh holdout.

## Replay

Use the stored request with the pinned data and original numerical build. No network fallback is allowed.

Dataset digest: 0a82d27ff95e3406c71be379f69889c4d9d8a9fd9cb12b5b9995ceac34699df5

Numerical build: 03793650fd52a2480aa509612339c5583ad419dabfdd27dbeea3ca533c69ce78

```json
{
  "analysis": {
    "grouping": {
      "context": "volume_ratio20",
      "edges": [
        1.0
      ]
    },
    "label": "return_5m"
  },
  "application": {
    "digest": "f25e374161984b43bc00c66eda5dda9cc0a359e55c0f93babb721ca4111a791b",
    "id": "qqq",
    "version": "1.0.0"
  },
  "end": "2026-08-10T14:05:00+00:00",
  "idea": {
    "digest": "2c2d5a609c69bba1a999454dbc5aa87a09d4f89807d729d475b7229b3b8e7b2b",
    "id": "vwap-reclaim",
    "version": "1.0.0"
  },
  "operation": "event_study",
  "protocol": {
    "id": "demo-event-study",
    "replication": "once",
    "split": "development",
    "stage": "development"
  },
  "specification": {
    "digest": "28696f83b74bcbf077a1c97971294b6de9b4dbb6a577b7ba283b5b6502de772f",
    "id": "study-participation",
    "version": "1.0.0"
  },
  "start": "2026-08-03T13:30:00+00:00"
}
```

## Artifact references

```json
{
  "events_artifact": "c692fde9554572a42d9f8f42015edd2c462ced1696a0adbc311534cb93fae79c",
  "labels_artifact": "a85331d168ec71d0ef49ff507d98a7d1915546fad1e69fb64968887a008c9716"
}
```
