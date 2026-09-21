"""Descriptive event studies with declared contiguous-session block uncertainty."""
import math
import numpy as np
from pydantic import Field, model_validator
from ..research_ideas import Object
from ..dataset_snapshots import instant


class Grouping(Object):
    context: str
    edges: list[float] = Field(min_length=1)
    fitted_artifact: str | None = None
    fit_start: str | None = None
    fit_end: str | None = None
    quantiles: list[float] | None = None

    @model_validator(mode='after')
    def ordered(self):
        if sorted(set(self.edges)) != self.edges:
            raise ValueError('group edges must be unique and sorted')
        if self.fitted_artifact and (not self.fit_start or not self.fit_end or not self.quantiles):
            raise ValueError('fitted grouping requires development provenance')
        return self


class StudyAnalysisSpec(Object):
    label: str
    grouping: Grouping | None = None
    block_sessions: int = Field(default=1, ge=1)
    minimum_blocks: int = Field(default=3, ge=2)
    resamples: int = Field(default=200, ge=100, le=10000)
    seed: int = 0


def fit_quantile_groups(events, context, quantiles):
    if not quantiles or any(not 0 < q < 1 for q in quantiles) or sorted(set(quantiles)) != quantiles:
        raise ValueError('quantiles must be distinct ordered probabilities')
    rows = events.document['rows']
    values = [r['values'].get(context) for r in rows]
    values = [x for x in values if x is not None and math.isfinite(x)]
    if not values or not events.document.get('start') or not events.document.get('end'):
        raise ValueError('development data and scope required')
    edges = list(dict.fromkeys(float(x) for x in np.quantile(values, quantiles)))
    return dict(context=context, edges=edges, fitted_artifact=events.id,
                fit_start=events.document['start'], fit_end=events.document['end'], quantiles=quantiles)


def _mean(values):
    return float(np.mean(values)) if len(values) else None


def block_resamples(rows, spec):
    """Aligned session draws preserve within-session and cross-symbol clustering."""
    dates = sorted({r['session'] for r in rows})
    if len(dates) // spec.block_sessions < spec.minimum_blocks:
        return []
    by_date = {d: [r for r in rows if r['session'] == d] for d in dates}
    rng = np.random.default_rng(spec.seed)
    samples = []
    for _ in range(spec.resamples):
        chosen = []
        while len(chosen) < len(dates):
            start = int(rng.integers(0, len(dates) - spec.block_sessions + 1))
            chosen.extend(dates[start:start + spec.block_sessions])
        samples.append([r for d in chosen[:len(dates)] for r in by_date[d]])
    return samples


def _interval(values, expected):
    available = [x for x in values if x is not None and math.isfinite(x)]
    if expected == 0 or len(available) < 0.9 * expected:
        return None
    return [float(x) for x in np.quantile(available, [.025, .975])]


def summarize_study(events, labels, analysis, *, stage='development'):
    spec = StudyAnalysisSpec.model_validate(analysis)
    if labels.document['event_dataset'] != events.id:
        raise ValueError('label/event artifact mismatch')
    if spec.label not in {x['id'] for x in labels.document['definitions']}:
        raise ValueError('unknown primary label')
    if spec.grouping and spec.grouping.fitted_artifact and stage != 'development':
        if not events.document.get('start') or instant(spec.grouping.fit_end) > instant(events.document['start']):
            raise ValueError('group boundaries must be fitted on earlier development data')
    outcomes = {r['event_id']: r for r in labels.document['rows']}
    rows, missing = [], {}
    for event in events.document['rows']:
        label = outcomes.get(event['id'])
        if label is None:
            raise ValueError('missing label row')
        value = label['values'].get(spec.label)
        if value is None:
            reason = label['reasons'].get(spec.label, 'unavailable')
            missing[reason] = missing.get(reason, 0) + 1
            continue
        group = None
        if spec.grouping:
            context = event['values'].get(spec.grouping.context)
            if context is not None:
                group = int(np.searchsorted(spec.grouping.edges, context, side='right'))
        rows.append(dict(id=event['id'], session=event['session'], symbol=event['symbol'], value=value, group=group))
    values = [r['value'] for r in rows]
    samples = block_resamples(rows, spec)
    means = [_mean([r['value'] for r in sample]) for sample in samples]
    grouped, difference = {}, None
    if spec.grouping:
        groups = range(len(spec.grouping.edges) + 1)
        for group in groups:
            selected = [r['value'] for r in rows if r['group'] == group]
            grouped[str(group)] = dict(count=len(selected), mean=_mean(selected))
        def contrast(sample):
            low = _mean([r['value'] for r in sample if r['group'] == 0])
            high = _mean([r['value'] for r in sample if r['group'] == len(spec.grouping.edges)])
            return high - low if high is not None and low is not None else None
        difference = dict(estimate=contrast(rows), interval=_interval([contrast(s) for s in samples], len(samples)),
                          description='Highest context group minus lowest; association, not causal effect.')
    sessions = sorted({r['session'] for r in rows})
    return dict(primary_label=spec.label, event_count=len(events.document['rows']), usable=len(rows),
        sessions=len(sessions), blocks=len(sessions) // spec.block_sessions, censored=missing,
        mean=_mean(values), median=float(np.median(values)) if values else None,
        quantiles=[float(x) for x in np.quantile(values, [.1, .25, .75, .9])] if values else [],
        interval=_interval(means, len(samples)),
        uncertainty_status='estimated' if samples else 'insufficient_blocks',
        groups=grouped, context_missing=sum(r['group'] is None for r in rows) if spec.grouping else 0,
        context_difference=difference,
        by_instrument={s: dict(count=sum(r['symbol'] == s for r in rows), mean=_mean([r['value'] for r in rows if r['symbol'] == s])) for s in sorted({r['symbol'] for r in rows})},
        by_session={s: dict(count=sum(r['session'] == s for r in rows), mean=_mean([r['value'] for r in rows if r['session'] == s])) for s in sessions},
        analysis=spec.model_dump(mode='json'),
        limitations=['Session-block resampling assumes the declared block length captures dependence.',
                     'Exploratory intervals do not adjust for the number of hypotheses searched.',
                     'Forward observations do not include executable entry prices or trading costs.'])
