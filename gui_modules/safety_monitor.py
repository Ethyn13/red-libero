"""Evaluate configured violation conditions and record activation events."""

from collections import Counter
import json
from pathlib import Path
import time

from gui_modules.safety.expressions import ExpressionEvaluator, format_expression, validate_expression
from gui_modules.safety_config_parser import DEFAULT_CONFIG, parse_safety_text


class SafetyMonitor:
    """One event per false-to-true rule activation; failures remain visible."""

    def __init__(self, env, config_path=None, debug=False):
        self.wrapped_env = env if hasattr(env, "env") else None
        self.env = env.env if self.wrapped_env is not None else env
        self.config_path = str(config_path or DEFAULT_CONFIG)
        self.debug = debug
        self.config_rules = []
        self.config_error = ""
        self.source_text = ""
        self.evaluator = ExpressionEvaluator(self.env)
        self.clear_events()
        self.reload_config()

    def clear_events(self):
        self.safety_events = []
        self.rule_results = []
        self.step_count = 0
        self._last_step = None
        self._active = {}
        self._rules_signature = None
        self.evaluator.reset()

    reset = clear_events

    def apply_text(self, text, config_path=None):
        rules = parse_safety_text(text)
        self.config_rules, self.source_text = rules, text
        if config_path is not None:
            self.config_path = str(config_path)
        self.config_error = ""
        self.clear_events()
        return len(rules)

    def reload_config(self):
        try:
            text = Path(self.config_path).read_text(encoding="utf-8")
            rules = parse_safety_text(text)
        except (OSError, ValueError) as error:
            self.config_error = str(error)
            return False
        if rules != self.config_rules or self.config_error:
            self.apply_text(text)
        else:
            self.source_text = text
        return True

    def check_step(self, step):
        if self.config_error:
            return []
        signature = json.dumps(self.config_rules, sort_keys=True)
        if signature != self._rules_signature:
            self.clear_events()
            try:
                for rule in self.config_rules:
                    validate_expression(rule)
            except ValueError as error:
                self.config_error = str(error)
                return []
            self._rules_signature = signature
        if step == self._last_step:
            return []
        if self._last_step is not None and step < self._last_step:
            self.clear_events()
            self._rules_signature = signature
        self.step_count, self._last_step = step, step
        self.evaluator.begin_sample(step)
        events, results, seen = [], [], set()
        for index, rule in enumerate(self.config_rules, 1):
            key = format_expression(rule)
            result = self.evaluator.evaluate(rule)
            status = "Unknown" if result.errors or result.value is None else "Active" if result.value else "Clear"
            if result.notes and all(note.startswith("Empty domain:") for note in result.notes) and result.value is False:
                status = "No matches"
            results.append({"rule_id": index, "expression": key, "status": status,
                            "value": result.value, "objects": sorted(result.objects),
                            "errors": list(dict.fromkeys(result.errors)), "notes": list(dict.fromkeys(result.notes))})
            if result.value is True and not self._active.get(key, False) and key not in seen:
                events.append({"step": step, "rule_id": index, "rule_name": key,
                               "event_type": "rule_activated", "event_description": f"Violation condition active: {key}",
                               "object_name": ", ".join(sorted(result.objects)) or "scene",
                               "objects": sorted(result.objects), "predicate": rule[0], "rule": rule,
                               "logic_operator": rule[0], "is_composite": any(isinstance(v, list) for v in rule[1:]),
                               "timestamp": time.time(), "diagnostics": results[-1]})
                seen.add(key)
            # Unknown samples cannot fabricate a deactivation edge.
            if result.value is not None:
                self._active[key] = bool(result.value)
        self.rule_results = results
        self.safety_events.extend(events)
        return events

    def get_all_events(self):
        return self.safety_events

    def get_events_summary(self):
        return {"total_events": len(self.safety_events),
                "events_by_type": dict(Counter(e["event_type"] for e in self.safety_events)),
                "events_by_object": dict(Counter(e["object_name"] for e in self.safety_events))}

    def get_status(self):
        errors = [error for row in self.rule_results for error in row["errors"]]
        return {"rules": len(self.config_rules), "evaluated": len(self.rule_results),
                "active": sum(row["value"] is True for row in self.rule_results),
                "unknown": sum(row["status"] == "Unknown" for row in self.rule_results),
                "no_matches": sum(row["status"] == "No matches" for row in self.rule_results),
                "error": self.config_error or (errors[0] if errors else ""), "step": self.step_count}
