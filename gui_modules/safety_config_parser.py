"""Parse monitor expressions without flattening logical operators."""

from pathlib import Path

from gui_modules.safety.expressions import RuleError, parse_forms, validate_expression

DEFAULT_CONFIG = Path(__file__).with_name("safety_monitoring_config.bddl")


def parse_safety_text(text):
    forms = parse_forms(text)
    if len(forms) != 1 or not forms[0] or forms[0][0] != "define":
        raise RuleError("Expected one (define ... (:safety_rules ...)) form.")
    sections = [part for part in forms[0][1:] if isinstance(part, list) and part and part[0] == ":safety_rules"]
    if len(sections) != 1:
        raise RuleError("Expected exactly one :safety_rules section.")
    rules = sections[0][1:]
    def normalize(rule):
        if not isinstance(rule, list):
            return rule
        if len(rule) >= 4 and rule[0] == "cumu" and isinstance(rule[1], str):
            rule = ["cumu", rule[1:-1], rule[-1]]
        return [normalize(item) for item in rule]
    rules = [normalize(rule) for rule in rules]
    for index, rule in enumerate(rules, 1):
        try:
            validate_expression(rule)
        except RuleError as error:
            raise RuleError(f"Rule {index}: {error}") from error
    return rules


def parse_safety_config(config_path):
    path = Path(config_path)
    return {"safety_rules": parse_safety_text(path.read_text(encoding="utf-8")), "config_path": str(path)}


def get_safety_rules_from_config(config_path=None):
    return parse_safety_config(config_path or DEFAULT_CONFIG)["safety_rules"]
