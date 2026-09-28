"""Bounded Massive futures acquisition, independent of strategy execution."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
import math
import re

import httpx

from .providers import MASSIVE_BASE_URL


PRODUCT_PATTERN = r"^[A-Z0-9]{1,10}$"
CONTRACT_PATTERN = r"^[A-Z0-9]{1,10}[FGHJKMNQUVXZ][0-9]{1,4}$"


class FuturesDataError(Exception):
    """Only fixed, credential-free messages cross the API boundary."""
    def __init__(self, code="futures_invalid_response", status=502,
                 message="Massive returned invalid or incomplete futures data."):
        super().__init__(message)
        self.code, self.status = code, status


def validate_range(ticker: str, start: date, end: date) -> None:
    if not re.fullmatch(CONTRACT_PATTERN, ticker):
        raise ValueError("Use an explicit futures contract, not a root or continuous symbol.")
    if end < start or (end - start).days > 30 or end == date.max:
        raise ValueError("Futures bars require 1 through 31 inclusive UTC dates.")


class MassiveFuturesProvider:
    def __init__(self, api_key, *, transport=None, sleep_fn=asyncio.sleep, max_retries=2):
        if not api_key:
            raise FuturesDataError("futures_not_configured", 503,
                                   "The server Massive credential is not configured.")
        self.api_key, self.transport = api_key, transport
        self.sleep, self.max_retries = sleep_fn, max_retries

    async def _get(self, client, url, params):
        for attempt in range(self.max_retries + 1):
            try:
                response = await client.get(url, params=params)
            except httpx.HTTPError:
                raise FuturesDataError("futures_provider_unavailable", 502,
                                       "The Massive futures request could not be completed.") from None
            if response.status_code in (401, 403):
                raise FuturesDataError("futures_access_denied", 403,
                    "Massive denied futures access. Check the server key and futures data entitlement.")
            if response.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                try:
                    delay = float(response.headers.get("Retry-After", 0.5 * 2 ** attempt))
                except ValueError:
                    delay = 0.5
                await self.sleep(min(2.0, max(0.0, delay)) if math.isfinite(delay) else 2.0)
                continue
            if response.status_code == 429:
                raise FuturesDataError("futures_rate_limited", 429,
                                       "Massive futures request rate limit reached; retry later.")
            if response.status_code != 200:
                raise FuturesDataError("futures_provider_error", 502,
                                       "Massive could not fulfill the futures request.")
            try:
                payload = response.json()
            except ValueError:
                raise FuturesDataError() from None
            if not isinstance(payload, dict) or payload.get("status") not in ("OK", "DELAYED"):
                raise FuturesDataError()
            return payload

    async def _pages(self, path, params, max_rows):
        url = MASSIVE_BASE_URL + path
        seen, rows = set(), []
        async with httpx.AsyncClient(timeout=20, transport=self.transport,
                follow_redirects=False, trust_env=False,
                headers={"Authorization": "Bearer " + self.api_key}) as client:
            for _ in range(20):
                if url in seen:
                    raise FuturesDataError()
                seen.add(url)
                payload = await self._get(client, url, params)
                page = payload.get("results")
                if not isinstance(page, list) or any(not isinstance(row, dict) for row in page):
                    raise FuturesDataError()
                rows.extend(page)
                if len(rows) > max_rows:
                    raise FuturesDataError()
                next_url = payload.get("next_url")
                if not next_url:
                    return rows
                try:
                    link = httpx.URL(next_url)
                except (httpx.InvalidURL, TypeError):
                    raise FuturesDataError() from None
                if (link.scheme != "https" or link.host != "api.massive.com"
                    or link.port not in (None, 443) or link.userinfo or link.fragment
                    or link.path != path or any(k.lower() in {"apikey", "api_key", "authorization"}
                                               for k in link.params)):
                    raise FuturesDataError()
                url, params = str(link), None
        raise FuturesDataError()

    async def contracts(self, product_code: str, as_of: date) -> list[dict]:
        if not re.fullmatch(PRODUCT_PATTERN, product_code):
            raise ValueError("Invalid futures product code.")
        params = {
            "product_code": product_code, "date": as_of.isoformat(),
            "limit": 1000, "sort": "ticker.asc"}
        typed_contracts = as_of >= date(2025, 3, 12)
        if typed_contracts:
            params["type"] = "single"
        rows = await self._pages("/futures/v1/contracts", params, 10000)
        fields = {"ticker", "product_code", "date", "active", "first_trade_date", "last_trade_date",
                  "settlement_date", "trade_tick_size", "settlement_tick_size", "spread_tick_size",
                  "min_order_quantity", "max_order_quantity", "trading_venue", "type"}
        result, seen = [], set()
        for row in rows:
            ticker = row.get("ticker")
            if (not isinstance(ticker, str) or row.get("product_code") != product_code
                or row.get("date") != as_of.isoformat()):
                raise FuturesDataError()
            if row.get("type") == "combo":
                continue
            outright = re.fullmatch(re.escape(product_code) + r"[FGHJKMNQUVXZ][0-9]{1,4}", ticker)
            # Contract type is unavailable before this date. Legacy combinations
            # cannot be returned as individually executable delivery contracts.
            if not typed_contracts and not outright:
                continue
            if not outright or ticker in seen:
                raise FuturesDataError()
            seen.add(ticker)
            result.append({k: v for k, v in row.items() if k in fields})
        return result

    async def bars(self, ticker: str, start: date, end: date) -> list[dict]:
        validate_range(ticker, start, end)
        rows = await self._pages("/futures/v1/aggs/" + ticker, {
            "resolution": "1min", "window_start.gte": start.isoformat(),
            "window_start.lt": (end + timedelta(days=1)).isoformat(),
            "limit": 50000, "sort": "window_start.asc"}, 44640)
        result, previous = [], None
        for row in rows:
            ns = row.get("window_start")
            if type(ns) is not int or ns % 60000000000 or row.get("ticker") != ticker:
                raise FuturesDataError()
            try:
                ts = datetime.fromtimestamp(ns // 1000000000, timezone.utc)
            except (ValueError, OverflowError, OSError):
                raise FuturesDataError() from None
            if not start <= ts.date() <= end or (previous is not None and ns <= previous):
                raise FuturesDataError()
            previous = ns
            numbers = {}
            for key in ("open", "high", "low", "close", "volume"):
                value = row.get(key)
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise FuturesDataError()
                numbers[key] = value
            if (numbers["volume"] < 0 or numbers["low"] > min(numbers["open"], numbers["close"])
                or numbers["high"] < max(numbers["open"], numbers["close"])):
                raise FuturesDataError()
            item = dict(ticker=ticker, timestamp=ts.isoformat().replace("+00:00", "Z"), **numbers)
            for key in ("dollar_volume", "transactions"):
                if key in row:
                    value = row[key]
                    if type(value) not in (int, float) or not math.isfinite(value) or (key == "transactions" and value < 0):
                        raise FuturesDataError()
                    item[key] = value
            result.append(item)
        return result
