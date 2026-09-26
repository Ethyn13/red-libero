"""Tree-based safety authoring with typed predicate and scene-entity pickers."""

from copy import deepcopy
import tkinter as tk
from tkinter import ttk

from .catalog import OPERATORS, PREDICATES, SELECTORS
from .expressions import RuleError, format_expression, signature_for, validate_expression
from .tree_model import (LABELS, RuleTree, child_indices, describe, display_expression,
                         make_operator, rename_binding)
from gui_modules.studio_theme import COLORS, button


def label(parent, text, **kwargs):
    return tk.Label(parent, text=text, bg=COLORS["surface"], fg=COLORS["text"], **kwargs)


def searchable(combo, values):
    values = tuple(dict.fromkeys(values))
    combo.configure(values=values)

    def filter_values(event):
        if event.keysym not in ("Up", "Down", "Return", "Escape", "Tab"):
            query = combo.get().casefold()
            combo.configure(values=[value for value in values if query in value.casefold()])

    combo.bind("<KeyRelease>", filter_values)


class NodeDialog:
    def __init__(self, owner, action, path, node=None, preset=None):
        self.owner, self.action, self.path = owner, action, path
        self.original = deepcopy(node)
        self.window = tk.Toplevel(owner.winfo_toplevel())
        self.window.title({"add": "Add safety rule", "child": "Insert child condition",
                           "replace": "Replace condition", "edit": "Edit node", "wrap": "Wrap condition"}[action])
        self.window.geometry("620x540")
        self.window.minsize(580, 500)
        self.window.configure(bg=COLORS["surface"])
        self.window.transient(owner.winfo_toplevel())
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _: self.close())
        panel = ttk.Frame(self.window, padding=18)
        panel.pack(fill="both", expand=True)
        panel.columnconfigure(1, weight=1)
        seed = node if action in ("edit", "replace") else None
        self.kind = tk.StringVar(value="Operator" if action == "wrap" or (seed and seed[0] in OPERATORS) else "Predicate")
        label(panel, "Node kind").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=6)
        kind = ttk.Combobox(panel, textvariable=self.kind, values=("Predicate", "Operator"), state="readonly", width=40)
        kind.grid(row=0, column=1, sticky="ew")
        if action in ("wrap", "edit"):
            kind.configure(state="disabled")
        kind.bind("<<ComboboxSelected>>", lambda _: self.set_kind())
        label(panel, "Predicate / operator").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=6)
        self.choice = ttk.Combobox(panel, state="readonly", width=40)
        self.choice.grid(row=1, column=1, sticky="ew")
        self.choice.bind("<<ComboboxSelected>>", lambda _: self.build_fields())
        self.description = label(panel, "", anchor="w", justify="left", wraplength=550)
        self.description.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 12))
        self.form = ttk.Frame(panel)
        self.form.grid(row=3, column=0, columnspan=2, sticky="nsew")
        panel.rowconfigure(3, weight=1)
        self.message = tk.StringVar(value="Select scene nouns from the lists, or type a name, type, or selector.")
        label(panel, "", textvariable=self.message, wraplength=550, anchor="w", justify="left").grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=10)
        actions = ttk.Frame(panel)
        actions.grid(row=5, column=0, columnspan=2, sticky="ew")
        button(actions, "Cancel", self.close, compact=True).pack(side="right")
        self.confirm = button(actions, "Update node" if action == "edit" else "Insert node", self.accept, primary=True, compact=True)
        self.confirm.pack(side="right", padx=8)
        self.set_kind(preset or (seed[0] if seed else None))
        if action == "edit" and node and node[0] in OPERATORS:
            self.choice.configure(state="disabled")

    def op(self):
        return next((op for op, text in LABELS.items() if text == self.choice.get()), self.choice.get())

    def set_kind(self, preset=None):
        values = list(LABELS.values()) if self.kind.get() == "Operator" else sorted(PREDICATES)
        self.choice.configure(values=values)
        self.choice.set(LABELS.get(preset, preset) if preset else (LABELS["cumu"] if self.kind.get() == "Operator" else "fall"))
        self.build_fields()

    def _field(self, row, key, caption, value="", values=None, spin=False):
        label(self.form, caption, anchor="w").grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
        if spin:
            widget = ttk.Spinbox(self.form, from_=1, to=1000000)
        elif values is not None:
            widget = ttk.Combobox(self.form)
            searchable(widget, values)
        else:
            widget = ttk.Entry(self.form)
        widget.grid(row=row, column=1, sticky="ew", pady=5)
        widget.insert(0, value)
        self.fields[key] = widget
        return widget

    def build_fields(self, signature_changed=False):
        chosen_signature = self.signature.get() if signature_changed else None
        for widget in self.form.winfo_children():
            widget.destroy()
        self.form.columnconfigure(1, weight=1)
        self.fields = {}
        op = self.op()
        original = self.original if self.action == "edit" and self.original and self.original[0] == op else None
        if op in OPERATORS:
            self.description.configure(text=OPERATORS[op])
            if op == "cumu":
                self._field(0, "threshold", "True samples", original[2] if original else "5", spin=True)
                label(self.form, "Counts samples where the child condition is true.\nFalse samples retain the count; reset clears it.",
                      justify="left", anchor="w", wraplength=530).grid(row=1, column=0, columnspan=2, sticky="w", pady=12)
            elif op in ("exists", "forall"):
                self._field(0, "variable", "Object variable", original[1][0] if original else self.owner.model.fresh_variable())
                self._field(1, "selector", "Objects to check", original[1][2] if original else "@objects",
                            list(SELECTORS) + ["@objects:*knife*"] + self.owner.nouns)
                label(self.form, "The child can use this variable as a noun.\nexists: at least one match. forall: every match.",
                      justify="left", anchor="w", wraplength=530).grid(row=2, column=0, columnspan=2, sticky="w", pady=12)
            else:
                label(self.form, "Add or replace child conditions in the tree after inserting this node.",
                      wraplength=530, justify="left").grid(row=0, column=0, columnspan=2, sticky="w", pady=12)
            return
        spec = PREDICATES[op]
        self.description.configure(text=spec.description)
        signatures = [", ".join(kinds) or "No arguments" for kinds in spec.signatures]
        self.signature = ttk.Combobox(self.form, values=signatures, state="readonly")
        label(self.form, "Arguments").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=5)
        self.signature.grid(row=0, column=1, sticky="ew", pady=5)
        current = signature_for(original) if original else spec.signatures[0]
        self.signature.set(chosen_signature or ", ".join(current) or "No arguments")
        self.signature.bind("<<ComboboxSelected>>", lambda _: self.build_fields(True))
        self.argument_kinds = spec.signatures[signatures.index(self.signature.get())]
        original_args = original[1:] if original and signature_for(original) == self.argument_kinds else []
        variables = self.owner.model.variables_at(self.path)
        if self.action == "child" and self.path:
            parent = self.owner.model.node(self.path)
            if parent and parent[0] in ("exists", "forall"):
                variables = variables + [parent[1][0]]
        nouns = variables + self.owner.nouns + list(SELECTORS)
        for index, kind in enumerate(self.argument_kinds):
            value = original_args[index] if original_args else "robot" if kind == "robot" else "all" if kind == "parts" else ""
            if isinstance(value, list):
                value = " ".join(value)
            caption = f"Object / region {index + 1}"
            choices = nouns
            if kind == "number":
                caption, choices = ("Threshold (m)" if "distance" in op else "Threshold (N)"), None
            elif kind == "robot":
                caption, choices = "Robot", ["robot", "robot0", "arm"]
            elif kind == "parts":
                caption, choices = f"Geometry parts {index + 1}", ["all"]
            self._field(index + 1, index, caption, str(value), choices)

    def expression(self):
        op = self.op()
        if op not in OPERATORS:
            args = []
            for index, kind in enumerate(self.argument_kinds):
                value = self.fields[index].get().strip().lower()
                if kind == "parts":
                    parts = value.replace(",", " ").split()
                    if not parts or any(char in "();" for part in parts for char in part):
                        raise RuleError("Use 'all' or geometry suffixes separated by spaces.")
                    value = parts if len(parts) > 1 else value
                elif not value or any(char.isspace() or char in "();" for char in value):
                    raise RuleError(f"Choose a valid value for argument {index + 1}.")
                args.append(value)
            return [op, *args]
        original = self.original if self.action == "edit" and self.original and self.original[0] == op else None
        variable = self.fields["variable"].get().strip().lower() if "variable" in self.fields else "?x"
        selector = self.fields["selector"].get().strip().lower() if "selector" in self.fields else "@objects"
        threshold = self.fields["threshold"].get().strip() if "threshold" in self.fields else "5"
        for value in (variable, selector, threshold):
            if not value or any(char.isspace() or char in "();" for char in value):
                raise RuleError("Use a single variable, selector, or numeric value in each field.")
        if original:
            node = deepcopy(original)
            if op == "cumu":
                node[2] = threshold
            elif op in ("exists", "forall"):
                node = rename_binding(node, variable)
                node[1][2] = selector
            return node
        child = self.owner.model.node(self.path) if self.action == "wrap" else None
        return make_operator(op, variable, selector, threshold, child)

    def accept(self):
        try:
            node = self.expression()

            def fill_slots(value):
                return ["true"] if value is None else [fill_slots(part) for part in value] if isinstance(value, list) else value

            variables = self.owner.model.variables_at(self.path)
            if self.action == "child" and self.path:
                parent = self.owner.model.node(self.path)
                if parent and parent[0] in ("exists", "forall"):
                    variables += [parent[1][0]]
            validate_expression(fill_slots(node), frozenset(variables))
            self.owner.commit(self.action, self.path, node)
        except (ValueError, KeyError) as error:
            self.message.set(str(error))
            return False
        self.close()
        return True

    def close(self):
        self.window.grab_release()
        self.window.destroy()
        parent = self.owner.winfo_toplevel()
        if parent.winfo_exists():
            parent.grab_set()
        self.owner.node_dialog = None


