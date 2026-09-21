import pytest


def observations(days=8):
    from bktstr.event_research import EventDataset, LabelDataset
    from bktstr.research_ideas import canonical
    rows, labels = [], []
    for day in range(days):
        for group in range(2):
            event_id = f'{day}-{group}'
            rows.append(dict(id=event_id, session=f'2026-08-{10+day:02}', symbol='SPY', values={'close':100., 'volume_ratio20':float(group)}, missing={}))
            labels.append(dict(event_id=event_id, session=f'2026-08-{10+day:02}', symbol='SPY', values={'r2':float(group*2)}, reasons={}))
    events = EventDataset(canonical(dict(rows=rows, start='2026-08-10T00:00:00Z', end='2026-08-18T00:00:00Z', coverage={'missing':0})))
    return events, LabelDataset(canonical(dict(event_dataset=events.id, definitions=[dict(id='r2', kind='return', minutes=2)], rows=labels)))


def test_known_context_effect_is_direct_difference_with_reproducible_uncertainty():
    from bktstr.services.event_studies import summarize_study
    events, labels = observations()
    analysis = dict(label='r2', grouping={'context':'volume_ratio20', 'edges':[0.5]}, resamples=100)
    result = summarize_study(events, labels, analysis)
    assert result['mean'] == 1
    assert result['context_difference']['estimate'] == 2
    assert result['context_difference']['interval'] == [2.,2.]
    assert result == summarize_study(events, labels, analysis)
    assert result['sessions'] == 8


def test_small_sample_and_missing_labels_stay_visible():
    from bktstr.services.event_studies import summarize_study
    events, labels = observations(1)
    result = summarize_study(events, labels, {'label':'r2'})
    assert result['interval'] is None
    assert result['uncertainty_status'] == 'insufficient_blocks'


def test_quantiles_are_frozen_from_development_and_future_fit_rejected():
    from bktstr.services.event_studies import fit_quantile_groups, summarize_study
    events, labels = observations()
    groups = fit_quantile_groups(events, 'volume_ratio20', [0.5])
    assert groups['edges'] == [0.5]
    with pytest.raises(ValueError, match='development'):
        summarize_study(events, labels, {'label':'r2', 'grouping':groups}, stage='final')


def test_label_identity_mismatch_rejected():
    from bktstr.services.event_studies import summarize_study
    events, labels = observations()
    with pytest.raises(ValueError, match='label'):
        summarize_study(events, labels, {'label':'unknown'})
