from __future__ import annotations

from collections.abc import Iterable


QUALITY_TIERS = {
    "A": {
        "label": "clean",
        "description": "objective point-in-time market data with deterministic transformation",
    },
    "B": {
        "label": "structured",
        "description": "reliable structured data whose interpretation or revision history requires care",
    },
    "C": {
        "label": "derived",
        "description": "model-transformed narrative, text, or other derived information",
    },
    "D": {
        "label": "experimental",
        "description": "esoteric, low-confidence, or difficult-to-reconstruct information",
    },
}

ARTIFACT_TIERS = {
    "source_arrays": {
        "tier": "A",
        "description": "immutable point-in-time source arrays before derived calculation",
    },
    "deterministic_measurements": {
        "tier": "B",
        "description": "immutable validated measurements calculated deterministically from Tier A arrays",
    },
}

SOURCE_REGISTRY = {
    "price": {
        "id": "price",
        "tier": "A",
        "description": "subject daily OHLC plus sector/market daily closes transformed into price-implied sentiment",
        "point_in_time_safe": True,
        "model_derived": False,
        "available": True,
    },
    "options": {
        "id": "options",
        "tier": "B",
        "description": "historical options positioning/skew (future source)",
        "point_in_time_safe": True,
        "model_derived": False,
        "available": False,
    },
    "analyst": {
        "id": "analyst",
        "tier": "B",
        "description": "point-in-time analyst and estimate revisions (future source)",
        "point_in_time_safe": True,
        "model_derived": False,
        "available": False,
    },
    "macro": {
        "id": "macro",
        "tier": "B",
        "description": "point-in-time macro releases and market expectations (future source)",
        "point_in_time_safe": True,
        "model_derived": False,
        "available": False,
    },
    "news": {
        "id": "news",
        "tier": "C",
        "description": "model-derived historical news narrative/tone (future source)",
        "point_in_time_safe": True,
        "model_derived": True,
        "available": False,
    },
    "social": {
        "id": "social",
        "tier": "D",
        "description": "experimental social/narrative sentiment (future source)",
        "point_in_time_safe": False,
        "model_derived": True,
        "available": False,
    },
}

DATA_PROFILES = {
    "clean": {
        "label": "clean",
        "allowed_tiers": ("A",),
        "default_sources": ("price",),
    },
}
DEFAULT_DATA_PROFILE = "clean"


def _parse_sources(value: str | Iterable[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        candidates = [part.strip().lower() for part in value.split(",")]
    else:
        candidates = [str(part).strip().lower() for part in value]
    seen: set[str] = set()
    result: list[str] = []
    for source in candidates:
        if source and source not in seen:
            seen.add(source)
            result.append(source)
    return tuple(result)


def resolve_sentiment_sources(
    profile: str | None = None,
    sources: str | Iterable[str] | None = None,
) -> tuple[str, tuple[str, ...]]:
    normalized_profile = (profile or DEFAULT_DATA_PROFILE).strip().lower()
    if normalized_profile not in DATA_PROFILES:
        raise ValueError(f"sentiment data profile '{normalized_profile}' is not available")

    requested = _parse_sources(sources)
    if not requested:
        requested = tuple(DATA_PROFILES[normalized_profile]["default_sources"])

    allowed_tiers = set(DATA_PROFILES[normalized_profile]["allowed_tiers"])
    for source_id in requested:
        source = SOURCE_REGISTRY.get(source_id)
        if source is None or not source["available"]:
            raise ValueError(f"sentiment source '{source_id}' is not available in this build")
        if source["tier"] not in allowed_tiers:
            raise ValueError(
                f"sentiment source '{source_id}' tier {source['tier']} is not allowed by profile '{normalized_profile}'"
            )
    return normalized_profile, requested


def sentiment_provenance(profile: str, sources: Iterable[str]) -> dict:
    source_rows = [dict(SOURCE_REGISTRY[source_id]) for source_id in sources]
    non_clean = any(row["tier"] != "A" for row in source_rows)
    all_point_in_time_safe = bool(source_rows) and all(row["point_in_time_safe"] for row in source_rows)
    return {
        "profile": profile,
        "non_clean_data_used": non_clean,
        "all_point_in_time_safe": all_point_in_time_safe,
        "sources": source_rows,
    }


def capability_provenance() -> dict:
    return {
        "default": DEFAULT_DATA_PROFILE,
        "available_profiles": {
            name: {
                "label": spec["label"],
                "allowed_tiers": list(spec["allowed_tiers"]),
                "default_sources": list(spec["default_sources"]),
            }
            for name, spec in DATA_PROFILES.items()
        },
        "tiers": QUALITY_TIERS,
        "artifact_tiers": {key: dict(value) for key, value in ARTIFACT_TIERS.items()},
        "sources": {key: dict(value) for key, value in SOURCE_REGISTRY.items()},
    }
