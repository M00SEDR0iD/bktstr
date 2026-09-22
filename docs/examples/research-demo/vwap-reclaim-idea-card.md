# Idea card: vwap-reclaim

Status: research record; no live-trading approval.

## Continuation after a VWAP reclaim / 1.0.0

### Thesis

A same-session close crossing above VWAP may precede continuation.

### Proposed mechanism

Participation returning above the session average may sustain direction.

### Disproof criteria

Reject if forward differences do not persist across held-out sessions and instruments, or a policy fails after costs.

### Applicability

Liquid equity/ETF minute bars; portability must be tested.

## Research specification

First tested event rule: `close.cross_above:vwap`

Context: volume_ratio20, rsi14.

| Outcome | Measurement | Horizon |
| --- | --- | --- |
| return_5m | return from event close | 5 minutes |
| mfe_5m | mfe from event close | 5 minutes |
| mae_5m | mae from event close | 5 minutes |

Future outcomes are separate from decision-time inputs. Missing and boundary-crossing outcomes remain visible in the test reports.

## Categorized variations

- policy / risk: policy-shorter-hold. Declared policy sensitivity

```json
{
  "risk": {
    "max_hold_minutes": 3
  }
}
```

- policy / entry: policy-volume. Declared policy sensitivity

```json
{
  "entry": {
    "rules": "close.cross_above:vwap,volume_ratio20.gt:1"
  }
}
```

- study / technical_context: study-momentum. Inspect a declared context selection

```json
{
  "event_rules": "close.cross_above:vwap,rsi14.gt:50"
}
```

- study / technical_context: study-participation. Inspect a declared context selection

```json
{
  "event_rules": "close.cross_above:vwap,volume_ratio20.gt:1"
}
```


| Variant | Kind | Based on | Modifiers |
| --- | --- | --- | --- |
| policy-shorter-hold | policy | vwap-policy @ 1.0.0 | policy-shorter-hold |
| policy-volume | policy | vwap-policy @ 1.0.0 | policy-volume |
| study-momentum | study | vwap-study @ 1.0.0 | study-momentum |
| study-participation | study | vwap-study @ 1.0.0 | study-participation |

## Tests and results

| Test | Instrument | Kind | Specification | Period | Status |
| --- | --- | --- | --- | --- | --- |
| [7be8d536](exp_7be8d53664a34d1789e00d196216075f-results.md) | SPY | event_study | vwap-study | development | completed |
| [9c0eebe6](exp_9c0eebe640bd428cab81d4e2bc7230b6-results.md) | SPY | event_study | study-participation | development | completed |
| [babba58c](exp_babba58c3f394aa2bdae99dc0f0c87f4-results.md) | SPY | event_study | study-momentum | development | completed |
| [8c1155bb](exp_8c1155bbe2684ccabbbd07b6b881050e-results.md) | QQQ | event_study | vwap-study | development | completed |
| [81ab6a30](exp_81ab6a3083ef4d81bf8453e1a8ba75fd-results.md) | QQQ | event_study | study-participation | development | completed |
| [f821ee68](exp_f821ee683bd549c5822d164807b98e59-results.md) | QQQ | event_study | study-momentum | development | completed |
| [ab3dfb12](exp_ab3dfb12a3594c0ba676e0edda07965d-results.md) | SPY | configured_backtest | vwap-policy | validation | completed |
| [4e7f8427](exp_4e7f8427952247ac881d20aeb784e1c9-results.md) | SPY | configured_backtest | policy-volume | validation | completed |
| [bd1a18ef](exp_bd1a18ef5e014f31bfab93d32240349a-results.md) | SPY | configured_backtest | policy-shorter-hold | validation | completed |
| [bacec717](exp_bacec7176df64fa09fd1e61a8bc4729e-results.md) | QQQ | configured_backtest | vwap-policy | validation | completed |
| [1c3ee8d1](exp_1c3ee8d119d14dad9a83fb2f5bc29d2d-results.md) | QQQ | configured_backtest | policy-volume | validation | completed |
| [d18bb22e](exp_d18bb22ebf4c45678dda396d0b2041be-results.md) | QQQ | configured_backtest | policy-shorter-hold | validation | completed |
| [7c8c4550](exp_7c8c45502fe9487c9eb984a957ea5170-results.md) | SPY | configured_backtest | vwap-policy | final | completed |
| [0c189d12](exp_0c189d1253774a85adca9914a56d00da-results.md) | QQQ | configured_backtest | vwap-policy | final | completed |

## Blocked admissions

None recorded.

## Assessment history

### synthetic acceptance demonstration

Inconclusive for real markets. Proceed only to verify the policy workflow.

Limitations: All observations are manufactured fixtures; no investment conclusion.

Evidence: [exp_7be8d53664a34d1789e00d196216075f](exp_7be8d53664a34d1789e00d196216075f-results.md), [exp_9c0eebe640bd428cab81d4e2bc7230b6](exp_9c0eebe640bd428cab81d4e2bc7230b6-results.md), [exp_babba58c3f394aa2bdae99dc0f0c87f4](exp_babba58c3f394aa2bdae99dc0f0c87f4-results.md), [exp_8c1155bbe2684ccabbbd07b6b881050e](exp_8c1155bbe2684ccabbbd07b6b881050e-results.md), [exp_81ab6a3083ef4d81bf8453e1a8ba75fd](exp_81ab6a3083ef4d81bf8453e1a8ba75fd-results.md), [exp_f821ee683bd549c5822d164807b98e59](exp_f821ee683bd549c5822d164807b98e59-results.md)


## Search history

14 recorded experiments; 6 distinct specification revisions.

| Research family | Candidates used / budget | Attempts used / budget | Budget amendments |
| --- | --- | --- | --- |
| vwap-reclaim:backtest | 3 / 3 | 8 / 8 | 0 |
| vwap-reclaim:study | 3 / 3 | 6 / 6 | 0 |

A failed or inconclusive study remains part of this card. Results are specific to the tested inputs.
