# v0.3.5 Merge / Deployment Checklist

- [ ] Work on a feature branch created from current production `main`; do not edit production `main` directly.
- [ ] Replace/merge the v0.3.5 repository files.
- [ ] Remove any generated Python artifacts currently tracked by Git. Check with:

```bash
git ls-files | grep -E '(^|/)(__pycache__|\.pytest_cache)(/|$)|\.py[co]$' || true
```

If this prints files, remove them from Git before the v0.3.5 commit.
- [ ] Run `python -m pytest -q` locally.
- [ ] Run `python -m compileall -q bktstr bktstr_cache integration scripts benchmarks tests`.
- [ ] Run `python benchmarks/benchmark_cache.py` and verify cold miss → warm hit with one compute call.
- [ ] Commit the feature branch and push it to GitHub.
- [ ] Require the **BKTSTR CI** GitHub Actions workflow to pass.
- [ ] Merge the feature branch to `main` only after CI is green.
- [ ] Confirm Railway deploys the new `main` commit.
- [ ] Check `/health`: require `version=0.3.5` and record `git_commit`.
- [ ] Check `/api/v1/capabilities`: require v0.3.5 release/formula/cache metadata.
- [ ] Run:

```bash
python scripts/production_acceptance.py --base-url https://bktstr-production.up.railway.app
```

- [ ] Require the frozen anchor: 7 trades / 6 wins / 1 loss / +$42.604714 / +$6.086388 EV.
- [ ] Require exact trading-output equality across the two acceptance runs.
- [ ] Require second-run derived cache hits for intraday, regime, and sentiment.
- [ ] Tag the accepted commit as `v0.3.5`.