class SafetyTreeEditor(ttk.Frame):
    def __init__(self, parent, inventory, on_change, status, before_edit):
        super().__init__(parent)
        self.model = RuleTree()
        self.on_change, self.status, self.before_edit = on_change, status, before_edit
        self.nouns = [item["name"] for item in inventory] + sorted({item["type"] for item in inventory if item["type"]})
        self.node_dialog = None
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        actions = ttk.Frame(self)
        actions.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.buttons = {}
        for text, action in [("Add rule", "add"), ("Insert child", "child"), ("Edit node", "edit"), ("Replace", "replace")]:
            self.buttons[action] = button(actions, text, lambda a=action: self.open_node(a), compact=True)
            self.buttons[action].pack(side="left", padx=(0, 5))
        for text, action in [("Remove", "remove"), ("Undo", "undo"), ("Redo", "redo")]:
            self.buttons[action] = button(actions, text, lambda a=action: self.operate(a), compact=True)
            self.buttons[action].pack(side="left", padx=(0, 5))
        label(self, "Select a node to edit it. Insert children into logic nodes; nouns appear under their predicate.",
              anchor="w", wraplength=800).grid(row=1, column=0, sticky="ew", pady=(0, 8))
        panes = ttk.Panedwindow(self, orient="horizontal")
        panes.grid(row=2, column=0, sticky="nsew")
        tree_frame = ttk.Frame(panes)
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(tree_frame, columns=("value",), show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Rule / condition")
        self.tree.heading("value", text="Arguments / scope")
        self.tree.column("#0", width=320, minwidth=150)
        self.tree.column("value", width=220, minwidth=110)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        self.tree.tag_configure("missing", foreground=COLORS["danger"])
        self.tree.tag_configure("argument", foreground=COLORS["muted"])
        panes.add(tree_frame, weight=3)
        details = ttk.Frame(panes, padding=(14, 0, 0, 0), width=270)
        panes.add(details, weight=1)
        label(details, "Selected node", font=("TkDefaultFont", 11, "bold"), anchor="w").pack(fill="x")
        self.detail = tk.Text(details, width=27, height=3, wrap="word", relief="flat", bg=COLORS["surface"],
                              fg=COLORS["text"], padx=0, pady=10)
        self.detail.pack(fill="both", expand=True)
        label(details, "Wrap selected condition with", anchor="w").pack(fill="x", pady=(10, 4))
        self.wrap = ttk.Combobox(details, values=list(LABELS.values()), state="readonly", width=27)
        self.wrap.set(LABELS["cumu"])
        self.wrap.pack(fill="x")
        self.buttons["wrap"] = button(details, "Wrap node…", self.wrap_node, compact=True)
        self.buttons["wrap"].pack(fill="x", pady=6)
        movement = ttk.Frame(details)
        movement.pack(fill="x")
        self.buttons["up"] = button(movement, "Move up", lambda: self.operate("up"), compact=True)
        self.buttons["up"].pack(side="left", padx=(0, 6))
        self.buttons["down"] = button(movement, "Move down", lambda: self.operate("down"), compact=True)
        self.buttons["down"].pack(side="left")
        self.tree.bind("<<TreeviewSelect>>", self.select)
        self.tree.bind("<Double-1>", lambda _: self.open_node("edit"))
        self.render()

    def path(self):
        selected = self.tree.selection()
        return self.paths.get(selected[0], ()) if selected else ()

    def render(self, selected=()):
        closed = {self.paths[item] for item in getattr(self, "paths", {})
                  if self.tree.exists(item) and not self.tree.item(item, "open") and self.tree.get_children(item)}
        self.tree.delete(*self.tree.get_children())
        self.paths = {"root": ()}
        self.items = {(): "root"}
        self.tree.insert("", "end", iid="root", text="Independent violation rules", values=("Any rule can trigger an event",), open=True)

        def add(parent, path, node):
            caption, value = describe(node)
            item = "n" + "_".join(map(str, path))
            self.paths[item], self.items[path] = path, item
            prefix = f"Rule {path[0] + 1}: " if len(path) == 1 else ""
            self.tree.insert(parent, "end", iid=item, text=prefix + caption, values=(value,), open=path not in closed,
                             tags=("missing",) if node is None else ())
            if node is None:
                return
            op = node[0]
            if op in ("exists", "forall"):
                args = [("Object variable", node[1][0]), ("Objects to check", node[1][2])]
            elif op == "cumu":
                args = [("True samples", node[2])]
            elif op in OPERATORS:
                args = []
            else:
                args = [(f"{kind.title()} {index}", format_expression(value))
                        for index, (kind, value) in enumerate(zip(signature_for(node), node[1:]), 1)]
            for index, (key, value) in enumerate(args):
                arg = item + "a" + str(index)
                self.tree.insert(item, "end", iid=arg, text=key, values=(value,), tags=("argument",))
                self.paths[arg] = path
            for index in child_indices(node):
                add(item, path + (index,), node[index])

        for index, rule in enumerate(self.model.rules):
            add("root", (index,), rule)
        item = self.items.get(selected, "root")
        self.tree.selection_set(item)
        self.tree.see(item)
        self.select()

    def select(self, _event=None):
        path = self.path()
        node = self.model.node(path) if path else None
        if not path:
            text = "Each rule is a violation condition. A true rule records an event.\n\nAdd a rule to begin. Logic operators combine child conditions; predicate arguments are scene nouns or thresholds."
        elif node is None:
            text = "This condition is unfinished.\n\nChoose Insert child or Replace to select a predicate or operator. Incomplete rules cannot be applied."
        else:
            op = node[0]
            description = OPERATORS.get(op) or PREDICATES[op].description
            text = describe(node)[0] + "\n\n" + description + "\n\n" + display_expression(node)
            if op == "exists":
                text += "\n\nExample: any object falls means at least one selected object satisfies fall. It does not count samples; use cumu for that."
            variables = self.model.variables_at(path)
            if variables:
                text += "\n\nAvailable object variables: " + ", ".join(variables)
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.configure(state="disabled")
        for key in ("edit", "replace", "remove", "wrap", "up", "down"):
            self.buttons[key].configure(state="normal" if path else "disabled")
        self.buttons["undo"].configure(state="normal" if self.model.undo_stack else "disabled")
        self.buttons["redo"].configure(state="normal" if self.model.redo_stack else "disabled")

    def open_node(self, action, preset=None):
        if not self.before_edit():
            return None
        path = () if action == "add" else self.path()
        node = self.model.node(path) if path else None
        if action in ("edit", "replace", "wrap") and not path:
            self.status("Select a condition first.")
            return None
        if action == "edit" and node is None:
            action = "replace"
        if action == "child" and node is not None and node[0] not in ("and", "or") and not any(node[i] is None for i in child_indices(node)):
            self.status("No empty child slot. Select a child to edit it, or wrap this node in and/or.")
            return None
        self.node_dialog = NodeDialog(self, action, path, node, preset)
        return self.node_dialog

    def wrap_node(self):
        op = next(op for op, text in LABELS.items() if text == self.wrap.get())
        return self.open_node("wrap", op)

    def commit(self, action, path, node):
        if action == "add":
            selected = self.model.add_rule(node)
        elif action == "child":
            selected = self.model.insert_child(path, node)
        else:
            selected = self.model.replace(path, node)
        self.changed(selected)

    def operate(self, action):
        if not self.before_edit():
            return
        try:
            path = self.path()
            if action in ("up", "down"):
                path = self.model.move(path, -1 if action == "up" else 1)
            elif action == "remove":
                path = self.model.remove(path)
            else:
                getattr(self.model, action)()
                path = ()
            self.changed(path)
        except ValueError as error:
            self.status(str(error))

    def changed(self, path=()):
        self.render(path)
        self.on_change(self.model.text())
        self.status("Draft updated. Validate and Apply to activate it; Undo restores the previous tree.")
