"""Validated safety expressions with explicit binding and per-sample state."""

from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from itertools import product
import math
import re

from .catalog import OPERATORS, PREDICATES, SELECTORS


class RuleError(ValueError):
    pass


def format_expression(expression):
    if isinstance(expression, list):
        return "(" + " ".join(format_expression(item) for item in expression) + ")"
    return str(expression)


def parse_forms(text):
    if len(text) > 200_000:
        raise RuleError("Rule text exceeds 200 KB.")
    tokens = re.findall(r"\(|\)|[^\s()]+", re.sub(r";[^\n]*", "", text))
    if len(tokens) > 10_000:
        raise RuleError("Rule text exceeds 10,000 tokens.")
    stack, roots = [], []
    for token in tokens:
        if token == "(":
            if len(stack) >= 40:
                raise RuleError("Expression nesting exceeds 40 levels.")
            form = []
            (stack[-1] if stack else roots).append(form)
            stack.append(form)
        elif token == ")":
            if not stack:
                raise RuleError("Unexpected closing parenthesis.")
            stack.pop()
        elif stack:
            stack[-1].append(token.lower())
        else:
            raise RuleError(f"Expected an expression, found {token!r}.")
    if stack:
        raise RuleError("Missing closing parenthesis.")
    return roots


def _number(value):
    try:
        return not isinstance(value, list) and math.isfinite(float(value)) and float(value) >= 0
    except (ValueError, TypeError):
        return False


def signature_for(rule):
    spec = PREDICATES.get(rule[0])
    if not spec:
        raise RuleError(f"Unknown predicate: {rule[0]}")
    for signature in spec.signatures:
        if len(signature) != len(rule) - 1:
            continue
        valid = True
        for kind, arg in zip(signature, rule[1:]):
            if kind == "number":
                valid &= _number(arg)
            elif kind == "parts":
                valid &= (isinstance(arg, str) and bool(arg)) or (
                    isinstance(arg, list) and bool(arg) and all(isinstance(v, str) and v for v in arg))
            elif kind == "robot":
                valid &= arg in ("robot", "robot0", "arm")
            else:
                valid &= isinstance(arg, str) and bool(arg) and not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?|[+-]?(?:nan|inf)", arg)
        if valid:
            return signature
    raise RuleError(f"Invalid arguments for {rule[0]}; expected {spec.syntax or 'no arguments'}.")


def validate_expression(rule, variables=frozenset(), depth=0):
    if depth > 40 or not isinstance(rule, list) or not rule or not isinstance(rule[0], str):
        raise RuleError("Expected a nonempty predicate or logical expression.")
    op = rule[0]
    if op in ("exists", "forall"):
        if len(rule) != 3 or not isinstance(rule[1], list) or len(rule[1]) != 3:
            raise RuleError(f"Use ({op} (?x - selector) expression). Nest quantifiers for multiple variables.")
        variable, separator, selector = rule[1]
        if not isinstance(variable, str) or not re.fullmatch(r"\?[a-z][a-z0-9_]*", variable) or separator != "-":
            raise RuleError("A binding must have the form (?x - selector).")
        if variable in variables:
            raise RuleError(f"Variable {variable} is already bound; use a distinct variable name.")
        validate_selector(selector)
        validate_expression(rule[2], variables | {variable}, depth+1)
    elif op in ("and", "or", "not", "implies", "rising", "cumu"):
        count = len(rule) - 1
        expected = {"not": 1, "rising": 1, "implies": 2, "cumu": 2}
        if (op in expected and count != expected[op]) or (op in ("and", "or") and count < 1):
            raise RuleError(f"Invalid arguments: {OPERATORS[op]}")
        if op == "cumu" and (not _number(rule[-1]) or float(rule[-1]) != int(float(rule[-1])) or int(float(rule[-1])) < 1):
            raise RuleError("cumu requires a positive integer sample count.")
        for child in rule[1:-1] if op == "cumu" else rule[1:]:
            validate_expression(child, variables, depth+1)
    else:
        for kind, value in zip(signature_for(rule), rule[1:]):
            if kind == "object":
                if value.startswith("?"):
                    if value not in variables:
                        raise RuleError(f"Unbound variable: {value}")
                else:
                    validate_selector(value)
    return rule


