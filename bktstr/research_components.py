"""Research roles and timing around the existing numerical indicator library."""
import math
from dataclasses import dataclass
from .research_ideas import Revision, parse_study
from .rules import parse_rules


class ComponentCatalog:
    version = '1.0.0'

    def definitions(self):
        from .measurements import intraday_definitions
        formulas = {x.column: x.formula_version for x in intraday_definitions()}
        definitions = []
        for name in ('open', 'high', 'low', 'close', 'volume', 'vwap', 'rsi14', 'volume_ratio20'):
            definitions.append(dict(id=name, version=self.version,
                role='reference' if name == 'vwap' else 'context', value_type='continuous',
                units='ratio' if name == 'volume_ratio20' else 'index' if name == 'rsi14' else 'shares' if name == 'volume' else 'USD',
                formula=formulas.get(name, 'source.1.0.0'),
                availability='bar_open_plus_one_minute', missing='retain_null',
                lookback=20 if name == 'volume_ratio20' else 14 if name == 'rsi14' else 1,
                trust='B' if name in formulas else 'A', profile='equity-minute'))
        return definitions

    def require(self, name):
        for definition in self.definitions():
            if definition['id'] == name:
                return definition
        raise ValueError(f'unknown predictor component: {name}')


def resolve_study(spec, catalog=None):
    catalog = catalog or ComponentCatalog()
    study = parse_study(spec.document if isinstance(spec, Revision) else spec)
    document = study.document
    if document['macro_mode'] != 'none':
        raise ValueError('macro evaluator is unavailable; no fallback')
    for context in document['contexts']:
        catalog.require(context)
    for rule in parse_rules(document['event_rules']):
        catalog.require(rule.left)
        if isinstance(rule.right, str):
            catalog.require(rule.right)
        elif not math.isfinite(rule.right):
            raise ValueError('nonfinite rule operand')
    return study


@dataclass(frozen=True)
class CausalInputs:
    """Only predictor data. Outcome artifacts have no predictor lookup."""
    canonical_json: str


@dataclass(frozen=True)
class OutcomeInputs:
    canonical_json: str
