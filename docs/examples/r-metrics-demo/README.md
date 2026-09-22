# Synthetic research demonstration

This demonstrates software behavior. Every price is synthetic; these results are not evidence of a trading edge.

[Open the visual idea card](vwap-reclaim-idea-card.html) · [Markdown export](vwap-reclaim-idea-card.md)

Study campaign: completed, 6 attempts.

Policy campaign: completed, 8 attempts.

Development, validation, and final sessions are chronological and disjoint.

The two artificial instruments use scaled versions of the same prices. Matching results demonstrate consistent application, not independent market confirmation.

Each policy split has only three synthetic sessions. Extremely large Sharpe values reflect this artificial, low-variance sample and cannot establish market performance.

## Study comparisons

Differences are candidate minus baseline mean five-minute return, in percentage points. Intervals use session-block resampling and remain exploratory.

| Variation | Instrument | Difference | Interval | Common / added / removed events |
| --- | --- | --- | --- | --- |
| study-participation | SPY | -0.001584 | -0.008659 to 0.003217 | 21 / 0 / 25 |
| study-momentum | SPY | 0.000177 | 0.000000 to 0.000739 | 43 / 0 / 3 |
| study-participation | QQQ | -0.001584 | -0.008659 to 0.003217 | 21 / 0 / 25 |
| study-momentum | QQQ | 0.000177 | 0.000000 to 0.000739 | 43 / 0 / 3 |

## Policy comparisons

Validation-period differences are candidate minus baseline net EV in R/trade. Each instrument is tested independently. The idea card shows RR, daily Sharpe, and marked-equity drawdown alongside EV.

| Variation | Instrument | EV difference (R/trade) | Status |
| --- | --- | --- | --- |
| policy-volume | SPY | 0.000000 | descriptive |
| policy-shorter-hold | SPY | 0.000000 | descriptive |
| policy-volume | QQQ | 0.000000 | descriptive |
| policy-shorter-hold | QQQ | 0.000000 | descriptive |

## Assessment

The workflow completed and retained every declared attempt. These manufactured observations support no market conclusion. Review the linked test reports for exact rules, dates, assumptions, limitations, and replay references.