def validate_selector(selector):
    if not isinstance(selector, str) or not selector or selector.startswith("?"):
        raise RuleError("Expected an object name, type, wildcard, or named selector.")
    if selector.startswith("@") and selector.split(":", 1)[0] not in SELECTORS:
        raise RuleError(f"Unknown selector: {selector}")


class SceneSymbols:
    def __init__(self, env):
        self.env = env
        self.states = getattr(env, "object_states_dict", {})
        self.objects = set(getattr(env, "objects_dict", {}))
        self.fixtures = set(getattr(env, "fixtures_dict", {}))
        self.regions = set(self.states) - self.objects - self.fixtures
        task = getattr(env, "obj_of_interest", []) or []
        self.task = {task} if isinstance(task, str) else set(task)
        self.types = {}
        problem = getattr(env, "parsed_problem", {}) or {}
        for group in ("objects", "fixtures"):
            for kind, names in problem.get(group, {}).items():
                for name in names:
                    self.types[name] = kind

    def resolve(self, selector):
        groups = {"@objects": self.objects, "@fixtures": self.fixtures,
                  "@regions": self.regions, "@all": set(self.states), "@task": self.task}
        if selector in groups:
            return sorted(groups[selector] & set(self.states))
        if ":" in selector and selector.split(":", 1)[0] in groups:
            group, pattern = selector.split(":", 1)
            return sorted(name for name in groups[group] & set(self.states) if fnmatchcase(name, pattern))
        if selector in self.states:
            return [selector]
        if any(c in selector for c in "*?["):
            return sorted(name for name in self.states if fnmatchcase(name, selector))
        if re.search(r"_\d+(?:_|$)", selector):
            return []
        noun = re.compile(r"(?:^|_)" + re.escape(selector) + r"(?:_|$)")
        return sorted(name for name in (self.objects | self.fixtures) & set(self.states)
                      if any(noun.search(value) for value in
                             (self.types.get(name, ""), re.sub(r"_\d+$", "", name))))

    def inventory(self):
        return [{"name": name, "kind": "Object" if name in self.objects else "Fixture" if name in self.fixtures else "Region",
                 "type": self.types.get(name, ""), "task": name in self.task}
                for name in sorted(self.states)]


@dataclass
class Result:
    value: object
    objects: set = field(default_factory=set)
    errors: list = field(default_factory=list)
    notes: list = field(default_factory=list)


def combine(op, results):
    values = [r.value for r in results]
    if op == "and":
        value = False if False in values else None if None in values else True
    else:
        value = True if True in values else None if None in values else False
    witnesses = [r for r in results if r.value is True] if op == "or" and value is True else results
    return Result(value, set().union(*(r.objects for r in witnesses)),
                  [e for r in results for e in r.errors], [n for r in results for n in r.notes])


