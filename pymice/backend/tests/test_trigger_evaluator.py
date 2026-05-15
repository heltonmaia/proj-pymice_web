"""Tests for the per-frame trigger evaluator."""

from app.processing.trigger_evaluator import TriggerEvaluator
from app.models.schemas import TriggerRule, TriggerMatch, TriggerAction


def _rule(rule_id, event_type, roi_name=None, min_dwell=None, cooldown=0.0):
    return TriggerRule(
        id=rule_id,
        name=rule_id,
        match=TriggerMatch(
            event_type=event_type,
            roi_name=roi_name,
            min_dwell_sec=min_dwell,
            cooldown_sec=cooldown,
        ),
        action=TriggerAction(kind="log", label=rule_id),
    )


def test_simple_match():
    ev = TriggerEvaluator([_rule("t1", "roi_entry", roi_name="center")])
    fires = ev.evaluate(
        [{"type": "roi_entry", "roi_name": "center", "frame_idx": 1, "t": 0.1}]
    )
    assert [f["trigger_id"] for f in fires if not f.get("skipped")] == ["t1"]


def test_filter_by_roi_name():
    ev = TriggerEvaluator([_rule("t1", "roi_entry", roi_name="center")])
    fires = ev.evaluate(
        [{"type": "roi_entry", "roi_name": "edge", "frame_idx": 1, "t": 0.1}]
    )
    assert fires == []


def test_cooldown_silences_second_fire():
    ev = TriggerEvaluator([_rule("t1", "roi_entry", roi_name="center", cooldown=5.0)])
    e1 = {"type": "roi_entry", "roi_name": "center", "frame_idx": 1, "t": 0.0}
    e2 = {"type": "roi_entry", "roi_name": "center", "frame_idx": 60, "t": 2.0}
    e3 = {"type": "roi_entry", "roi_name": "center", "frame_idx": 200, "t": 10.0}
    f1 = ev.evaluate([e1])
    f2 = ev.evaluate([e2])
    f3 = ev.evaluate([e3])

    assert [f for f in f1 if not f.get("skipped")] != []
    assert [f for f in f2 if f.get("skipped") == "cooldown"] != []
    assert [f for f in f3 if not f.get("skipped")] != []


def test_min_dwell_filters_short_visits():
    ev = TriggerEvaluator([_rule("t1", "roi_exit", roi_name="center", min_dwell=1.0)])
    entry = {"type": "roi_entry", "roi_name": "center", "frame_idx": 1, "t": 0.0}
    short_exit = {"type": "roi_exit", "roi_name": "center", "frame_idx": 10, "t": 0.5}
    long_entry = {"type": "roi_entry", "roi_name": "center", "frame_idx": 50, "t": 5.0}
    long_exit = {"type": "roi_exit", "roi_name": "center", "frame_idx": 200, "t": 10.0}

    ev.evaluate([entry])
    fires_short = ev.evaluate([short_exit])
    ev.evaluate([long_entry])
    fires_long = ev.evaluate([long_exit])

    assert fires_short == []
    assert any(not f.get("skipped") for f in fires_long)


def test_multiple_triggers_same_frame():
    ev = TriggerEvaluator(
        [
            _rule("t1", "roi_entry", roi_name="center"),
            _rule("t2", "roi_entry"),
        ]
    )
    fires = ev.evaluate(
        [{"type": "roi_entry", "roi_name": "center", "frame_idx": 1, "t": 0.1}]
    )
    assert {f["trigger_id"] for f in fires if not f.get("skipped")} == {"t1", "t2"}
