"""Scene Studio layout and UI-to-controller bindings."""

from __future__ import annotations

import logging
import math
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from types import SimpleNamespace

from gui_modules.studio_theme import COLORS as C
from gui_modules.studio_theme import apply_theme, button, decorate_dialog


logger = logging.getLogger(__name__)


class InstructionField:
    def __init__(self, variable, focus_canvas):
        self.variable = variable
        self.focus_canvas = focus_canvas

    @property
    def text(self):
        return self.variable.get()

    def set_val(self, text):
        self.variable.set(text)

    def stop_typing(self):
        self.focus_canvas()


class StudioShell:
    def __init__(self, editor):
        self.editor = editor
        self.root = editor.fig.canvas.manager.window
        self.root.title("red-libero · Scene Studio")
        width = max(1180, min(1480, self.root.winfo_screenwidth() - 60))
        height = max(780, min(920, self.root.winfo_screenheight() - 100))
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(1180, 780)
        self.family = apply_theme(self.root)
        self.root.configure(bg=C["bg"])
        self.canvas = editor.fig.canvas.get_tk_widget()
        for child in self.root.winfo_children():
            if child.winfo_manager() == "pack":
                child.pack_forget()
        self._syncing = False
        self._tree_signature = None
        self._tree_selection = None
        self._events_signature = None
        self._last_mode = None
        self._messages = []
        self.controls = {}
        self._build_header()
        self._build_toolbar()
        self._build_statusbar()
        self.body = tk.Frame(self.root, bg=C["bg"])
        self.body.pack(fill="both", expand=True, padx=14, pady=14)
        self.body.grid_rowconfigure(0, weight=1)
        self.body.grid_columnconfigure(1, weight=1)
        self.left = self._panel(self.body)
        self.left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.left.configure(width=218)
        self.left.grid_propagate(False)
        self.center = tk.Frame(self.body, bg=C["bg"])
        self.center.grid(row=0, column=1, sticky="nsew")
        self.center.grid_columnconfigure(0, weight=1)
        self.center.grid_rowconfigure(1, weight=1)
        self.right = self._panel(self.body)
        self.right.grid(row=0, column=2, sticky="nsew", padx=(12, 0))
        self.right.configure(width=272)
        self.right.grid_propagate(False)
        self._build_objects()
        self._build_workspace()
        self._build_inspector()
        self._setup_figure()
        self.canvas.bind("<Button-1>", lambda e: self.focus_canvas(), add="+")
        self.root.bind("<F1>", lambda e: self.show_help())
        self.editor.fig.canvas.mpl_connect("close_event", lambda event: self.close())
        self.log("Workspace ready. Select an object in the scene or the object list.")
        self.refresh()
        self._after = self.root.after(250, self._tick)

    def _panel(self, parent):
        return tk.Frame(
            parent, bg=C["surface"], highlightthickness=1, highlightbackground=C["line"]
        )

    def show_safety_rules(self):
        from gui_modules.safety.dialog import SafetyRulesDialog
        self.safety_dialog = SafetyRulesDialog(self)
        return self.safety_dialog

    def _label(self, parent, text="", size=10, color=None, bold=False, **kwargs):
        return tk.Label(
            parent,
            text=text,
            font=(self.family, size, "bold" if bold else "normal"),
            bg=parent.cget("bg"),
            fg=color or C["text"],
            anchor="w",
            **kwargs,
        )

    def _section(self, parent, title):
        self._label(parent, title, 9, C["muted"], True).pack(anchor="w", pady=(14, 8))

    def _action(self, parent, label, callback, key=None, primary=False, compact=False):
        control = button(
            parent, label, lambda: self.invoke(label, callback), primary, compact
        )
        if key:
            self.controls[key] = control
        return control

    def _build_header(self):
        header = tk.Frame(self.root, bg=C["header"], height=66)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text="R",
            bg=C["accent"],
            fg="white",
            font=(self.family, 19, "bold"),
            width=2,
            pady=3,
        ).pack(side="left", padx=(20, 12), pady=12)
        self._label(header, "RED-LIBERO", 15, "#ffffff", True).pack(side="left")
        self._label(header, "/", 16, "#698291").pack(side="left", padx=16)
        self._label(header, "Scene Studio", 12, "#c5d4de").pack(side="left")
        help_button = tk.Button(
            header,
            text="Keyboard guide  F1",
            command=self.show_help,
            bg=C["header"],
            fg="#d6e2e9",
            activebackground="#29404f",
            activeforeground="white",
            relief="flat",
            padx=12,
            pady=8,
            cursor="hand2",
        )
        help_button.pack(side="right", padx=18)
        self.connection = self._label(
            header, "SIMULATION WORKSPACE", 9, "#9eb8c5", True
        )
        self.connection.pack(side="right", padx=12)

    def _build_toolbar(self):
        toolbar = tk.Frame(self.root, bg="white", height=60)
        toolbar.pack(fill="x")
        left = tk.Frame(toolbar, bg="white")
        left.pack(side="left", padx=18, pady=10)
        self._action(
            left, "Open scene", self.editor.load_scene_from_folder, "open"
        ).pack(side="left", padx=(0, 7))
        self._action(
            left, "Save scene", self.editor.save_scene_to_folder, "save", primary=True
        ).pack(side="left")
        self._action(left, "Change task", self.editor.switch_bddl_task, "task").pack(
            side="left", padx=(7, 0)
        )
        tk.Frame(left, width=1, height=24, bg=C["line"]).pack(side="left", padx=14)
        self._action(left, "Reset", self.editor.reset_scene, "reset").pack(
            side="left", padx=(0, 6)
        )
        self._action(left, "Resample", self.editor.resample_scene, "resample").pack(
            side="left"
        )
        mode_frame = tk.Frame(toolbar, bg=C["bg"], padx=3, pady=3)
        mode_frame.pack(side="right", padx=18, pady=10)
        self.mode_buttons = {}
        for key, label in [
            ("physics", "Physics"),
            ("free", "Free edit"),
            ("human", "Human"),
            ("ai", "AI policy"),
        ]:
            control = tk.Button(
                mode_frame,
                text=label,
                relief="flat",
                borderwidth=0,
                padx=13,
                pady=8,
                command=lambda k=key: self.invoke("Mode", lambda: self.select_mode(k)),
                bg=C["bg"],
                fg=C["muted"],
                cursor="hand2",
            )
            control.pack(side="left", padx=1)
            self.mode_buttons[key] = control

    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg="white", height=32)
        bar.pack(side="bottom", fill="x")
        bar.pack_propagate(False)
        self.status = self._label(bar, "Ready", 9, C["muted"])
        self.runtime = self._label(bar, "", 9, C["muted"])
        self.runtime.pack(side="right", padx=18)
        self.status.pack(side="left", fill="x", expand=True, padx=18)

    def _build_objects(self):
        self.left.grid_rowconfigure(2, weight=1)
        self.left.grid_columnconfigure(0, weight=1)
        heading = tk.Frame(self.left, bg="white")
        heading.grid(row=0, column=0, sticky="ew", padx=14, pady=(17, 10))
        self._label(heading, "Scene objects", 12, bold=True).pack(side="left")
        self.object_count = self._label(heading, "0", 10, C["muted"])
        self.object_count.pack(side="right")
        search_frame = tk.Frame(self.left, bg="white")
        search_frame.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))
        self._label(search_frame, "Filter by name or type", 9, C["muted"]).pack(
            anchor="w", pady=(0, 5)
        )
        self.search = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search)
        self.search_entry.pack(fill="x")
        self._input_focus(self.search_entry)
        self.search.trace_add("write", lambda *_: self._refresh_objects(force=True))
        tree_frame = tk.Frame(self.left, bg="white")
        tree_frame.grid(row=2, column=0, sticky="nsew", padx=7)
        self.tree = ttk.Treeview(tree_frame, show="tree", selectmode="browse")
        self.tree.column("#0", width=186, minwidth=100)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(tree_frame, command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.tag_configure(
            "group", foreground=C["muted"], font=(self.family, 9, "bold")
        )
        self.tree.bind("<<TreeviewSelect>>", self._select_object)
        bottom = tk.Frame(self.left, bg="white")
        bottom.grid(row=3, column=0, sticky="ew", padx=12, pady=14)
        self.edit_hint = self._label(
            bottom,
            "Add and remove objects in Free edit.",
            9,
            C["muted"],
            wraplength=185,
        )
        self.edit_hint.pack(anchor="w", pady=(0, 10))
        actions = tk.Frame(bottom, bg="white")
        actions.pack(fill="x")
        self._action(
            actions, "+ Add", self.editor.add_object, "add", compact=True
        ).pack(side="left", expand=True, fill="x", padx=(0, 6))
        self._action(
            actions, "Remove", self.remove_object, "remove", compact=True
        ).pack(side="left", expand=True, fill="x")

    def _build_workspace(self):
        instruction = self._panel(self.center)
        instruction.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        top = tk.Frame(instruction, bg="white")
        top.pack(fill="x", padx=16, pady=(13, 7))
        self._label(top, "Task instruction", 11, bold=True).pack(side="left")
        self.task_badge = self._label(top, "BDDL TASK", 9, C["muted"], True)
        self.task_badge.pack(side="right")
        self.instruction = tk.StringVar(value=self.editor._current_instruction)
        self.instruction_entry = ttk.Entry(instruction, textvariable=self.instruction)
        self.instruction_entry.pack(fill="x", padx=16, pady=(0, 14))
        self._input_focus(self.instruction_entry)
        self.instruction.trace_add(
            "write",
            lambda *_: self.editor._on_instruction_change(self.instruction.get()),
        )
        self.instruction_entry.bind("<Return>", lambda event: self.commit_instruction())
        self.editor.instruction_textbox = InstructionField(
            self.instruction, self.focus_canvas
        )
        cameras = self._panel(self.center)
        cameras.grid(row=1, column=0, sticky="nsew", pady=(0, 12))
        cameras.grid_columnconfigure(0, weight=1)
        cameras.grid_rowconfigure(1, weight=1)
        titles = tk.Frame(cameras, bg="white")
        titles.grid(row=0, column=0, sticky="ew", padx=14, pady=14)
        titles.columnconfigure(0, weight=1)
        titles.columnconfigure(1, weight=1)
        main = tk.Frame(titles, bg="white")
        main.grid(row=0, column=0, sticky="ew")
        wrist = tk.Frame(titles, bg="white")
        wrist.grid(row=0, column=1, sticky="ew", padx=(14, 0))
        self._label(main, "Main camera", 11, bold=True).pack(side="left")
        self._label(main, "INTERACTIVE", 8, C["accent"], True).pack(
            side="right", padx=6
        )
        self._label(wrist, "Wrist camera", 11, bold=True).pack(side="left")
        self._label(wrist, "END EFFECTOR", 8, C["muted"], True).pack(
            side="right", padx=6
        )
        self.canvas_holder = tk.Frame(cameras, bg=C["bg"])
        self.canvas_holder.grid(row=1, column=0, sticky="nsew", padx=8)
        self.canvas.pack(in_=self.canvas_holder, fill="both", expand=True)
        self.canvas.tk.call("raise", self.canvas._w)
        self.camera_hint = self._label(
            cameras,
            "Click to select  ·  Drag to move  ·  Scroll to adjust height",
            9,
            C["muted"],
        )
        self.camera_hint.grid(row=2, column=0, sticky="w", padx=16, pady=12)
        activity = self._panel(self.center)
        activity.grid(row=2, column=0, sticky="ew")
        line = tk.Frame(activity, bg="white")
        line.pack(fill="x", padx=16, pady=(12, 7))
        self._label(line, "Session activity", 11, bold=True).pack(side="left")
        self.activity = tk.Text(
            activity,
            height=5,
            bg="white",
            fg=C["muted"],
            relief="flat",
            wrap="word",
            font=(self.family, 10),
            padx=16,
            pady=3,
            state="disabled",
            takefocus=False,
            borderwidth=0,
        )
        self.activity.pack(fill="x", pady=(0, 8))
        self.activity.tag_configure("time", foreground="#99a7b1")
        self.activity.tag_configure("error", foreground=C["danger"])

    def _build_inspector(self):
        self.right.grid_rowconfigure(0, weight=1)
        self.right.grid_columnconfigure(0, weight=1)
        self.inspector_canvas = tk.Canvas(
            self.right, bg="white", highlightthickness=0, width=240
        )
        self.inspector_canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(self.right, command=self.inspector_canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.inspector_canvas.configure(yscrollcommand=scrollbar.set)
        frame = tk.Frame(self.inspector_canvas, bg="white", padx=15)
        window = self.inspector_canvas.create_window(0, 0, window=frame, anchor="nw")
        frame.bind(
            "<Configure>",
            lambda event: self.inspector_canvas.configure(
                scrollregion=self.inspector_canvas.bbox("all")
            ),
        )
        self.inspector_canvas.bind(
            "<Configure>",
            lambda event: self.inspector_canvas.itemconfigure(
                window, width=event.width
            ),
        )
        self._section(frame, "OBJECT INSPECTOR")
        self.selection_name = self._label(
            frame, "Nothing selected", 12, bold=True, wraplength=235
        )
        self.selection_name.pack(fill="x", pady=(0, 5))
        self.selection_kind = self._label(
            frame,
            "Select an object to inspect its position.",
            9,
            C["muted"],
            wraplength=232,
            justify="left",
        )
        self.selection_kind.pack(fill="x", pady=(0, 12))
        self.position_vars = {}
        self.position_entries = []
        for axis, color in [("X", "#ae675e"), ("Y", "#50856a"), ("Z", "#547ca4")]:
            row = tk.Frame(frame, bg="white")
            row.pack(fill="x", pady=3)
            self._label(row, axis, 10, color, True, width=2).pack(side="left")
            var = tk.StringVar(value="—")
            entry = ttk.Entry(row, textvariable=var, width=12)
            entry.pack(side="left", fill="x", expand=True, padx=8)
            self._label(row, "m", 9, C["muted"]).pack(side="right")
            self._input_focus(entry)
            entry.bind(
                "<Return>", lambda e: self.invoke("Position", self.apply_position)
            )
            self.position_vars[axis] = var
            self.position_entries.append(entry)
        self._action(
            frame, "Apply position", self.apply_position, "apply", compact=True
        ).pack(fill="x", pady=(10, 6))
        self._action(
            frame, "Toggle joint state", self.toggle_joint, "joint", compact=True
        ).pack(fill="x", pady=(0, 10))
        self._label(
            frame,
            "NumPad: move / rotate the selected object",
            9,
            C["muted"],
            wraplength=233,
        ).pack(fill="x")
        tk.Frame(frame, height=1, bg=C["line"]).pack(fill="x", pady=(17, 0))
        self._section(frame, "SAFETY MONITOR")
        self.monitor_status = self._label(frame, "Monitoring", 10, C["accent"], True)
        self.monitor_status.pack(anchor="w")
        self.events_count = self._label(frame, "0", 27, bold=True)
        self.events_count.pack(anchor="w", pady=(7, 0))
        self._label(frame, "recorded events", 9, C["muted"]).pack(anchor="w")
        self.last_event = self._label(
            frame,
            "No safety events recorded.",
            9,
            C["muted"],
            wraplength=232,
            justify="left",
        )
        self.last_event.pack(fill="x", pady=(8, 0))
        self.rule_summary = self._label(frame, "No rules evaluated yet", 9, C["muted"], wraplength=232, justify="left")
        self.rule_summary.pack(fill="x", pady=(8, 6))
        self._action(frame, "Rules & detections…", self.show_safety_rules, "safety_rules", compact=True).pack(fill="x")
        tk.Frame(frame, height=1, bg=C["line"]).pack(fill="x", pady=(17, 0))
        self._section(frame, "POLICY & EXECUTION")
        self.model_name = self._label(
            frame, "No model selected", 10, wraplength=232, justify="left"
        )
        self.model_name.pack(fill="x", pady=(0, 8))
        self._action(
            frame, "Choose model…", self.editor.switch_vla_model, "model", compact=True
        ).pack(fill="x")
        self.execution = self._label(
            frame,
            "Choose AI policy, then Start run.",
            9,
            C["muted"],
            wraplength=232,
            justify="left",
        )
        self.execution.pack(fill="x", pady=(10, 0))
        self._action(
            frame, "Start run", self.editor.start_ai_run, "start", primary=True, compact=True
        ).pack(fill="x", pady=(8, 0))
        actions = tk.Frame(frame, bg="white")
        actions.pack(fill="x", pady=(8, 12))
        self._action(
            actions, "Pause / resume", lambda: self.send_key("p"), "pause", compact=True
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._action(
            actions, "Replay", lambda: self.send_key("r"), "replay", compact=True
        ).pack(side="left", fill="x", expand=True)

        def bind_scroll(widget):
            widget.bind(
                "<Button-4>",
                lambda event: self.inspector_canvas.yview_scroll(-2, "units"),
            )
            widget.bind(
                "<Button-5>",
                lambda event: self.inspector_canvas.yview_scroll(2, "units"),
            )
            widget.bind(
                "<MouseWheel>",
                lambda event: self.inspector_canvas.yview_scroll(
                    -1 if event.delta > 0 else 1, "units"
                ),
            )
            for child in widget.winfo_children():
                bind_scroll(child)

        bind_scroll(frame)

    def _setup_figure(self):
        editor = self.editor
        editor.info_ax.set_visible(False)
        editor.fig.set_facecolor(C["bg"])
        editor.ax.set_position([0.014, 0.02, 0.479, 0.96])
        editor.ax_wrist.set_position([0.507, 0.02, 0.479, 0.96])
        for axis in (editor.ax, editor.ax_wrist):
            axis.set_title("")
            axis.set_xlabel("")
            axis.set_facecolor(C["bg"])
        self.canvas.configure(bg=C["bg"], highlightthickness=0)
        editor.fig.canvas.draw_idle()

    def _input_focus(self, widget):
        widget.bind(
            "<FocusIn>", lambda event: setattr(self.editor, "_textbox_editing", True)
        )
        widget.bind(
            "<FocusOut>", lambda event: setattr(self.editor, "_textbox_editing", False)
        )
        widget.bind("<Escape>", lambda event: self.focus_canvas())

    def focus_canvas(self):
        self.editor._textbox_editing = False
        self.canvas.focus_set()

    def commit_instruction(self):
        self.editor._on_instruction_submit(self.instruction.get())
        self.log("Task instruction updated for this session.")
        self.focus_canvas()

    def invoke(self, label, callback):
        self.focus_canvas()
        try:
            result = callback()
            if isinstance(result, (str, Path)):
                self.log(f"{label}: {result}")
            self.refresh()
            return result
        except Exception as error:
            self.log(f"{label}: {error}", error=True)
            messagebox.showerror(label, str(error), parent=self.root)

    def mode(self):
        e = self.editor
        if e.data_collection_mode:
            return "human"
        if e.ai_mode:
            return "ai"
        return "free" if e.free_mode else "physics"

    def select_mode(self, target):
        e = self.editor
        current = self.mode()
        if getattr(e, "_object_change_pending", False):
            return
        if current == target:
            return
        if current == "human":
            e.exit_data_collection_mode(save=True)
        elif current == "ai":
            e.exit_ai_mode()
        e.free_mode = False
        e.keyboard_control_active = True
        if target == "free":
            e.free_mode = True
        elif target == "human":
            e.enter_data_collection_mode()
        elif target == "ai":
            e.enter_ai_mode()
            if not e.ai_mode and current == "free":
                e.free_mode = True
        elif current == "free":
            e.apply_physics_settling()
        e._init_hotkey_panel()
        if self.mode() != target:
            self.log(
                f"Could not enter {self.mode_buttons[target].cget('text')}. See the terminal for controller details.",
                error=True,
            )

    def send_key(self, key):
        self.editor.on_key_press(SimpleNamespace(key=key, guiEvent=None))

    def _refresh_objects(self, force=False):
        query = self.search.get().casefold().strip()
        objects = self.editor.object_info
        signature = tuple(
            (
                (name, info.get("type"), info.get("is_fixture"))
                for (name, info) in sorted(objects.items())
            )
        )
        rebuilt = force or signature != self._tree_signature
        if rebuilt:
            self._tree_signature = signature
            self._syncing = True
            self.tree.delete(*self.tree.get_children())
            for fixture, group, title in [
                (False, "@objects", "OBJECTS"),
                (True, "@fixtures", "FIXTURES"),
            ]:
                matches = [
                    (name, info)
                    for (name, info) in sorted(objects.items())
                    if bool(info.get("is_fixture")) == fixture
                    and query in (name + " " + info.get("type", "")).casefold()
                ]
                if matches:
                    self.tree.insert(
                        "",
                        "end",
                        iid=group,
                        text=f"{title}   {len(matches)}",
                        open=True,
                        tags=("group",),
                    )
                for name, info in matches:
                    self.tree.insert(
                        group, "end", iid=name, text=name.replace("_", " ")
                    )
            self._syncing = False
            self.object_count.configure(text=str(len(objects)))
        selected = self.editor.selected_object
        if rebuilt or selected != self._tree_selection:
            self._tree_selection = selected
            self._syncing = True
            if selected and self.tree.exists(selected):
                self.tree.selection_set(selected)
                self.tree.see(selected)
            elif self.tree.selection():
                self.tree.selection_remove(*self.tree.selection())
            self._syncing = False

    def _select_object(self, event=None):
        if self._syncing:
            return
        names = self.tree.selection()
        if not names or names[0] not in self.editor.object_info:
            return
        name = names[0]
        old = self.editor.selected_object
        if old != name:
            if old:
                self.editor._remove_highlight(old)
            self.editor.selected_object = name
            self.editor.selected_body_id = None
            self.editor.keyboard_control_active = True
            self.editor._apply_highlight(name)
            self.log(f"Selected {name.replace('_', ' ')}.")
        self.refresh()

    def _position(self, info):
        return self.editor.env.sim.data.body_xpos[info["body_id"]].copy()

    def apply_position(self):
        name = self.editor.selected_object
        info = self.editor.object_info.get(name, {})
        if not info.get("has_free_joint") or self.mode() not in ("physics", "free"):
            return
        values = [float(self.position_vars[axis].get()) for axis in "XYZ"]
        if not all((math.isfinite(value) for value in values)):
            raise ValueError("Position coordinates must be finite numbers.")
        current = self._position(info)
        if self.editor.move_object_6dof(
            name,
            **dict(zip(("dx", "dy", "dz"), [v - c for (v, c) in zip(values, current)])),
        ):
            self.log(f"Position updated: {name.replace('_', ' ')}.")

    def toggle_joint(self):
        if self.editor.selected_object:
            self.editor.quick_toggle_state(
                self.editor.selected_object, self.editor.selected_body_id
            )

    def remove_object(self):
        name = self.editor.selected_object
        if self.mode() != "free" or not name or getattr(self.editor, "_object_change_pending", False):
            return
        if messagebox.askyesno(
            "Remove object", f"Remove {name} from this scene?", parent=self.root
        ):
            self.editor.delete_object(name)

    def refresh(self):
        if not self.root.winfo_exists():
            return
        e = self.editor
        mode = self.mode()
        busy = getattr(e, "_object_change_pending", False)
        editing = mode in ("physics", "free") and not busy
        self._refresh_objects()
        for key, control in self.mode_buttons.items():
            control.configure(
                bg=C["accent"] if key == mode else C["bg"],
                fg="white" if key == mode else C["muted"],
                activebackground=C["accent_soft"],
                state="disabled" if busy else "normal",
            )
        if mode != self._last_mode:
            self._last_mode = mode
            self.log(f"Mode: {self.mode_buttons[mode].cget('text')}.")
        info = e.object_info.get(e.selected_object, {})
        if info:
            self.selection_name.configure(text=e.selected_object.replace("_", " "))
            kind = "Fixed fixture" if info.get("is_fixture") else "Movable object"
            if e.selected_body_id is not None:
                part = e.env.sim.model.body_id2name(e.selected_body_id)
                self.selection_kind.configure(text=f"Part: {part}")
            else:
                self.selection_kind.configure(text=f"{kind} · {info.get('type', '')}")
            if str(self.root.tk.call("focus")) not in {str(entry) for entry in self.position_entries}:
                for axis, value in zip("XYZ", self._position(info)):
                    self.position_vars[axis].set(f"{value:.4f}")
        else:
            self.selection_name.configure(text="Nothing selected")
            self.selection_kind.configure(
                text="Select an object to inspect its position."
            )
            for variable in self.position_vars.values():
                variable.set("—")
        can_move = editing and bool(info.get("has_free_joint"))
        for entry in self.position_entries:
            entry.configure(state="normal" if can_move else "disabled")
        states = {
            "open": editing,
            "save": editing,
            "task": editing,
            "reset": editing,
            "resample": editing,
            "model": editing,
            "add": mode == "free" and not busy,
            "remove": mode == "free" and not busy and bool(info) and (not info.get("is_fixture")),
            "apply": can_move,
            "joint": editing and bool(info.get("joints")),
            "start": mode == "ai" and not busy
            and bool(getattr(e.ai_controller, "is_active", False))
            and not getattr(e.ai_controller, "is_executing", False)
            and not getattr(e.ai_controller, "execution_done", False),
            "pause": mode == "ai" and (bool(getattr(e.ai_controller, "is_executing", False))
            or bool(getattr(e.ai_controller, "is_playing", False))),
            "replay": mode == "ai"
            and bool(getattr(e.ai_controller, "execution_done", False)),
        }
        for key, enabled in states.items():
            self.controls[key].configure(state="normal" if enabled else "disabled")
        monitor = getattr(e, "physics_safety_monitor", None)
        if mode == "ai":
            monitor = getattr(e.ai_controller, "safety_monitor", monitor)
        events = monitor.get_all_events() if monitor else []
        count = len(events)
        health = monitor.get_status() if monitor else {}
        self.monitor_status.configure(
            text="Configuration error" if monitor and monitor.config_error
            else "Detection needs attention" if health.get("unknown")
            else "No rules configured" if monitor and not health.get("rules")
            else "Paused in Free edit" if mode == "free"
            else "Ready - waiting for Start run"
            if mode == "ai" and not e.ai_controller.is_executing and not e.ai_controller.execution_done
            else "Monitoring"
            if monitor
            else "Unavailable",
            fg=C["danger"] if health.get("error") else C["muted"] if mode == "free" or not monitor else C["accent"],
        )
        self.rule_summary.configure(text=(
            f"{health.get('rules', 0)} rules · {health.get('active', 0)} active · {health.get('unknown', 0)} unknown"
            + (f"\n{health['no_matches']} rules have no matching entities" if health.get("no_matches") else "")
            + ("\n" + health["error"][:160] if health.get("error") else "")
        ))
        self.events_count.configure(
            text=str(count), fg=C["warning"] if count else C["text"]
        )
        recent = events[-1] if events else {}
        description = str(
            recent.get("rule_name")
            or recent.get("predicate")
            or recent.get("event_type")
            or "Safety event"
        )
        self.last_event.configure(
            text=description.replace("_", " ")
            if events
            else "No safety events recorded.",
            fg=C["warning"] if events else C["muted"],
        )
        signature = (id(monitor), count)
        if signature != self._events_signature and count:
            self.log(f"Safety event: {description.replace('_', ' ')}.", error=True)
        self._events_signature = signature
        controller = e.ai_controller
        profile = controller.profile if controller else None
        self.model_name.configure(text=profile.name if profile else "No policy profile selected")
        if mode == "ai" and controller:
            state = controller.get_status_text()
        elif mode == "human":
            state = "Human control · use the numeric keypad."
        else:
            manager = getattr(e, "policy_service", None)
            if manager:
                for message, error in manager.poll():
                    self.log(message, error=error)
            state = manager.status if manager and profile and manager.profile_key == profile.key else "Choose a model service, then enter AI policy."
        self.execution.configure(text=state)
        self.task_badge.configure(
            text="NO TASK GOAL" if not e.editor.parsed_dict.get("goal_state") else
                 "TASK COMPLETE" if e.task_success else "BDDL TASK",
            fg=C["accent"] if e.task_success else C["muted"],
        )
        self.status.configure(text=f"{Path(e.bddl_file).name}")
        self.runtime.configure(
            text=f"{len(e.object_info)} objects   ·   {self.mode_buttons[mode].cget('text')}   ·   Cost {e.episode_cost:g}"
        )

    def log(self, text, error=False):
        self._messages.append((datetime.now().strftime("%H:%M:%S"), text, error))
        self._messages = self._messages[-50:]
        if not hasattr(self, "activity"):
            return
        self.activity.configure(state="normal")
        self.activity.delete("1.0", "end")
        for timestamp, message, is_error in self._messages[-5:]:
            self.activity.insert("end", timestamp + "   ", "time")
            self.activity.insert("end", message + "\n", "error" if is_error else "")
        self.activity.see("end")
        self.activity.configure(state="disabled")

    def _tick(self):
        try:
            self.refresh()
        except Exception:
            logger.exception("Cannot refresh Scene Studio")
        finally:
            try:
                if self.root.winfo_exists():
                    self._after = self.root.after(250, self._tick)
            except tk.TclError:
                pass

    def show_help(self):
        existing = getattr(self, "_help_window", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            return
        dialog = tk.Toplevel(self.root)
        self._help_window = dialog
        dialog.title("red-libero · Keyboard guide")
        x = max(0, self.root.winfo_rootx() + (self.root.winfo_width() - 650) // 2)
        y = max(0, self.root.winfo_rooty() + (self.root.winfo_height() - 580) // 2)
        dialog.geometry(f"650x580+{x}+{y}")
        dialog.configure(bg="white")
        dialog.transient(self.root)
        frame = tk.Frame(dialog, bg="white", padx=24, pady=20)
        frame.pack(fill="both", expand=True)
        self._label(frame, "Work faster with the keyboard", 16, bold=True).pack(
            anchor="w", pady=(0, 8)
        )
        self._label(
            frame, "Click a camera view before using scene shortcuts.", 10, C["muted"]
        ).pack(anchor="w", pady=(0, 18))
        rows = [
            ("SELECT & EDIT", ""),
            ("Click / drag / wheel", "Select / move / adjust height"),
            ("Alt + left-click", "Select a part, then use Toggle joint state"),
            ("Alt + right-click", "Open or close the clicked part directly"),
            ("2 / 8 · 4 / 6 · 5 / 0", "Translate X / Y / Z"),
            ("7 / 9 · 1 / 3 · * / /", "Rotate yaw / pitch / roll"),
            ("SCENE & EXECUTION", ""),
            ("Shift + S / I", "Save / open scene"),
            ("Shift + R / E", "Reset / resample scene"),
            ("Shift + A", "Add object in Free edit"),
            ("Ctrl + Enter", "Start AI from Physics"),
            ("Space", "Cycle manual modes / leave AI mode"),
            ("P / R in AI", "Pause / replay trajectory"),
            ("F1", "Open this guide"),
        ]
        for key, action in rows:
            row = tk.Frame(frame, bg="white")
            row.pack(fill="x", pady=4 if action else 9)
            self._label(
                row,
                key,
                10 if action else 9,
                C["text"] if action else C["accent"],
                not action,
                width=29,
            ).pack(side="left")
            self._label(row, action, 10, C["muted"]).pack(side="left")
        dialog.bind("<Escape>", lambda event: dialog.destroy())
        decorate_dialog(dialog)

    def close(self):
        if getattr(self, "_after", None):
            try:
                self.root.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None
