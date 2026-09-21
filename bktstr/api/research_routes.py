"""Additive authenticated idea, research, and human report operations."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request, Header, Query
from fastapi.responses import PlainTextResponse, HTMLResponse
from pydantic import Field
import pandas as pd

from .auth import require_api_key
from .schemas import EventStudyExperimentResponse, ConfiguredBacktestExperimentResponse
from ..research_ideas import Idea, Object
from ..research_components import ComponentCatalog
from ..dataset_snapshots import freeze_dataset, instant
from ..services.research_store import ResearchCatalog
from ..services.configured_research import ResearchRunRequest, submit_research_run
from ..services.research_protocol import (Protocol, register_protocol, run_protocol, cancel_attempt,
                                         inspect_experiment, record_inspection)
from ..services.idea_reports import (idea_report, export_idea_markdown, export_experiment_markdown,
                                    list_research_experiments, export_idea_html)

research_router = APIRouter(dependencies=[Depends(require_api_key)])


def _catalog(request):
    return ResearchCatalog(request.app.state.experiment_store)


def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except (ValueError, KeyError, FileNotFoundError) as error:
        raise HTTPException(422, detail='Invalid or unavailable research input: ' + type(error).__name__) from error


@research_router.get('/ideas')
def ideas(request: Request):
    return [x.document for x in _catalog(request).revisions('idea')]


@research_router.post('/ideas', status_code=201)
def create_idea(document: Idea, request: Request):
    return _call(_catalog(request).register, 'idea', document.model_dump(mode='json')).ref


@research_router.post('/research/revisions/{kind}', status_code=201)
def register_revision(kind: Literal['study','policy','modifier','variant','application'], document: dict, request: Request):
    return _call(_catalog(request).register, kind, document).ref


@research_router.get('/research/revisions/{kind}')
def revisions(kind: Literal['study','policy','modifier','variant','application'], request: Request):
    return [dict(reference=x.ref, document=x.document) for x in _catalog(request).revisions(kind)]


@research_router.get('/research/components')
def components():
    return ComponentCatalog().definitions()


class DatasetUpload(Object):
    bars: dict[str, list[list]]
    schedule: list[dict]
    source: str = Field(min_length=1)
    schedule_source: str = Field(min_length=1)
    adjustment: Literal['unadjusted','adjusted']
    controlled: bool = True


@research_router.post('/research/datasets', status_code=201)
def upload_dataset(document: DatasetUpload, request: Request):
    def save():
        frames = {}
        for symbol, rows in document.bars.items():
            frame = pd.DataFrame(rows, columns=['timestamp','open','high','low','close','volume'])
            frame.index = pd.DatetimeIndex([instant(x) for x in frame.pop('timestamp')])
            frames[symbol] = frame
        result = freeze_dataset(frames, document.schedule, _catalog(request).datasets,
            source=document.source, controlled=document.controlled, adjustment=document.adjustment,
            schedule_source=document.schedule_source)
        return dict(dataset=result.id, coverage=result.document['coverage'])
    return _call(save)


@research_router.post('/event-studies', status_code=202, response_model=EventStudyExperimentResponse)
def submit_study(document: ResearchRunRequest, request: Request, idempotency_key: str = Header(min_length=1)):
    if document.operation != 'event_study': raise HTTPException(422, detail='operation mismatch')
    record = _call(submit_research_run, _catalog(request).store, document.model_dump(mode='json'), idempotency_key)
    return EventStudyExperimentResponse.from_record(record)


@research_router.post('/configured-backtests', status_code=202, response_model=ConfiguredBacktestExperimentResponse)
def submit_policy(document: ResearchRunRequest, request: Request, idempotency_key: str = Header(min_length=1)):
    if document.operation != 'configured_backtest': raise HTTPException(422, detail='operation mismatch')
    record = _call(submit_research_run, _catalog(request).store, document.model_dump(mode='json'), idempotency_key)
    return ConfiguredBacktestExperimentResponse.from_record(record)


@research_router.post('/research-protocols', status_code=201)
def create_protocol(document: Protocol, request: Request):
    return _call(register_protocol, document.model_dump(mode='json'), _catalog(request)).ref


@research_router.post('/research-protocols/{protocol_id}/run', status_code=202)
def queue_protocol(protocol_id: str, request: Request):
    return _call(run_protocol, protocol_id, _catalog(request).store, execute=False)


@research_router.get('/research-protocols/{protocol_id}')
def protocol_report(protocol_id: str, request: Request):
    return _call(run_protocol, protocol_id, _catalog(request).store, execute=False, admit=False)


@research_router.get('/ideas/{idea_id}/report')
def get_idea_report(idea_id: str, request: Request):
    return _call(idea_report, idea_id, _catalog(request).store)


@research_router.get('/ideas/{idea_id}/markdown', response_class=PlainTextResponse)
def get_idea_markdown(idea_id: str, request: Request):
    return _call(export_idea_markdown, idea_id, _catalog(request).store).read_text(encoding='utf-8')


@research_router.get('/ideas/{idea_id}/html', response_class=HTMLResponse)
def get_idea_html(idea_id: str, request: Request):
    content = _call(export_idea_html, idea_id, _catalog(request).store).read_text(encoding='utf-8')
    return HTMLResponse(content, headers={
        'Content-Security-Policy': "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})


@research_router.get('/experiments')
def history(request: Request, idea_id: str | None = None, kind: str | None = None,
            variant: str | None = None, instrument: str | None = None, campaign: str | None = None,
            status: str | None = None, start: str | None = None, end: str | None = None,
            limit: int = Query(default=50, ge=1, le=200), cursor: str | None = None):
    return _call(list_research_experiments, _catalog(request).store, idea_id=idea_id, kind=kind,
        variant=variant, instrument=instrument, campaign=campaign, status=status,
        start=start, end=end, limit=limit, cursor=cursor)


@research_router.get('/experiments/{experiment_id}/markdown', response_class=PlainTextResponse)
def get_test_markdown(experiment_id: str, request: Request):
    return _call(export_experiment_markdown, experiment_id, _catalog(request).store).read_text(encoding='utf-8')


@research_router.post('/experiments/{experiment_id}/cancel')
def cancel(experiment_id: str, request: Request):
    return {'requested': _call(cancel_attempt, experiment_id, _catalog(request))}


@research_router.get('/experiments/{experiment_id}/artifacts/{kind}')
def get_artifact(experiment_id: str, kind: Literal['events','labels'], request: Request):
    def load():
        catalog = _catalog(request)
        record = catalog.store.load_experiment(experiment_id)
        inspect_experiment(catalog, record, reason='raw research artifact export')
        return catalog.load_artifact(record.result[kind + '_artifact'])
    return _call(load)


class Assessment(Object):
    author: str
    conclusion: str
    evidence: list[str]
    limitations: str


@research_router.post('/ideas/{idea_id}/assessments', status_code=201)
def assess(idea_id: str, document: Assessment, request: Request):
    return {'id': _call(_catalog(request).assess, idea_id, **document.model_dump())}


class Inspection(Object):
    symbols: list[str]
    start: str
    end: str
    artifact_id: str
    actor: str
    reason: str


@research_router.post('/research/inspections', status_code=201)
def inspection(document: Inspection, request: Request):
    _call(record_inspection, _catalog(request), **document.model_dump())
    return {'recorded':True}
