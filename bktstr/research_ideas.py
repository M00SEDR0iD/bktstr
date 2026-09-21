"""Versioned research documents. Canonical strings own state; callers receive copies."""
from dataclasses import dataclass
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from .strategy_config import _require_version


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Object(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True, allow_inf_nan=False)


class Ref(Object):
    id: str = Field(pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,100}$')
    version: str
    digest: str = Field(pattern=r'^[0-9a-f]{64}$')


class Definition(Object):
    id: str = Field(pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,100}$')
    version: str

    @model_validator(mode='after')
    def valid_version(self):
        _require_version(self.version, label='revision version')
        return self


class Idea(Definition):
    title: str = Field(min_length=1)
    thesis: str = Field(min_length=1)
    mechanism: str = Field(min_length=1)
    falsification: str = Field(min_length=1)
    applicability: str = Field(min_length=1)
    roles: list[Literal['subject', 'benchmark']] = Field(min_length=1)
    base_study: Ref | None = None
    derived_from: Ref | None = None

    @model_validator(mode='after')
    def meaningful(self):
        if any(not getattr(self, x).strip() for x in ('title', 'thesis', 'mechanism', 'falsification', 'applicability')):
            raise ValueError('idea text cannot be blank')
        if len(set(self.roles)) != len(self.roles) or 'subject' not in self.roles:
            raise ValueError('unique roles including subject required')
        return self


class Label(Object):
    id: str = Field(pattern=r'^[a-z][a-z0-9_]{0,60}$')
    kind: Literal['return', 'mfe', 'mae']
    minutes: int = Field(gt=0, le=390)
    reference: Literal['event_close'] = 'event_close'
    boundary: Literal['censor'] = 'censor'


class Study(Definition):
    event_rules: str
    contexts: list[str] = Field(default_factory=lambda: ['volume_ratio20'])
    labels: list[Label] = Field(min_length=1)
    sampling: Literal['all'] = 'all'
    macro_mode: Literal['none', 'evidence_required', 'scenario_only', 'unavailable'] = 'none'
    component_version: Literal['1.0.0'] = '1.0.0'

    @model_validator(mode='after')
    def unique(self):
        if len({x.id for x in self.labels}) != len(self.labels) or len(set(self.contexts)) != len(self.contexts):
            raise ValueError('duplicate label or context')
        return self


class Policy(Definition):
    recipe: dict
    evidence: list[str] = Field(default_factory=list)
    contrary_evidence: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=1)
    limitations: str = Field(min_length=1)
    status: Literal['untested', 'candidate'] = 'untested'

    @model_validator(mode='after')
    def promoted(self):
        if self.status == 'candidate' and not self.evidence:
            raise ValueError('candidate requires study evidence')
        if set(self.recipe) & {'instruments', 'evaluation', 'paper_limits'}:
            raise ValueError('policy recipe cannot contain application bindings')
        return self


class Modifier(Definition):
    kind: Literal['study', 'policy']
    category: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    changes: dict = Field(min_length=1)
    prerequisites: list[Ref] = Field(default_factory=list)
    conflicts: list[Ref] = Field(default_factory=list)

    @model_validator(mode='after')
    def targets(self):
        allowed = {'event_rules', 'contexts', 'labels', 'macro_mode'} if self.kind == 'study' else {'entry', 'risk', 'execution', 'filters', 'session'}
        if set(self.changes) - allowed:
            raise ValueError('modifier changes unsupported fields for its kind')
        return self


class Variant(Definition):
    kind: Literal['study', 'policy']
    idea: Ref
    base: Ref
    parent: Ref | None = None
    modifiers: list[Ref] = Field(default_factory=list)
    rationale: str = Field(min_length=1)


class Application(Definition):
    instruments: dict[str, str]
    dataset: str = Field(pattern=r'^[0-9a-f]{64}$')
    profile: Literal['equity-minute'] = 'equity-minute'
    calendar: Literal['XNYS'] = 'XNYS'
    timezone: Literal['America/New_York'] = 'America/New_York'
    timeframe: Literal['1m'] = '1m'
    currency: Literal['USD'] = 'USD'

    @model_validator(mode='after')
    def roles(self):
        import re
        if 'subject' not in self.instruments or set(self.instruments) - {'subject', 'benchmark'}:
            raise ValueError('subject and optional benchmark required')
        if any(not re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,14}', x) for x in self.instruments.values()):
            raise ValueError('explicit uppercase symbols required')
        return self


@dataclass(frozen=True)
class Revision:
    kind: str
    canonical_json: str

    @property
    def document(self):
        return json.loads(self.canonical_json)

    @property
    def id(self):
        return self.document['id']

    @property
    def version(self):
        return self.document['version']

    @property
    def digest(self):
        return digest(self.document)

    @property
    def semantic_digest(self):
        return digest({k: v for k, v in self.document.items() if k not in {
            'id', 'version', 'title', 'rationale', 'limitations', 'thesis', 'mechanism',
            'falsification', 'applicability'}})

    @property
    def ref(self):
        return {'id': self.id, 'version': self.version, 'digest': self.digest}


MODELS = {'idea': Idea, 'study': Study, 'policy': Policy, 'modifier': Modifier,
          'variant': Variant, 'application': Application}


def parse_revision(kind, document):
    validated = MODELS[kind].model_validate(document)
    return Revision(kind, canonical(validated.model_dump(mode='json')))


def parse_idea(document): return parse_revision('idea', document)
def parse_study(document): return parse_revision('study', document)
def parse_policy(document): return parse_revision('policy', document)
def parse_modifier(document): return parse_revision('modifier', document)
def parse_variant(document): return parse_revision('variant', document)
def parse_application(document): return parse_revision('application', document)

IdeaRevision = StudySpec = PolicyRevision = ModifierRevision = VariantRevision = ApplicationSpec = Revision
