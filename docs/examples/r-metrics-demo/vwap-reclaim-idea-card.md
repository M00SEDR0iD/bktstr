# Idea card: vwap-reclaim

Status: research record; no live-trading approval.

## Primary outcomes

Iterate on net EV (R/trade). Review RR, Sharpe, maximum drawdown, sample size and held-out evidence alongside it. Higher EV alone does not promote a variant.

| Test / specification | Instrument | Period | EV (R/trade) | EV ($/trade) | Planned RR | Realized RR (R) | Daily Sharpe | Max drawdown (%) | Max drawdown ($) | Trades |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [vwap-policy @ 1.0.0](exp_79418ff0b7b54158a3714a9c5a5973a6-results.md) | SPY | validation / 2026-08-11 to 2026-08-13 | -1.0198 | -10.198 | 2 | Unavailable | -2207.82 | 2.14158 | 214.158 | 21 |
| [policy-volume @ 1.0.0](exp_a2ab6040055e4b76abe37e80dff6fc0b-results.md) | SPY | validation / 2026-08-11 to 2026-08-13 | -1.0198 | -10.198 | 2 | Unavailable | -32.0252 | 0.71386 | 71.386 | 7 |
| [policy-shorter-hold @ 1.0.0](exp_9c1dbf6c7cf844bb9e55dc47d5f75834-results.md) | SPY | validation / 2026-08-11 to 2026-08-13 | -1.0198 | -10.198 | 2 | Unavailable | -2207.82 | 2.14158 | 214.158 | 21 |
| [vwap-policy @ 1.0.0](exp_1a0295e85b65467ca63b0d805b4587e1-results.md) | QQQ | validation / 2026-08-11 to 2026-08-13 | -1.0198 | -10.198 | 2 | Unavailable | -2207.82 | 2.14158 | 214.158 | 21 |
| [policy-volume @ 1.0.0](exp_efcfddfb1d18496196b0ac0624e77c4e-results.md) | QQQ | validation / 2026-08-11 to 2026-08-13 | -1.0198 | -10.198 | 2 | Unavailable | -32.0252 | 0.71386 | 71.386 | 7 |
| [policy-shorter-hold @ 1.0.0](exp_a83db5d794ed4ddcb6aea77ed473c074-results.md) | QQQ | validation / 2026-08-11 to 2026-08-13 | -1.0198 | -10.198 | 2 | Unavailable | -2207.82 | 2.14158 | 214.158 | 21 |
| [vwap-policy @ 1.0.0](exp_f6ce323bb76e486c94c3175106e0de02-results.md) | SPY | final / 2026-08-14 to 2026-08-18 | -1.0198 | -10.198 | 2 | Unavailable | -2207.82 | 2.14158 | 214.158 | 21 |
| [vwap-policy @ 1.0.0](exp_121b56211822498fa4dea9c11ce1e943-results.md) | QQQ | final / 2026-08-14 to 2026-08-18 | -1.0198 | -10.198 | 2 | Unavailable | -2207.82 | 2.14158 | 214.158 | 21 |

Policy metrics require a trading simulation. Event studies retain forward-outcome statistics. Results stay separate by instrument and period; they are not a portfolio score.

Drawdown uses minute-close marked equity. Sharpe uses daily returns including inactive sessions, 252 sessions/year, and zero risk-free return. RR reports reward divided by risk.

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
| [5fb2712f](exp_5fb2712f1cc24a51b8033ac37a661dd3-results.md) | SPY | event_study | vwap-study | development | completed |
| [46bf63ad](exp_46bf63ade22448389f9b2417eee5a6b3-results.md) | SPY | event_study | study-participation | development | completed |
| [6330f6a8](exp_6330f6a87e3d4543ad42cf7e1e0ce6c7-results.md) | SPY | event_study | study-momentum | development | completed |
| [dc5744f4](exp_dc5744f4641743549dd2a5edc0e3e160-results.md) | QQQ | event_study | vwap-study | development | completed |
| [281e29bb](exp_281e29bbe505402cbcf5fa03ebd4c7e2-results.md) | QQQ | event_study | study-participation | development | completed |
| [4ca964d2](exp_4ca964d252d243a2aed34da332f41310-results.md) | QQQ | event_study | study-momentum | development | completed |
| [79418ff0](exp_79418ff0b7b54158a3714a9c5a5973a6-results.md) | SPY | configured_backtest | vwap-policy | validation | completed |
| [a2ab6040](exp_a2ab6040055e4b76abe37e80dff6fc0b-results.md) | SPY | configured_backtest | policy-volume | validation | completed |
| [9c1dbf6c](exp_9c1dbf6c7cf844bb9e55dc47d5f75834-results.md) | SPY | configured_backtest | policy-shorter-hold | validation | completed |
| [1a0295e8](exp_1a0295e85b65467ca63b0d805b4587e1-results.md) | QQQ | configured_backtest | vwap-policy | validation | completed |
| [efcfddfb](exp_efcfddfb1d18496196b0ac0624e77c4e-results.md) | QQQ | configured_backtest | policy-volume | validation | completed |
| [a83db5d7](exp_a83db5d794ed4ddcb6aea77ed473c074-results.md) | QQQ | configured_backtest | policy-shorter-hold | validation | completed |
| [f6ce323b](exp_f6ce323bb76e486c94c3175106e0de02-results.md) | SPY | configured_backtest | vwap-policy | final | completed |
| [121b5621](exp_121b56211822498fa4dea9c11ce1e943-results.md) | QQQ | configured_backtest | vwap-policy | final | completed |

## Blocked admissions

None recorded.

## Assessment history

### synthetic acceptance demonstration

Inconclusive for real markets. Proceed only to verify the policy workflow.

Limitations: All observations are manufactured fixtures; no investment conclusion.

Evidence: [exp_5fb2712f1cc24a51b8033ac37a661dd3](exp_5fb2712f1cc24a51b8033ac37a661dd3-results.md), [exp_46bf63ade22448389f9b2417eee5a6b3](exp_46bf63ade22448389f9b2417eee5a6b3-results.md), [exp_6330f6a87e3d4543ad42cf7e1e0ce6c7](exp_6330f6a87e3d4543ad42cf7e1e0ce6c7-results.md), [exp_dc5744f4641743549dd2a5edc0e3e160](exp_dc5744f4641743549dd2a5edc0e3e160-results.md), [exp_281e29bbe505402cbcf5fa03ebd4c7e2](exp_281e29bbe505402cbcf5fa03ebd4c7e2-results.md), [exp_4ca964d252d243a2aed34da332f41310](exp_4ca964d252d243a2aed34da332f41310-results.md)


## Search history

14 recorded experiments; 6 distinct specification revisions.

| Research family | Candidates used / budget | Attempts used / budget | Budget amendments |
| --- | --- | --- | --- |
| vwap-reclaim:backtest | 3 / 3 | 8 / 8 | 0 |
| vwap-reclaim:study | 3 / 3 | 6 / 6 | 0 |

A failed or inconclusive study remains part of this card. Results are specific to the tested inputs.
