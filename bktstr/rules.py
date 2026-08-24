from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


SUPPORTED_OPS = {"lt", "lte", "gt", "gte", "eq", "cross_below", "cross_above"}


@dataclass(frozen=True)
class Rule:
    left: str
    op: str
    right: str | float


def parse_rules(spec: str) -> list[Rule]:
    if not spec or not spec.strip():
        raise ValueError("at least one entry rule is required")
    parsed: list[Rule] = []
    for raw in spec.split(","):
        raw = raw.strip()
        try:
            lhs, rhs = raw.split(":", 1)
            left, op = lhs.rsplit(".", 1)
        except ValueError as exc:
            raise ValueError(f"invalid rule '{raw}'") from exc
        if op not in SUPPORTED_OPS:
            raise ValueError(f"unsupported operator '{op}'")
        try:
            right: str | float = float(rhs)
        except ValueError:
            right = rhs.strip()
        parsed.append(Rule(left=left.strip(), op=op, right=right))
    return parsed


def _operand(frame: pd.DataFrame, value: str | float) -> pd.Series:
    if isinstance(value, float):
        return pd.Series(value, index=frame.index, dtype=float)
    if value not in frame.columns:
        raise ValueError(f"unknown indicator '{value}'")
    return frame[value]


def evaluate_rules(
    frame: pd.DataFrame,
    rules: list[Rule],
    cross_group: pd.Series | None = None,
) -> pd.Series:
    signal = pd.Series(True, index=frame.index, dtype=bool)
    for rule in rules:
        if rule.left not in frame.columns:
            raise ValueError(f"unknown indicator '{rule.left}'")
        left = frame[rule.left]
        right = _operand(frame, rule.right)
        if rule.op == "lt":
            current = left < right
        elif rule.op == "lte":
            current = left <= right
        elif rule.op == "gt":
            current = left > right
        elif rule.op == "gte":
            current = left >= right
        elif rule.op == "eq":
            current = left == right
        elif rule.op == "cross_below":
            current = (left < right) & (left.shift(1) >= right.shift(1))
            if cross_group is not None:
                current &= cross_group.eq(cross_group.shift(1))
        elif rule.op == "cross_above":
            current = (left > right) & (left.shift(1) <= right.shift(1))
            if cross_group is not None:
                current &= cross_group.eq(cross_group.shift(1))
        else:  # pragma: no cover - protected by parser
            raise ValueError(f"unsupported operator '{rule.op}'")
        signal &= current.fillna(False)
    return signal
