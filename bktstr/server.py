from __future__ import annotations

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from urllib.parse import parse_qs, urlparse

import httpx

from .service import BacktestRequest, execute_backtest


CAPABILITIES = {
    "service": "bktstr",
    "version": "0.1.0",
    "timeframes": ["1m", "5m", "15m", "1h", "1d"],
    "sides": ["long", "short"],
    "rule_syntax": {
        "examples": [
            "close.cross_below:vwap",
            "close.cross_above:vwap",
            "rsi14.lt:45",
            "rsi14.gt:55",
            "volume_ratio20.gt:1.5",
        ],
        "combine": "comma-separated rules are ANDed",
        "operators": ["lt", "lte", "gt", "gte", "eq", "cross_below", "cross_above"],
    },
    "execution_model": {
        "entry": "next bar open after signal",
        "same_bar_stop_target": "stop first (conservative)",
        "slippage": "applied adversely to entry and exit",
        "default_regular_hours_only": True,
        "default_same_day_only": True,
    },
    "providers": {
        "massive": "used when MASSIVE_API_KEY is configured",
        "yahoo": "fallback for recent intraday data only",
    },
}


def _first(params: dict[str, list[str]], name: str, default: str | None = None) -> str:
    values = params.get(name)
    if values:
        return values[0]
    if default is None:
        raise ValueError(f"missing required query parameter '{name}'")
    return default


def _bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean '{value}'")


def parse_backtest_query(query: str) -> tuple[BacktestRequest, dict]:
    params = parse_qs(query, keep_blank_values=False)
    request = BacktestRequest.from_values(
        symbol=_first(params, "symbol"),
        start=_first(params, "start"),
        end=_first(params, "end"),
        timeframe=_first(params, "timeframe", "1m"),
        side=_first(params, "side", "long"),
        entry=_first(params, "entry"),
        stop_pct=float(_first(params, "stop_pct", "1.0")),
        target_pct=float(_first(params, "target_pct", "3.0")),
        max_hold_minutes=int(_first(params, "max_hold_minutes", "240")),
        position_size=float(_first(params, "position_size", "1000")),
        starting_capital=float(_first(params, "starting_capital", "10000")),
        slippage_bps=float(_first(params, "slippage_bps", "2")),
        regular_hours_only=_bool(_first(params, "regular_hours_only", "true")),
        same_day_only=_bool(_first(params, "same_day_only", "true")),
    )
    trade_limit = int(_first(params, "trade_limit", "100"))
    if not 0 <= trade_limit <= 1000:
        raise ValueError("trade_limit must be between 0 and 1000")
    return request, {"trade_limit": trade_limit}


def _trim_result(result: dict, trade_limit: int) -> dict:
    trades = result.get("trades", [])
    result = dict(result)
    result["trades_total"] = len(trades)
    result["trades"] = trades[:trade_limit]
    result["trades_returned"] = len(result["trades"])
    result["trades_truncated"] = len(trades) > trade_limit
    return result


class Handler(BaseHTTPRequestHandler):
    server_version = "BKTSTR/0.1"

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        print(f"{self.address_string()} - {format % args}")

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/health"}:
            self._json(200, {"status": "ok", "service": "bktstr", "version": "0.1.0"})
            return
        if parsed.path == "/api/v1/capabilities":
            self._json(200, CAPABILITIES)
            return
        if parsed.path != "/api/v1/backtest":
            self._json(404, {"error": "not_found"})
            return

        try:
            request, options = parse_backtest_query(parsed.query)
            result = asyncio.run(execute_backtest(request))
            self._json(200, _trim_result(result, options["trade_limit"]))
        except ValueError as exc:
            self._json(400, {"error": "invalid_request", "detail": str(exc)})
        except httpx.HTTPStatusError as exc:
            self._json(502, {"error": "market_data_http_error", "detail": str(exc)})
        except RuntimeError as exc:
            self._json(503, {"error": "service_unavailable", "detail": str(exc)})
        except Exception as exc:  # pragma: no cover - last-resort production guard
            self._json(500, {"error": "internal_error", "detail": str(exc)})


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"BKTSTR listening on 0.0.0.0:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
