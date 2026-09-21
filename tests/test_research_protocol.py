from concurrent.futures import ThreadPoolExecutor
import pytest
from test_configured_research import configured


def protocol_doc(request, **patch):
    return dict(id='campaign', version='1.0.0', idea=request['idea'], kind='study',
        baseline=request['specification'], candidates=[request['specification']],
        applications=[request['application']],
        splits=[dict(name='dev', stage='development', start=request['start'], end=request['end'])],
        candidate_budget=1, attempt_budget=1, minimum_samples=2, stopping_rule='Run declared matrix once',
        primary_metric='mean', allowed_differences=[], aggregation='equal_instrument',
        analysis={'label':'r2'}) | patch


def test_admission_is_atomic_and_retry_does_not_spend_again(tmp_path):
    from bktstr.services.research_protocol import register_protocol, admit_attempt
    store, catalog, request = configured(tmp_path)
    protocol = register_protocol(protocol_doc(request), catalog)
    def admit(_):
        return admit_attempt(protocol.id, request['specification'], request['application'], 'dev', 'once', catalog)
    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(admit, range(2)))
    assert records[0].experiment_id == records[1].experiment_id
    with pytest.raises(ValueError, match='budget'):
        admit_attempt(protocol.id, request['specification'], request['application'], 'dev', 'again', catalog)


def test_exposure_survives_new_campaign_name(tmp_path):
    from bktstr.services.research_protocol import register_protocol, admit_attempt, record_inspection
    store, catalog, request = configured(tmp_path)
    record_inspection(catalog, symbols=['SPY'], start=request['start'], end=request['end'],
                      artifact_id='external', actor='owner', reason='already inspected')
    split = dict(name='final', stage='final', start=request['start'], end=request['end'])
    p = register_protocol(protocol_doc(request, id='renamed', splits=[split], final_candidates=[request['specification']]), catalog)
    with pytest.raises(ValueError, match='exposed'):
        admit_attempt(p.id, request['specification'], request['application'], 'final', 'once', catalog)


def test_splits_and_candidates_must_be_frozen(tmp_path):
    from bktstr.services.research_protocol import register_protocol
    store, catalog, request = configured(tmp_path)
    doc = protocol_doc(request)
    doc['splits'].append(doc['splits'][0] | {'name':'val', 'stage':'validation'})
    with pytest.raises(ValueError, match='overlap'):
        register_protocol(doc, catalog)
