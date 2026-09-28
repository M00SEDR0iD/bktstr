"""Futures data inspection only; existing policy and acquisition contracts stay separate."""
from datetime import date, datetime, timezone
import os
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, FiniteFloat, ValidationError

from .auth import require_api_key
from .schemas import ErrorResponse
from ..futures_data import (CONTRACT_PATTERN, PRODUCT_PATTERN, FuturesDataError,
                            MassiveFuturesProvider, validate_range)


class FuturesBar(BaseModel):
    ticker: str
    timestamp: datetime
    open: FiniteFloat
    high: FiniteFloat
    low: FiniteFloat
    close: FiniteFloat
    volume: FiniteFloat
    dollar_volume: FiniteFloat | None = None
    transactions: FiniteFloat | None = None


class FuturesContract(BaseModel):
    ticker: str
    product_code: str
    date: date
    active: bool | None = None
    first_trade_date: date | None = None
    last_trade_date: date | None = None
    settlement_date: date | None = None
    trade_tick_size: FiniteFloat | None = None
    settlement_tick_size: FiniteFloat | None = None
    spread_tick_size: FiniteFloat | None = None
    min_order_quantity: int | None = None
    max_order_quantity: int | None = None
    trading_venue: str | None = None
    type: str | None = None


class FuturesBarsResponse(BaseModel):
    source: Literal['massive'] = 'massive'
    asset_class: Literal['futures'] = 'futures'
    timeframe: Literal['1m'] = '1m'
    adjustment: Literal['unadjusted'] = 'unadjusted'
    timestamp_convention: Literal['minute-open UTC'] = 'minute-open UTC'
    execution_supported: Literal[True] = True
    ticker: str
    start: date
    end: date
    acquired_at: datetime
    bars: list[FuturesBar]


class FuturesContractsResponse(BaseModel):
    source: Literal['massive'] = 'massive'
    product_code: str
    as_of: date
    acquired_at: datetime
    contracts: list[FuturesContract]


futures_router = APIRouter(prefix='/market-data/futures', dependencies=[Depends(require_api_key)],
    responses={code: {'model': ErrorResponse} for code in (401, 403, 422, 429, 502, 503)})


def get_provider():
    return MassiveFuturesProvider(os.environ.get('MASSIVE_API_KEY', ''))


def fail(error):
    raise HTTPException(error.status, detail={'code': error.code, 'message': str(error)}) from None


@futures_router.get('/contracts', response_model=FuturesContractsResponse)
async def contracts(product_code: Annotated[str, Query(pattern=PRODUCT_PATTERN)], as_of: date):
    """List explicit contracts at a specified date using the existing Massive credential."""
    try:
        rows = await get_provider().contracts(product_code, as_of)
        return FuturesContractsResponse(product_code=product_code, as_of=as_of,
            acquired_at=datetime.now(timezone.utc), contracts=rows)
    except FuturesDataError as error:
        fail(error)
    except ValidationError:
        fail(FuturesDataError())


@futures_router.get('/bars', response_model=FuturesBarsResponse)
async def bars(ticker: Annotated[str, Query(pattern=CONTRACT_PATTERN)], start: date, end: date):
    """Fetch up to 31 inclusive UTC dates; no continuous series, imputation, or fallback."""
    try:
        validate_range(ticker, start, end)
    except ValueError as error:
        raise HTTPException(422, detail={'code': 'validation_error', 'message': str(error)}) from None
    try:
        rows = await get_provider().bars(ticker, start, end)
        return FuturesBarsResponse(ticker=ticker, start=start, end=end,
            acquired_at=datetime.now(timezone.utc), bars=rows)
    except FuturesDataError as error:
        fail(error)
    except ValidationError:
        fail(FuturesDataError())
