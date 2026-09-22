import pytest


def study_doc(**patch):
    return dict(id='reclaim', version='1.0.0', event_rules='close.cross_above:vwap',
                contexts=['volume_ratio20'], labels=[dict(id='r2', kind='return', minutes=2)]) | patch


def test_components_keep_roles_types_units_and_availability_explicit():
    from bktstr.research_components import ComponentCatalog, resolve_study
    catalog = ComponentCatalog()
    assert catalog.require('vwap')['role'] == 'reference'
    assert catalog.require('volume_ratio20')['units'] == 'ratio'
    result = resolve_study(study_doc(), catalog)
    assert result.document['labels'][0]['minutes'] == 2


@pytest.mark.parametrize('patch', [dict(event_rules='r2.gt:0'), dict(contexts=['r2']),
                                     dict(contexts=['unknown']), dict(macro_mode='scenario_only'),
                                     dict(event_rules='close.gt:nan')])
def test_future_unknown_and_unimplemented_components_fail(patch):
    from bktstr.research_components import resolve_study
    with pytest.raises(ValueError):
        resolve_study(study_doc(**patch))
