# Merge / Deployment Checklist

Use this archive as an overlay on the real BKTSTR repository, not as a replacement checkout.

- [ ] Create a feature branch from the current GitHub v0.3.3 code.
- [ ] Copy `bktstr_cache/`, new tests, runbook, and updated docs into their matching paths.
- [ ] Follow `integration/INTEGRATION_GUIDE.md` at the current intraday/daily/context computation call sites.
- [ ] Keep the existing formula functions unchanged; wrap them as callbacks.
- [ ] Run the original v0.3.3 suite (prior bundle baseline: 64/64).
- [ ] Run `python -m pytest -q` including this package's cache tests.
- [ ] Run cache-disabled vs cache-enabled copies of the same backtest and compare every trade field.
- [ ] Reproduce the known NVDA Jun-Aug 2026 control: 7 trades / 6 wins / ~+$6.086 EV per trade.
- [ ] Reproduce the known NVDA Mar-Dec 2025 bearish-regime control: 30 trades / 12 wins / ~-$2.266 EV per trade.
- [ ] Confirm coverage/provenance values are identical with cache enabled and disabled.
- [ ] Confirm a repeated warm run reports derived cache hits.
- [ ] Run QQQ and SOXX controls as documented in `AGENT_BACKTEST_RUNBOOK.md`.
- [ ] Only after behavioral equality, bump service/health version to v0.3.4 and deploy Railway.