class ExpressionEvaluator:
    """Cache atomic checks once per sample; temporal operators own their history."""

    def __init__(self, env, max_evaluations=4096):
        self.env = env
        self.symbols = SceneSymbols(env)
        self.max_evaluations = max_evaluations
        self.reset()

    def reset(self):
        self.counters, self.previous = {}, {}
        self.sample = object()
        self.cache = {}
        self.remaining = self.max_evaluations

    def begin_sample(self, sample):
        if sample != self.sample:
            self.sample = sample
            self.cache = {}
            self.remaining = self.max_evaluations
            self.symbols = SceneSymbols(self.env)

    def evaluate(self, rule, bindings=None):
        bindings = bindings or {}
        key = (format_expression(rule), tuple(sorted(bindings.items())))
        if key in self.cache:
            return self.cache[key]
        if self.remaining <= 0:
            return Result(None, errors=["Rule evaluation budget exceeded; narrow object selectors."])
        self.remaining -= 1
        try:
            result = self._evaluate(rule, bindings, key)
        except Exception as error:
            result = Result(None, errors=[f"{format_expression(rule)}: {error}"])
        self.cache[key] = result
        return result

    def _evaluate(self, rule, bindings, key):
        op = rule[0]
        if op in ("exists", "forall"):
            variable, _, selector = rule[1]
            names = self.symbols.resolve(selector)
            if not names:
                return Result(op == "forall", notes=[f"Empty domain: {selector}"])
            children = []
            for name in names:
                children.append(self.evaluate(rule[2], {**bindings, variable: name}))
                if self.remaining <= 0:
                    children.append(Result(None, errors=["Quantifier evaluation budget exceeded."]))
                    break
            return combine("or" if op == "exists" else "and", children)
        if op in ("and", "or"):
            return combine(op, [self.evaluate(child, bindings) for child in rule[1:]])
        if op == "not":
            result = self.evaluate(rule[1], bindings)
            return Result(None if result.value is None else not result.value, result.objects, result.errors, result.notes)
        if op == "implies":
            left, right = self.evaluate(rule[1], bindings), self.evaluate(rule[2], bindings)
            left = Result(None if left.value is None else not left.value, left.objects, left.errors, left.notes)
            return combine("or", [left, right])
        if op in ("cumu", "rising"):
            child = self.evaluate(rule[1], bindings)
            if op == "cumu":
                self.counters[key] = self.counters.get(key, 0) + int(child.value is True)
                value = self.counters[key] >= int(float(rule[2]))
                if child.value is None and not value:
                    value = None
                return Result(value, child.objects, child.errors,
                              child.notes + [f"Cumulative samples: {self.counters[key]}/{rule[2]}"])
            previous = self.previous.get(key)
            self.previous[key] = child.value
            return Result(None if child.value is None else previous is False and child.value is True,
                          child.objects, child.errors, child.notes)
        signature = signature_for(rule)
        arguments, object_slots = [], []
        for index, (kind, arg) in enumerate(zip(signature, rule[1:])):
            if kind == "object":
                names = [bindings[arg]] if arg.startswith("?") else self.symbols.resolve(arg)
                if not names:
                    return Result(None, errors=[f"No scene entity matches '{arg}'."])
                object_slots.append(index)
                arguments.append(names)
            elif kind == "number":
                arguments.append([float(arg)])
            else:
                arguments.append([arg])
        results = []
        for args in product(*arguments):
            atom_key = (op, repr(args))
            if atom_key not in self.cache:
                if self.remaining <= 0:
                    results.append(Result(None, errors=["Predicate evaluation budget exceeded."]))
                    break
                self.remaining -= 1
                names = {args[i] for i in object_slots}
                try:
                    value = self._atom(op, args, signature)
                    self.cache[atom_key] = Result(bool(value), names)
                except Exception as error:
                    self.cache[atom_key] = Result(None, names, [f"{op}{args}: {error}"])
            results.append(self.cache[atom_key])
        return combine("or", results)

    def _atom(self, op, args, signature):
        from libero.libero.envs.predicates import eval_predicate_fn

        values = [self.symbols.states[arg] if kind == "object" else arg
                  for arg, kind in zip(args, signature)]
        if op == "equal":
            return args[0] == args[1]
        if op == "checkarmforce":
            return self.env.check_arm_force(*([args[-1]] if signature and signature[-1] == "number" else []))
        if op == "checkarmstuck":
            return self.env.check_arm_stuck()
        if op in ("checkdistance", "checkgripperdistance"):
            distance = float(eval_predicate_fn(op, *values[:-1]))
            if not math.isfinite(distance):
                raise ValueError("Distance measurement is not finite.")
            return distance <= values[-1]
        if op == "incontactpart":
            return self.env._eval_predicate([op, *args])
        if op == "knock" and len(args) == 2:
            op = "knockbinary"
        return eval_predicate_fn(op, *values)
