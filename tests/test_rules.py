import pandas as pd

from bktstr.rules import evaluate_rules, parse_rules


def test_parse_rules_supports_indicator_and_cross_rules():
    rules = parse_rules("close.cross_below:vwap,rsi14.lt:45")
    assert [(r.left, r.op, r.right) for r in rules] == [
        ("close", "cross_below", "vwap"),
        ("rsi14", "lt", 45.0),
    ]


def test_evaluate_rules_requires_all_conditions():
    frame = pd.DataFrame({"close": [101.0, 99.0, 98.0], "vwap": [100.0, 100.0, 99.0], "rsi14": [55.0, 42.0, 44.0]})
    signal = evaluate_rules(frame, parse_rules("close.cross_below:vwap,rsi14.lt:45"))
    assert signal.tolist() == [False, True, False]
