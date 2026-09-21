"""Pure variant composition and explicit policy/application binding."""
from copy import deepcopy
import pandas as pd
from .dataset_snapshots import instant
from .research_ideas import Revision, parse_variant, parse_study, parse_policy
from .research_components import resolve_study
from .strategy_config import compile_strategy


def leaf_changes(value, prefix=()):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from leaf_changes(child, (*prefix, key))
    else:
        yield prefix, value


def differences(base, candidate, prefix=''):
    result = {}
    for key in sorted(set(base) | set(candidate)):
        path = prefix + key
        a, b = base.get(key), candidate.get(key)
        if isinstance(a, dict) and isinstance(b, dict):
            result.update(differences(a, b, path + '.'))
        elif a != b:
            result[path] = {'before':a, 'after':b}
    return result


def resolve_variant(variant, catalog, _seen=()):
    variant = parse_variant(variant.document if isinstance(variant, Revision) else variant)
    if variant.digest in _seen or len(_seen) >= 32:
        raise ValueError('variant ancestry cycle or depth limit')
    doc = variant.document
    catalog.require(doc['idea'], 'idea')
    base = catalog.require(doc['base'], doc['kind'])
    if doc['parent']:
        parent = catalog.require(doc['parent'], 'variant')
        if any(parent.document[key] != doc[key] for key in ('idea', 'base', 'kind')):
            raise ValueError('parent must share idea, base, and kind')
        base = resolve_variant(parent, catalog, (*_seen, variant.digest))
    result = base.document
    target = result if doc['kind'] == 'study' else result['recipe']
    refs = doc['modifiers']
    assigned = set()
    for ref in refs:
        modifier = catalog.require(ref, 'modifier').document
        if modifier['kind'] != doc['kind']:
            raise ValueError('modifier kind mismatch')
        if any(x not in refs for x in modifier['prerequisites']) or any(x in refs for x in modifier['conflicts']):
            raise ValueError('modifier prerequisite/conflict')
        for path, value in leaf_changes(modifier['changes']):
            if path in assigned or any(path[:len(p)] == p or p[:len(path)] == path for p in assigned):
                raise ValueError('conflicting modifier assignments')
            assigned.add(path)
            cursor = target
            for part in path[:-1]:
                if part not in cursor or not isinstance(cursor[part], dict):
                    raise ValueError('modifier path does not exist')
                cursor = cursor[part]
            cursor[path[-1]] = deepcopy(value)
    return resolve_study(result) if doc['kind'] == 'study' else parse_policy(result)


def bind_policy(policy, application, run_window):
    policy = parse_policy(policy.document if isinstance(policy, Revision) else policy)
    app = application.document if isinstance(application, Revision) else application
    start, end = (instant(x) for x in run_window)
    if start >= end:
        raise ValueError('invalid run window')
    recipe = policy.document['recipe']
    recipe.update(instruments=app['instruments'], calendar=app['calendar'],
        timezone=app['timezone'], timeframe=app['timeframe'],
        evaluation=dict(start=str(start.tz_convert(app['timezone']).date()),
                        end=str((end - pd.Timedelta(nanoseconds=1)).tz_convert(app['timezone']).date()), variant_budget=1))
    return compile_strategy(recipe)
