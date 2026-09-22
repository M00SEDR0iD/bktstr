# Test results: exp_ab3dfb12a3594c0ba676e0edda07965d

Status: **completed**

Operation: configured_backtest

Idea: vwap-reclaim

Period: 2026-08-11T13:30:00+00:00 to 2026-08-13T14:05:00+00:00

## What was tested

Specification: vwap-policy at 1.0.0

Application: spy

Protocol: id: demo-policy; replication: once; split: validation; stage: validation

## Simulated trading results

| Measure | Result |
| --- | --- |
| Average return pct | -1.0198 |
| Ending equity | 9785.84 |
| Expected pnl per trade | -10.198 |
| Losses | 21 |
| Max drawdown pct | -2.14158 |
| Total pnl dollars | -214.158 |
| Trades | 21 |
| Win rate pct | 0 |
| Wins | 0 |

### Policy and rationale

```json
{
  "contrary_evidence": [
    "exp_7be8d53664a34d1789e00d196216075f",
    "exp_9c0eebe640bd428cab81d4e2bc7230b6",
    "exp_babba58c3f394aa2bdae99dc0f0c87f4",
    "exp_8c1155bbe2684ccabbbd07b6b881050e",
    "exp_81ab6a3083ef4d81bf8453e1a8ba75fd",
    "exp_f821ee683bd549c5822d164807b98e59"
  ],
  "evidence": [
    "exp_7be8d53664a34d1789e00d196216075f",
    "exp_9c0eebe640bd428cab81d4e2bc7230b6",
    "exp_babba58c3f394aa2bdae99dc0f0c87f4",
    "exp_8c1155bbe2684ccabbbd07b6b881050e",
    "exp_81ab6a3083ef4d81bf8453e1a8ba75fd",
    "exp_f821ee683bd549c5822d164807b98e59"
  ],
  "id": "vwap-policy",
  "limitations": "Synthetic data, simplified execution, independent symbols.",
  "rationale": "Workflow demonstration only; synthetic studies cannot justify a real trading edge.",
  "recipe": {
    "entry": {
      "rules": "close.cross_above:vwap",
      "side": "long"
    },
    "execution": {
      "id": "bktstr.next-bar-open",
      "slippage_bps": 2,
      "version": "1.0.0"
    },
    "falsification": "Reject if held-out comparisons fail after execution costs. Macro evidence will be added in a later task.",
    "filters": [],
    "hypothesis": "Simulation research: a close above VWAP may precede a short intraday continuation.",
    "model_policy": {
      "enabled": false,
      "model": null,
      "question": null
    },
    "risk": {
      "max_hold_minutes": 5,
      "position_size": 1000,
      "starting_capital": 10000,
      "stop_pct": 1,
      "target_pct": 2
    },
    "schema_version": "1.0.0",
    "session": {
      "entry_end_time": "16:00",
      "entry_start_time": "09:30"
    },
    "strategy_id": "bktstr.minute-strategy",
    "strategy_version": "1.0.0"
  },
  "status": "candidate",
  "version": "1.0.0"
}
```

## Limitations

- Fixed-bps costs and next-bar execution; existing stop/gap assumptions remain.
- Independent symbol simulation, not a shared-cash portfolio.
- Synthetic demonstrations verify behavior; they are not market evidence.
- All inspected results remain in the archive. Repeated tuning does not create a fresh holdout.

## Replay

Use the stored request with the pinned data and original numerical build. No network fallback is allowed.

Dataset digest: 0a82d27ff95e3406c71be379f69889c4d9d8a9fd9cb12b5b9995ceac34699df5

Numerical build: 03793650fd52a2480aa509612339c5583ad419dabfdd27dbeea3ca533c69ce78

```json
{
  "analysis": null,
  "application": {
    "digest": "56e9020008e4cf8814434eaa59d6a9e6b4b76cc2f283aba64ba431e135fe6f04",
    "id": "spy",
    "version": "1.0.0"
  },
  "end": "2026-08-13T14:05:00+00:00",
  "idea": {
    "digest": "2c2d5a609c69bba1a999454dbc5aa87a09d4f89807d729d475b7229b3b8e7b2b",
    "id": "vwap-reclaim",
    "version": "1.0.0"
  },
  "operation": "configured_backtest",
  "protocol": {
    "id": "demo-policy",
    "replication": "once",
    "split": "validation",
    "stage": "validation"
  },
  "specification": {
    "digest": "2cdf6ef62f842617b4c061bcd082cf4bf92a50486420c7255cd1f4dff4754f4f",
    "id": "vwap-policy",
    "version": "1.0.0"
  },
  "start": "2026-08-11T13:30:00+00:00"
}
```

## Artifact references

```json
{}
```
