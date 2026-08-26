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


__all__ = ["SemanticValidationError"]
