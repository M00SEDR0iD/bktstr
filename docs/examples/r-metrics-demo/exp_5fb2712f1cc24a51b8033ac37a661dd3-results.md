# Test results: exp_5fb2712f1cc24a51b8033ac37a661dd3

Status: **completed**

Operation: event_study

Idea: vwap-reclaim

Period: 2026-08-03T13:30:00+00:00 to 2026-08-10T14:05:00+00:00

## What was tested

Specification: vwap-study at 1.0.0

Application: spy

Protocol: id: demo-event-study; replication: once; split: development; stage: development

## Observations

Forward observations, not executable trading profit.

Eligible events: 46

| Measure | Result |
| --- | --- |
| Primary label | return_5m |
| Usable | 41 |
| Sessions | 6 |
| Blocks | 6 |
| Mean (%) | 0.131088 |
| Median (%) | 0.139115 |
| Mean interval (%) | 0.129222, 0.135058 |
| Uncertainty status | estimated |
| Context difference | description: Highest context group minus lowest; association, not causal effect.; estimate: -0.0027251; interval: -0.013821, 0.00562973 |
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
  "event_rules": "close.cross_above:vwap",
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
    "digest": "ed62f3debba9d4b934cc5df35db21ca020cb04c2cfa468e0596b7a61137828e1",
    "id": "spy",
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
    "digest": "f25c44d0fe449220c301c5ce8b2f14fdddf6d1967182389670f13705916b4ca2",
    "id": "vwap-study",
    "version": "1.0.0"
  },
  "start": "2026-08-03T13:30:00+00:00"
}
```

## Artifact references

```json
{
  "events_artifact": "d190f8739d38ea401680744e2897ff71bc431d217d46177c7938f5181d7a3b82",
  "labels_artifact": "53a6b8790ccfe5091780380cb3fe430590b689e4ce3423e572404ded902cced5"
}
```
