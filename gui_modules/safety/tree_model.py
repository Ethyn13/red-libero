"""Editable rule trees with explicit unfinished conditions and bounded undo."""

from copy import deepcopy

from .expressions import RuleError, format_expression
from gui_modules.safety_config_parser import parse_safety_text


LABELS = {
    "and": "All conditions (and)", "or": "Any condition (or)",
    "not": "Negate condition (not)", "implies": "Implication (implies)",
    "exists": "Any matching object (exists)", "forall": "Every matching object (forall)",
    "cumu": "Cumulative samples (cumu)", "rising": "Becomes true (rising)",
}


def child_indices(node):
    if not node:
        return ()
    if node[0] in ("exists", "forall"):
        return (2,)
    if node[0] in ("cumu", "not", "rising"):
        return (1,)
    if node[0] in ("and", "or", "implies"):
        return tuple(range(1, len(node)))
    return ()


def walk(node):
    yield node
    for index in child_indices(node):
        yield from walk(node[index])


def display_expression(node):
    if node is None:
        return "(CHOOSE_CONDITION)"
    if isinstance(node, list):
        return "(" + " ".join(display_expression(part) for part in node) + ")"
    return str(node)


def describe(node):
    if node is None:
        return "Choose a condition", "Unfinished"
    op = node[0]
    if op in ("exists", "forall"):
        return LABELS[op], f"{node[1][0]} in {node[1][2]}"
    if op == "cumu":
        return LABELS[op], f"At least {node[2]} true samples"
    if op in LABELS:
        return LABELS[op], ""
    return op, " ".join(format_expression(arg) for arg in node[1:])


class RuleTree:
    def __init__(self, rules=()):
        self.rules = deepcopy(list(rules))
        self.undo_stack, self.redo_stack = [], []

    def node(self, path):
        node = self.rules
        for index in path:
            node = node[index]
        return node

    def variables_at(self, path):
        variables = []
        for size in range(1, len(path)):
            node = self.node(path[:size])
            if node and node[0] in ("exists", "forall"):
                variables.append(node[1][0])
        return variables

    def fresh_variable(self):
        used = {node[1][0] for rule in self.rules for node in walk(rule)
                if node and node[0] in ("exists", "forall")}
        return next(name for name in ["?x", "?y", "?z"] + [f"?x{i}" for i in range(10001)] if name not in used)

    def _change(self):
        self.undo_stack.append(deepcopy(self.rules))
        self.undo_stack = self.undo_stack[-100:]
        self.redo_stack.clear()

    def load(self, rules):
        self._change()
        self.rules = deepcopy(rules)

    def replace(self, path, node):
        if not path:
            raise RuleError("Select a condition first.")
        self._change()
        self.node(path[:-1])[path[-1]] = deepcopy(node)
        return path

    def add_rule(self, node):
        self._change()
        self.rules.append(deepcopy(node))
        return (len(self.rules) - 1,)

    def insert_child(self, path, node):
        if not path:
            return self.add_rule(node)
        parent = self.node(path)
        if parent is None:
            return self.replace(path, node)
        slots = child_indices(parent)
        empty = next((index for index in slots if parent[index] is None), None)
        if empty is not None:
            return self.replace(path + (empty,), node)
        if parent[0] not in ("and", "or"):
            raise RuleError("This node has no empty child slot. Select a child to replace it, or wrap this node in and/or.")
        self._change()
        parent.append(deepcopy(node))
        return path + (len(parent) - 1,)

    def remove(self, path):
        if not path:
            raise RuleError("Select a rule or condition to remove.")
        parent = self.node(path[:-1])
        self._change()
        if len(path) == 1:
            parent.pop(path[-1])
        elif parent[0] in ("and", "or") and len(parent) > 2:
            parent.pop(path[-1])
        else:
            parent[path[-1]] = None
        return path[:-1]

    def move(self, path, delta):
        if not path:
            raise RuleError("Select a rule or an and/or child to move.")
        parent = self.node(path[:-1])
        if len(path) > 1 and parent[0] not in ("and", "or"):
            raise RuleError("Only independent rules and and/or children can be reordered.")
        target = path[-1] + delta
        lower = 0 if len(path) == 1 else 1
        if not lower <= target < len(parent):
            return path
        self._change()
        parent[path[-1]], parent[target] = parent[target], parent[path[-1]]
        return path[:-1] + (target,)

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(deepcopy(self.rules))
            self.rules = self.undo_stack.pop()

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(deepcopy(self.rules))
            self.rules = self.redo_stack.pop()

    def text(self):
        lines = ["(define (safety_monitoring)", "  (:safety_rules"]
        lines.extend("    " + display_expression(rule) for rule in self.rules)
        return "\n".join(lines + ["  )", ")"])

    def validate(self):
        if any(node is None for rule in self.rules for node in walk(rule)):
            raise RuleError("Complete every 'Choose a condition' node before applying or exporting rules.")
        return parse_safety_text(self.text())


def make_operator(op, variable="?x", selector="@objects", threshold="5", child=None):
    if op in ("exists", "forall"):
        return [op, [variable, "-", selector], deepcopy(child)]
    if op == "cumu":
        return [op, deepcopy(child), threshold]
    if op in ("and", "or", "implies"):
        return [op, deepcopy(child), None]
    if op in ("not", "rising"):
        return [op, deepcopy(child)]
    raise RuleError(f"Unknown operator: {op}")


def rename_binding(node, variable):
    """Rename only references to this binding; nested bindings keep their scope."""
    node = deepcopy(node)
    old = node[1][0]
    node[1][0] = variable

    def rename(value):
        if not isinstance(value, list):
            return variable if value == old else value
        if value and value[0] in ("exists", "forall") and value[1][0] == old:
            return value
        return [rename(part) for part in value]

    node[2] = rename(node[2])
    return node
