from __future__ import annotations

from collections.abc import Iterable
from typing import Self


class SemanticValidationError(ValueError):
    """A semantic request rejection with stable public field paths."""

    def __init__(self, message: str, fields: Iterable[str]) -> None:
        normalized = tuple(dict.fromkeys(str(field) for field in fields if field))
        if not normalized:
            raise ValueError("semantic validation fields cannot be empty")
        super().__init__(message)
        self.fields = normalized

    def prefixed(self, prefix: str) -> SemanticValidationError:
        """Return the same semantic failure scoped below a compound field."""
        normalized_prefix = str(prefix).strip(".")
        if not normalized_prefix:
            raise ValueError("semantic validation prefix cannot be empty")
        return SemanticValidationError(
            str(self),
            (f"{normalized_prefix}.{field}" for field in self.fields),
        )

    def replace_fields(self, fields: Iterable[str]) -> SemanticValidationError:
        """Return the same semantic failure attributed to adapter-owned fields."""
        return SemanticValidationError(str(self), fields)


class StrategyCompatibilityError(SemanticValidationError):
    """A selected strategy cannot run against part of the typed request."""

    def __init__(
        self,
        message: str,
        fields: Iterable[str],
        *,
        strategy_id: str,
        strategy_version: str,
        required_timeframe: str,
        received_timeframe: str,
    ) -> None:
        super().__init__(message, fields)
        self.strategy_id = strategy_id
        self.strategy_version = strategy_version
        self.required_timeframe = required_timeframe
        self.received_timeframe = received_timeframe

    def _with_fields(self, fields: Iterable[str]) -> Self:
        return type(self)(
            str(self),
            fields,
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            required_timeframe=self.required_timeframe,
            received_timeframe=self.received_timeframe,
        )

    def prefixed(self, prefix: str) -> Self:
        normalized_prefix = str(prefix).strip(".")
        if not normalized_prefix:
            raise ValueError("semantic validation prefix cannot be empty")
        return self._with_fields(
            f"{normalized_prefix}.{field}" for field in self.fields
        )

    def replace_fields(self, fields: Iterable[str]) -> Self:
        return self._with_fields(fields)


__all__ = ["SemanticValidationError", "StrategyCompatibilityError"]
