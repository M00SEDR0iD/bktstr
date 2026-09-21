import pytest
from test_configured_research import configured
from test_research_protocol import protocol_doc


def test_campaign_restart_reuses_children_and_reports_all_cells(tmp_path):
    from bktstr.services.research_protocol import register_protocol, run_protocol
    store, catalog, request = configured(tmp_path)
    protocol = register_protocol(protocol_doc(request), catalog)
    first = run_protocol(protocol.id, store)
    second = run_protocol(protocol.id, store)
    assert first['cells'][0]['experiment_id'] == second['cells'][0]['experiment_id']
    assert second['status'] == 'completed'
    assert second['attempts'] == 1


def test_undeclared_candidate_difference_rejected(tmp_path):
    from bktstr.services.research_protocol import register_protocol
    store, catalog, request = configured(tmp_path)
    base = catalog.require(request['specification'])
    changed = catalog.register('study', base.document | {'id':'changed', 'event_rules':'close.gt:0'})
    with pytest.raises(ValueError, match='difference'):
        register_protocol(protocol_doc(request, candidates=[base.ref, changed.ref], candidate_budget=2), catalog)


def test_cancellation_is_visible_and_does_not_refund_attempt(tmp_path):
    from bktstr.services.research_protocol import register_protocol, admit_attempt, cancel_attempt, run_protocol
    store, catalog, request = configured(tmp_path)
    protocol = register_protocol(protocol_doc(request), catalog)
    attempt = admit_attempt(protocol.id, request['specification'], request['application'], 'dev', 'once', catalog)
    assert cancel_attempt(attempt.experiment_id, catalog)
    report = run_protocol(protocol.id, store)
    assert report['cells'][0]['status'] == 'failed'
    assert report['cells'][0]['error']['code'] == 'research_cancelled'
    assert report['attempts'] == 1
