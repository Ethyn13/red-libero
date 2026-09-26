"""Scene-aware safety rule editor and detection diagnostics."""

import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

from gui_modules.safety.catalog import OPERATORS, PREDICATES, SELECTORS
from gui_modules.safety.expressions import SceneSymbols, format_expression
from gui_modules.safety.tree_editor import SafetyTreeEditor
from gui_modules.safety_config_parser import DEFAULT_CONFIG, parse_safety_text
from gui_modules.studio_theme import COLORS, button


class SafetyRulesDialog:
    def __init__(self, shell):
        self.shell, self.editor = shell, shell.editor
        self.window = tk.Toplevel(shell.root)
        self.window.title("Safety rules · red-libero")
        self.window.geometry("1040x740")
        self.window.minsize(860, 620)
        self.window.configure(bg=COLORS["surface"])
        self.window.transient(shell.root)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _: self.close())
        self._after = None
        self._source_text = ""
        self.status = tk.StringVar(value="Build rules with the tree, then Validate and Apply.")
        self.path = Path(getattr(self.editor, "safety_config_path", DEFAULT_CONFIG))
        title = ttk.Frame(self.window, padding=16)
        title.pack(fill="x")
        ttk.Label(title, text="Safety rules", font=(shell.family, 16, "bold")).pack(anchor="w")
        ttk.Label(title, text="Define violation conditions using logic, scene entities, and simulator predicates.").pack(anchor="w", pady=(4, 0))
        style = ttk.Style(self.window)
        style.configure("Safety.TNotebook", background=COLORS["surface"], borderwidth=0)
        style.configure("Safety.TNotebook.Tab", padding=(14, 8), background=COLORS["bg"])
        style.map("Safety.TNotebook.Tab", background=[("selected", COLORS["accent_soft"])],
                  foreground=[("selected", COLORS["accent"])])
        style.configure("Safety.TLabelframe", background=COLORS["surface"], bordercolor=COLORS["line"])
        style.configure("Safety.TLabelframe.Label", background=COLORS["surface"], foreground=COLORS["text"])
        self.tabs = ttk.Notebook(self.window, style="Safety.TNotebook")
        self.tabs.pack(fill="both", expand=True, padx=16)
        self.edit_tab = ttk.Frame(self.tabs, padding=12)
        self.live_tab = ttk.Frame(self.tabs, padding=12)
        self.reference_tab = ttk.Frame(self.tabs, padding=12)
        for tab, text in [(self.edit_tab, "Rule tree"), (self.live_tab, "Live results"), (self.reference_tab, "Predicates & objects")]:
            self.tabs.add(tab, text=text)
        self.source_tab = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(self.source_tab, text="BDDL source (advanced)")
        self._build_editor()
        self._build_results()
        self._build_reference()
        footer = ttk.Frame(self.window, padding=16)
        footer.pack(side="bottom", fill="x", before=self.tabs)
        ttk.Label(footer, textvariable=self.status, wraplength=680).pack(side="left", fill="x", expand=True)
        button(footer, "Close", self.close).pack(side="right")
        monitor = getattr(self.editor, "physics_safety_monitor", None)
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError:
            text = monitor.source_text if monitor else DEFAULT_CONFIG.read_text(encoding="utf-8")
        self.set_source(text)
        self.sync_source()
        self._refresh_results()

    def _build_editor(self):
        self.edit_tab.columnconfigure(0, weight=1)
        self.edit_tab.rowconfigure(2, weight=1)
        tools = ttk.Frame(self.edit_tab)
        tools.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        for caption, callback in [("Open…", self.open_file), ("Save as…", self.save_as),
                                  ("Validate", self.validate), ("Apply", self.apply)]:
            button(tools, caption, callback, primary=caption == "Apply", compact=True).pack(side="left", padx=(0, 6))
        self.source_label = ttk.Label(self.edit_tab, text=str(self.path), wraplength=950)
        self.source_label.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        monitor = getattr(self.editor, "physics_safety_monitor", None)
        inventory = SceneSymbols(monitor.env).inventory() if monitor else []
        self.builder = SafetyTreeEditor(self.edit_tab, inventory, self.set_source, self.status.set, self.sync_source)
        self.builder.grid(row=2, column=0, sticky="nsew")
        self.source_tab.columnconfigure(0, weight=1)
        self.source_tab.rowconfigure(1, weight=1)
        ttk.Label(self.source_tab, text="Advanced BDDL editing. Update tree validates the text; invalid edits never replace the rule tree.",
                  wraplength=850).grid(row=0, column=0, sticky="w", pady=(0, 10))
        self.text = tk.Text(self.source_tab, height=16, undo=True, wrap="word", font=("DejaVu Sans Mono", 11),
                            bg="#f7f9fb", fg=COLORS["text"], relief="flat", padx=12, pady=12)
        self.text.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(self.source_tab, orient="vertical", command=self.text.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set)
        controls = ttk.Frame(self.source_tab)
        controls.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        button(controls, "Update tree", self.update_tree, primary=True, compact=True).pack(side="left")
        button(controls, "Discard source edits", self.discard_source, compact=True).pack(side="left", padx=8)
        ttk.Label(controls, text="Applying rules starts a new monitor history.").pack(side="left", padx=8)

    def set_source(self, text):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text)
        self._source_text = text

    def sync_source(self):
        text = self.text.get("1.0", "end-1c")
        if text == self._source_text and getattr(self, "_tree_loaded", False):
            return True
        try:
            rules = parse_safety_text(text)
        except ValueError as error:
            self.status.set(f"Source not loaded: {error} Fix the source or discard its edits.")
            self.tabs.select(self.source_tab)
            return False
        self.builder.model.load(rules)
        self.builder.render()
        self._source_text = text
        self._tree_loaded = True
        return True

    def update_tree(self):
        if self.sync_source():
            self.tabs.select(self.edit_tab)
            self.status.set("Source loaded into the tree. Apply to activate these rules.")
            return True
        return False

    def discard_source(self):
        self.set_source(self.builder.model.text())
        self._tree_loaded = True
        self.tabs.select(self.edit_tab)
        self.status.set("Source edits discarded; the last rule tree is restored.")

    def _build_results(self):
        self.results = ttk.Treeview(self.live_tab, columns=("status", "progress", "expression"), show="headings", height=7)
        self.results.heading("status", text="State")
        self.results.heading("progress", text="Cumulative samples")
        self.results.heading("expression", text="Violation condition")
        self.results.column("status", width=105, stretch=False)
        self.results.column("progress", width=160, stretch=False)
        self.results.column("expression", width=580)
        self.results.pack(fill="both", expand=True)
        self.results.bind("<<TreeviewSelect>>", self.show_result)
        self.details = tk.Text(self.live_tab, height=6, wrap="word", relief="flat", font=("DejaVu Sans Mono", 10))
        self.details.pack(fill="x", pady=8)
        controls = ttk.Frame(self.live_tab)
        controls.pack(fill="x")
        button(controls, "Export events…", self.export_events, compact=True).pack(side="left")
        ttk.Label(controls, text="  Results update after simulation steps. Free edit does not run detection.").pack(side="left")

    def _build_reference(self):
        self.reference_tab.columnconfigure(0, weight=1)
        self.reference_tab.columnconfigure(1, weight=1)
        self.reference_tab.rowconfigure(1, weight=1)
        ttk.Label(self.reference_tab, text="Predicates and operators").grid(row=0, column=0, sticky="w")
        ttk.Label(self.reference_tab, text="Scene nouns for predicate arguments").grid(row=0, column=1, sticky="w")
        reference = tk.Text(self.reference_tab, width=52, height=12, wrap="word", font=("DejaVu Sans Mono", 10), padx=8, pady=8)
        reference.grid(row=1, column=0, sticky="nsew", padx=(0, 10), pady=8)
        lines = ["LOGIC AND QUANTIFIERS", *OPERATORS.values(), "", "SELECTORS"]
        lines.extend(f"{name}: {description}" for name, description in SELECTORS.items())
        lines.extend(["Instance / type / noun / glob: bowl_1, akita_black_bowl, knife, *knife*",
                      "Short nouns match whole underscore-separated type components; numbered instances remain exact.",
                      "Scoped glob: @objects:*knife*", "", "PREDICATES"])
        lines.extend(f"{name} {spec.syntax}\n  {spec.description}" for name, spec in sorted(PREDICATES.items()))
        reference.insert("1.0", "\n\n".join(lines))
        reference.configure(state="disabled")
        self.entities = ttk.Treeview(self.reference_tab, columns=("kind", "name"), show="headings")
        self.entities.heading("kind", text="Kind")
        self.entities.heading("name", text="Name")
        self.entities.column("kind", width=70, stretch=False)
        self.entities.column("name", width=330)
        self.entities.grid(row=1, column=1, sticky="nsew", pady=8)
        monitor = getattr(self.editor, "physics_safety_monitor", None)
        if monitor:
            for item in SceneSymbols(monitor.env).inventory():
                self.entities.insert("", "end", values=(item["kind"], item["name"]))
        ttk.Label(self.reference_tab, text="Use Rule tree → Add rule / Edit node to select a predicate and its nouns. This tab is a lookup catalog.",
                  wraplength=850).grid(row=2, column=0, columnspan=2, sticky="w", pady=8)

    def validate(self):
        if not self.sync_source():
            return None
        try:
            rules = self.builder.model.validate()
            self.status.set(f"Valid: {len(rules)} independent rules. Object availability is reported during detection.")
            return rules
        except ValueError as error:
            self.status.set(str(error))
            return None

    def apply(self):
        controller = getattr(self.editor, "ai_controller", None)
        if getattr(controller, "is_executing", False) or self.editor.data_collection_mode:
            self.status.set("Finish the AI rollout or leave Human Assist before changing rules.")
            return False
        if self.validate() is None:
            return False
        text = self.text.get("1.0", "end-1c")
        path = Path(self.editor.workspace_dir).parent / "safety_rules.bddl"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(text + "\n", encoding="utf-8")
            temporary.replace(path)
            self.editor.safety_config_path = path
            self.editor._init_physics_safety_monitor()
            monitor = self.editor.physics_safety_monitor
            if not monitor or monitor.config_error:
                raise ValueError(monitor.config_error if monitor else "Monitor initialization failed.")
            if controller:
                controller.safety_monitor = monitor
            self.path = path
            self.source_label.configure(text=str(path))
            self.status.set(f"Applied {len(monitor.config_rules)} rules. Monitoring resumes on the next simulation step.")
            self.shell.log(f"Applied {len(monitor.config_rules)} safety rules.")
            return True
        except (OSError, ValueError) as error:
            self.status.set(str(error))
            return False

    def open_file(self):
        path = filedialog.askopenfilename(parent=self.window, title="Open safety rules", filetypes=[("BDDL rules", "*.bddl"), ("All files", "*")])
        if path:
            try:
                text = Path(path).read_text(encoding="utf-8")
                parse_safety_text(text)
                self.set_source(text)
                self._tree_loaded = False
                self.sync_source()
                self.tabs.select(self.edit_tab)
                self.path = Path(path)
                self.source_label.configure(text=str(path))
                self.status.set("Loaded for editing. Apply to activate these rules.")
            except (OSError, ValueError) as error:
                self.status.set(str(error))

    def save_as(self):
        if self.validate() is None:
            return
        path = filedialog.asksaveasfilename(parent=self.window, title="Save safety rules", defaultextension=".bddl", filetypes=[("BDDL rules", "*.bddl")])
        if path:
            try:
                Path(path).write_text(self.text.get("1.0", "end-1c") + "\n", encoding="utf-8")
                self.status.set(f"Saved {path}. Apply to activate the edited rules.")
            except OSError as error:
                self.status.set(str(error))

    def _refresh_results(self):
        monitor = getattr(self.editor, "physics_safety_monitor", None)
        rows = monitor.rule_results if monitor else []
        if monitor and not rows:
            rows = [{"rule_id": i, "status": "Waiting", "expression": format_expression(rule), "errors": [], "notes": []}
                    for i, rule in enumerate(monitor.config_rules, 1)]
        self._rows = {str(row["rule_id"]): row for row in rows}
        for key in self.results.get_children():
            if key not in self._rows:
                self.results.delete(key)
        for key, row in self._rows.items():
            progress = "; ".join(note.split(": ", 1)[1] for note in row["notes"] if note.startswith("Cumulative samples: "))
            values = (row["status"], progress, row["expression"])
            if self.results.exists(key):
                self.results.item(key, values=values)
            else:
                self.results.insert("", "end", iid=key, values=values)
        if monitor and monitor.config_error:
            self.status.set("Configuration error: " + monitor.config_error)
        self.show_result()
        self._after = self.window.after(500, self._refresh_results)

    def show_result(self, _event=None):
        selected = self.results.selection()
        if selected and selected[0] in self._rows:
            self.details.delete("1.0", "end")
            self.details.insert("1.0", json.dumps(self._rows[selected[0]], indent=2))

    def export_events(self):
        path = filedialog.asksaveasfilename(parent=self.window, title="Export safety events", defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            monitor = self.editor.physics_safety_monitor
            try:
                Path(path).write_text(json.dumps({"config_path": monitor.config_path, "rules": monitor.config_rules,
                    "results": monitor.rule_results, "events": monitor.get_all_events(),
                    "summary": monitor.get_events_summary()}, indent=2), encoding="utf-8")
                self.status.set(f"Events exported to {path}")
            except OSError as error:
                self.status.set(str(error))

    def close(self):
        if self.builder.node_dialog is not None:
            self.builder.node_dialog.close()
        if self._after is not None:
            self.window.after_cancel(self._after)
        self.window.grab_release()
        self.window.destroy()
        self.shell.focus_canvas()
