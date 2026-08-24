from __future__ import annotations

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from urllib.parse import parse_qs, urlparse

import httpx

from . import __version__
from .build_info import runtime_build_info
from .service import (
    BacktestRequest,
    INTRADAY_FEATURE_FORMULA_VERSION,
    REGIME_FORMULA_VERSION,
    SENTIMENT_FORMULA_VERSION,
    execute_backtest,
)
from bktstr_cache.derived import CACHE_FORMAT_VERSION
from .provenance import capability_provenance


CAPABILITIES = {
    "service": "bktstr",
    "version": __version__,
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
    "regime": {
        "parameter": "regime",
        "benchmark_parameter": "benchmark",
        "fields": [
            "day_close",
            "day_sma20",
            "day_sma50",
            "day_sma20_slope5",
            "day_return20",
            "benchmark_return20",
            "relative_return20",
            "sentiment_direction",
            "sentiment_confidence",
            "sentiment_momentum20",
            "sentiment_momentum60",
            "sentiment_momentum",
            "sentiment_component_spread",
            "sentiment_volatility_stress",
            "sentiment_fragility",
        ],
        "sentiment_fields_require": "sentiment=true",
        "operators": ["lt", "lte", "gt", "gte", "eq"],
        "lookahead_guard": "intraday session uses latest completed daily feature row strictly before that session date",
    },
    "sentiment": {
        "enabled_parameter": "sentiment",
        "sector_benchmark_parameter": "sentiment_sector_benchmark",
        "market_benchmark_parameter": "sentiment_market_benchmark",
        "direction_range": [-1.0, 1.0],
        "confidence_range": [0.0, 1.0],
        "momentum_range": [-1.0, 1.0],
        "fragility_range": [0.0, 1.0],
        "multiplier_range": [0.5, 1.5],
        "raw_features": [
            "relative_return63_sector",
            "relative_return126_sector",
            "relative_return63_market",
            "relative_return126_market",
            "distance_from_52w_high",
            "sma50_slope20",
            "sma100_slope20",
            "sma200_slope20",
            "days_below_sma50",
            "ema50",
            "ema100",
            "ema200",
            "atr20_pct",
            "realized_vol20",
            "realized_vol60",
            "volatility_ratio",
            "persistence_occupancy",
            "normalized_ema50_distance",
            "persistence_pressure_raw",
        ],
        "component_scores": [
            "sentiment_leadership_score",
            "sentiment_trend_score",
            "sentiment_peak_score",
            "sentiment_persistence_score",
        ],
        "outputs": [
            "sentiment_direction",
            "sentiment_confidence",
            "sentiment_completeness",
            "sentiment_multiplier_long",
            "sentiment_multiplier_short",
            "sentiment_momentum20",
            "sentiment_momentum60",
            "sentiment_momentum",
            "sentiment_component_spread",
            "sentiment_volatility_stress",
            "sentiment_fragility",
        ],
        "component_weights": {
            "leadership": 0.35,
            "trend": 0.30,
            "peak": 0.20,
            "persistence": 0.15,
        },
        "multipliers_are_informational": True,
        "filterable_fields": [
            "sentiment_direction",
            "sentiment_confidence",
            "sentiment_momentum20",
            "sentiment_momentum60",
            "sentiment_momentum",
            "sentiment_component_spread",
            "sentiment_volatility_stress",
            "sentiment_fragility",
        ],
        "coverage_fields": [
            "requested_warmup_start",
            "coverage_start",
            "coverage_end",
            "warmup_degraded",
        ],
        "optional_warmup_behavior": "degrade completeness and report coverage; required-period data remains strict",
        "data_profile_parameter": "sentiment_data_profile",
        "sources_parameter": "sentiment_sources",
        "data_profiles": capability_provenance(),
        "lookahead_guard": "intraday session uses latest completed sentiment row strictly before that session date",
    },
    "execution_model": {
        "entry": "next bar open after signal",
        "same_bar_stop_target": "stop first (conservative)",
        "slippage": "applied adversely to entry and exit",
        "default_regular_hours_only": True,
        "default_same_day_only": True,
        "entry_window": "optional entry_start_time/entry_end_time in America/New_York, HH:MM; end is exclusive",
    },
    "providers": {
        "massive": "full-range pagination with 429/5xx retry; used when MASSIVE_API_KEY is configured",
        "yahoo": "fallback for recent intraday data only",
    },
    "release": {
        "build": runtime_build_info(),
        "feature_formula_versions": {
            "intraday": INTRADAY_FEATURE_FORMULA_VERSION,
            "regime": REGIME_FORMULA_VERSION,
            "sentiment": SENTIMENT_FORMULA_VERSION,
        },
        "derived_cache_format_version": CACHE_FORMAT_VERSION,
    },
    "cache": {
        "type": "daily compressed OHLCV files",
        "persistent_when": "Railway Volume is attached or BKTSTR_CACHE_DIR is set",
        "default_path": "RAILWAY_VOLUME_MOUNT_PATH/bktstr-cache or /tmp/bktstr-cache",
        "raw": {
            "type": "daily compressed OHLCV files",
            "persistent_when": "Railway Volume is attached or BKTSTR_CACHE_DIR is set",
            "default_path": "RAILWAY_VOLUME_MOUNT_PATH/bktstr-cache or /tmp/bktstr-cache",
        },
        "derived": {
            "type": "deterministic feature/context DataFrames",
            "namespaces": ["intraday_features", "daily_regime", "daily_sentiment"],
            "toggle": "BKTSTR_DERIVED_CACHE_ENABLED",
            "default_enabled": True,
            "override_path_variable": "BKTSTR_DERIVED_CACHE_DIR",
            "strategy_decisions_cached": False,
        },
    },
}


def health_payload() -> dict:
    return {
        "status": "ok",
        "service": "bktstr",
        "version": __version__,
        **runtime_build_info(),
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
        entry_start_time=_first(params, "entry_start_time", "") or None,
        entry_end_time=_first(params, "entry_end_time", "") or None,
        regime=_first(params, "regime", "") or None,
        benchmark=_first(params, "benchmark", "") or None,
        sentiment=_bool(_first(params, "sentiment", "false")),
        sentiment_sector_benchmark=_first(params, "sentiment_sector_benchmark", "") or None,
        sentiment_market_benchmark=_first(params, "sentiment_market_benchmark", "") or None,
        sentiment_data_profile=_first(params, "sentiment_data_profile", "clean"),
        sentiment_sources=_first(params, "sentiment_sources", "") or None,
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
    server_version = f"BKTSTR/{__version__}"

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
            self._json(200, health_payload())
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
