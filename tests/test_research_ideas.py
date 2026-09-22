import json
import pytest


def idea_doc():
    return dict(id='vwap-reclaim', version='1.0.0', title='VWAP reclaim',
                thesis='A reclaim may precede continuation', mechanism='Participation resumes',
                falsification='No stable forward difference', applicability='Liquid equities',
                roles=['subject'])


def test_idea_can_exist_without_policy_and_is_deeply_immutable():
    from bktstr.research_ideas import parse_idea
    raw = idea_doc()
    idea = parse_idea(raw)
    raw['roles'].append('changed')
    copy = idea.document
    copy['roles'].append('changed')
    assert idea.document['roles'] == ['subject']
    assert parse_idea(dict(reversed(list(idea_doc().items())))).digest == idea.digest
    changed = idea_doc() | {'title': 'Reworded'}
    assert parse_idea(changed).semantic_digest == idea.semantic_digest
    assert parse_idea(changed).digest != idea.digest


@pytest.mark.parametrize('patch', [{'falsification': ''}, {'secret': 'value'}, {'version': 'latest'}, {'roles': ['subject', 'subject']}])
def test_invalid_idea_rejected(patch):
    from bktstr.research_ideas import parse_idea
    with pytest.raises(ValueError):
        parse_idea(idea_doc() | patch)


def test_study_modifiers_cannot_change_policy_and_references_pin_hashes():
    from bktstr.research_ideas import parse_modifier, parse_variant
    with pytest.raises(ValueError):
        parse_modifier(dict(id='bad', version='1.0.0', kind='study', category='context',
                            rationale='change', changes={'risk': {'stop_pct': 2}}))
    with pytest.raises(ValueError):
        parse_variant(dict(id='bad', version='1.0.0', kind='study', idea={'id': 'x'},
                           base={'id': 'x'}, rationale='test'))


def test_example_parses():
    from pathlib import Path
    from bktstr.research_ideas import parse_idea
    raw = json.loads(Path('examples/ideas/vwap-continuation.json').read_text())
    assert parse_idea(raw).id == 'vwap-reclaim'
