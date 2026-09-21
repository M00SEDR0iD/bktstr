import pytest
from test_dataset_snapshots import sample_frames, sample_schedule
from test_research_components import study_doc


def prepare(tmp_path, missing=False):
    from bktstr.dataset_snapshots import freeze_dataset
    return freeze_dataset(sample_frames(missing), sample_schedule(), tmp_path,
                          source='synthetic', controlled=not missing)


def test_all_events_and_forward_labels_have_separate_interfaces(tmp_path):
    from bktstr.event_research import build_events, label_events
    from bktstr.research_components import resolve_study
    snap = prepare(tmp_path)
    study = resolve_study(study_doc(contexts=['close']))
    events = build_events(study, {'instruments': {'subject': 'SPY'}}, snap)
    assert len(events.document['rows']) == 2
    assert all('r2' not in e['values'] for e in events.document['rows'])
    labels = label_events(events, study.document['labels'], snap)
    first, last = labels.document['rows']
    assert first['values']['r2'] == pytest.approx((103/102-1)*100)
    assert last['reasons']['r2'] == 'session_boundary'
    assert events.document['rows'][0]['cutoff'].endswith('13:33:00+00:00')


def test_future_change_cannot_change_earlier_predictors(tmp_path):
    from bktstr.event_research import build_events
    from bktstr.dataset_snapshots import freeze_dataset
    frames = sample_frames()
    study = study_doc(contexts=['close'])
    a = build_events(study, {'instruments': {'subject': 'SPY'}}, prepare(tmp_path))
    frames['SPY'].iloc[4:, :4] *= 2
    b = build_events(study, {'instruments': {'subject': 'SPY'}},
                     freeze_dataset(frames, sample_schedule(), tmp_path, source='changed'))
    assert a.document['rows'][0]['values'] == b.document['rows'][0]['values']
    assert a.document['rows'][0]['cutoff'] == b.document['rows'][0]['cutoff']


def test_missing_minutes_and_split_boundary_are_censored(tmp_path):
    from bktstr.event_research import build_events, label_events
    study = study_doc(event_rules='close.gt:0', contexts=['close'])
    snap = prepare(tmp_path, missing=True)
    events = build_events(study, {'instruments': {'subject': 'SPY'}}, snap)
    labels = label_events(events, study['labels'], snap, end='2026-08-17T13:34:00Z')
    assert labels.document['rows'][0]['reasons']['r2'] == 'missing_price'
    assert any(row['reasons'].get('r2') == 'split_boundary' for row in labels.document['rows'])
