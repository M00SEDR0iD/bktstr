from __future__ import annotations

from collections.abc import Iterable


class SemanticValidationError(ValueError):
    """A semantic request rejection with stable public field paths."""

    def __init__(self, message: str, fields: Iterable[str]) -> None:
        normalized = tuple(dict.fromkeys(str(field) for field in fields if field))
        if not normalized:
            raise ValueError("semantic validation fields cannot be empty")
        super().__init__(message)
        self.fields = normalized


__all__ = ["SemanticValidationError"]
