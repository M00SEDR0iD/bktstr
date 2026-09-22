# Test results: exp_281e29bbe505402cbcf5fa03ebd4c7e2

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

Dataset digest: 213426cb8342dd58ba5942f501014990a01e57d9b8c07836fbc82a7a6dc78c2b

Numerical build: 433e6500c7b43fee70aab624428bad257cdfce9ddeafab385cc7e35ed4c25df1

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
    "digest": "18bb4176698d49ae506099d9f0a4f56808f593bf3720740b3f3c8f97cb8ee6ce",
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
  "events_artifact": "537497b0f90e7d92e583dbca7993d7160ddc52496f4b67f198f6ce3d3197e02f",
  "labels_artifact": "7602e79a5831359a2eec5b84fcf1023052fb68c849e27c9b9d8109db4297f236"
}
```
