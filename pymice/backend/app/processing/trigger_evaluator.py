"""Per-frame trigger rule evaluator.

Holds per-trigger state (last_fired_at, last_entry_t_per_roi).
evaluate() is called by LiveExperiment after emitting frame events; it
returns a list of fire records (one per match), some marked skipped.
The caller is responsible for executing actions and persisting these
records to events.jsonl / WebSocket.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.models.schemas import TriggerRule


@dataclass
class _State:
    last_fired_at: Optional[float] = None
    last_entry_t_per_roi: Dict[str, float] = field(default_factory=dict)


class TriggerEvaluator:
    def __init__(self, rules: List[TriggerRule]):
        self._rules = list(rules)
        self._state: Dict[str, _State] = {r.id: _State() for r in self._rules}

    def replace_rules(self, rules: List[TriggerRule]) -> None:
        self._rules = list(rules)
        new_state = {}
        for r in self._rules:
            new_state[r.id] = self._state.get(r.id, _State())
        self._state = new_state

    def evaluate(self, events: List[dict]) -> List[dict]:
        fires: List[dict] = []

        for evt in events:
            if evt.get("type") == "roi_entry":
                roi_name = evt.get("roi_name") or ""
                t = evt.get("t", 0.0)
                for rule in self._rules:
                    st = self._state[rule.id]
                    st.last_entry_t_per_roi[roi_name] = t

        for evt in events:
            etype = evt.get("type")
            for rule in self._rules:
                m = rule.match
                if m.event_type != etype:
                    continue
                if m.roi_name is not None and evt.get("roi_name") != m.roi_name:
                    continue

                st = self._state[rule.id]
                t = evt.get("t", 0.0)

                if etype == "roi_exit" and m.min_dwell_sec is not None:
                    roi_name = evt.get("roi_name") or ""
                    entry_t = st.last_entry_t_per_roi.get(roi_name)
                    if entry_t is None or (t - entry_t) < m.min_dwell_sec:
                        continue

                if m.cooldown_sec and st.last_fired_at is not None:
                    if (t - st.last_fired_at) < m.cooldown_sec:
                        fires.append(
                            {
                                "trigger_id": rule.id,
                                "frame_idx": evt.get("frame_idx"),
                                "t": t,
                                "skipped": "cooldown",
                            }
                        )
                        continue

                st.last_fired_at = t
                fires.append(
                    {
                        "trigger_id": rule.id,
                        "rule": rule.model_dump(),
                        "frame_idx": evt.get("frame_idx"),
                        "t": t,
                    }
                )

        return fires
