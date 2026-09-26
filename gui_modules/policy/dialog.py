"""Policy profiles, environment binding, and managed service controls."""

import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from gui_modules.policy.profiles import PolicyProfile, available_profiles, load_profiles, remember_profile, save_profile
from gui_modules.policy.service import ServiceManager
from gui_modules.studio_theme import COLORS as C, button


class PolicyDialog:
    def __init__(self, parent, current=None, manager=None):
        self.result = None
        self.manager = manager or ServiceManager()
        self.owns_manager = manager is None
        self.window = tk.Toplevel(parent)
        self.window.title("Choose model - Policy services")
        self.window.geometry("980x720")
        self.window.minsize(900, 680)
        self.window.configure(bg=C["surface"])
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda event: self.close())
        self.variables, self.editors = {}, {}
        self.source = ""
        self._tracking_operation = False
        self.profiles, errors = available_profiles()
        if current:
            try:
                selected = current if isinstance(current, PolicyProfile) else load_profiles(current)[0]
                self.profiles.insert(0, selected)
            except Exception as error:
                errors.append(str(error))
        if not self.profiles:
            self.profiles.append(PolicyProfile("Custom policy", {"type": "remote", "path": "http://127.0.0.1:8001"}))
        header = tk.Frame(self.window, bg=C["header"], padx=22, pady=17)
        header.pack(fill="x")
        tk.Label(header, text="Connect a policy", bg=C["header"], fg="white", font=("sans", 19, "bold")).pack(anchor="w")
        tk.Label(header, text="Run the model in its own environment. Keep scene editing and inference connected.", bg=C["header"], fg="#bed0da").pack(anchor="w", pady=(5, 0))
        body = tk.Frame(self.window, bg=C["surface"], padx=18, pady=14)
        body.pack(fill="both", expand=True)
        sidebar = tk.Frame(body, bg=C["surface"], width=210)
        sidebar.pack(side="left", fill="y", padx=(0, 18))
        tk.Label(sidebar, text="SAVED PROFILES", bg=C["surface"], fg=C["muted"], anchor="w").pack(fill="x", pady=(0, 8))
        self.listbox = tk.Listbox(sidebar, width=24, relief="flat", highlightthickness=1, highlightbackground=C["line"], selectbackground=C["accent_soft"], selectforeground=C["accent"], exportselection=False)
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self.select)
        button(sidebar, "Import YAML...", self.import_profiles).pack(fill="x", pady=(10, 5))
        button(sidebar, "Save profile", self.save).pack(fill="x")
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)
        style = ttk.Style(self.window)
        style.configure("Policy.TNotebook", background=C["surface"], borderwidth=0)
        style.configure("Policy.TNotebook.Tab", padding=(16, 7), background=C["bg"], foreground=C["muted"])
        style.map("Policy.TNotebook.Tab", background=[("selected", C["accent_soft"])], foreground=[("selected", C["accent"])])
        self.notebook = ttk.Notebook(right, style="Policy.TNotebook")
        self.notebook.pack(fill="both", expand=True)
        self.tabs = {}
        for title in ("Connection", "Launch", "Run", "Logs"):
            frame = ttk.Frame(self.notebook, padding=14)
            self.notebook.add(frame, text=title)
            self.tabs[title] = frame
        connection = self.tabs["Connection"]
        self.entry(connection, "name", "Profile name")
        ttk.Label(connection, text="Service protocol").pack(anchor="w", pady=(8, 3))
        self.variables["type"] = tk.StringVar(value="remote")
        protocol = ttk.Combobox(connection, textvariable=self.variables["type"], values=("remote", "openpi"), state="readonly")
        protocol.pack(fill="x")
        ttk.Label(connection, text="remote = RedVLA HTTP / openpi = OpenPI WebSocket").pack(anchor="w", pady=(4, 5))
        self.entry(connection, "path", "Endpoint URL")
        self.textbox(connection, "options", "Client options (JSON)", 4)
        ttk.Label(connection, text="OpenVLA / VLA-Adapter use RedVLA HTTP. pi0 / pi0.5 use OpenPI.\nCheckpoint and normalization settings belong to the model service.", wraplength=600).pack(anchor="w", pady=10)
        launch = self.tabs["Launch"]
        self.entry(launch, "python", "Model environment Python", browse="file")
        self.entry(launch, "cwd", "Service working directory", browse="directory")
        self.textbox(launch, "command", "Launch arguments (one per line; {python} uses the environment above)", 5)
        button(launch, "Choose startup script...", self.choose_script, compact=True).pack(anchor="w", pady=4)
        self.textbox(launch, "env", "Environment overrides (JSON, e.g. CUDA_VISIBLE_DEVICES)", 2)
        self.entry(launch, "startup_timeout", "Startup timeout (seconds)")
        ttk.Label(launch, text="Managed launch runs on the GUI host. For another machine, start its\nservice there and enter its reachable endpoint under Connection.").pack(anchor="w", pady=5)
        run = self.tabs["Run"]
        for key, title in (("max_steps", "Maximum simulation steps"), ("settle_steps", "Initial settling steps"), ("seed", "Inference seed")):
            self.entry(run, key, title)
        ttk.Label(run, text="The active BDDL goal and scene instruction define the task.\nSettling steps count toward the total budget. Seed support depends\non the model backend. The current scene is not reset on entry.\n\nPause holds the simulator; leaving AI restores its entry state.\nInference errors stop execution and remain visible in the activity log.", wraplength=600).pack(anchor="w", pady=18)
        self.logs = tk.Text(self.tabs["Logs"], wrap="word", relief="flat", bg="#f4f7fa", fg=C["text"], state="disabled", font=("monospace", 9))
        self.logs.pack(fill="both", expand=True)
        self.status = tk.StringVar(value="; ".join(errors) if errors else "Choose a profile, then check its connection or start its service.")
        tk.Label(self.window, textvariable=self.status, bg=C["bg"], fg=C["text"], anchor="w", wraplength=930, padx=20, pady=10).pack(fill="x")
        footer = tk.Frame(self.window, bg=C["surface"], padx=18, pady=12)
        footer.pack(fill="x")
        self.check_button = button(footer, "Check connection", lambda: self.operation("check"))
        self.check_button.pack(side="left")
        self.start_button = button(footer, "Start service", lambda: self.operation("start"))
        self.start_button.pack(side="left", padx=6)
        self.stop_button = button(footer, "Stop owned service", lambda: self.operation("stop"))
        self.stop_button.pack(side="left")
        button(footer, "Use profile", self.use, primary=True).pack(side="right")
        button(footer, "Cancel", self.close).pack(side="right", padx=6)
        self.refresh_list()
        self.fill(self.profiles[0])
        if parent is not None:
            self.window.transient(parent)
        self._after = self.window.after(200, self.poll)

    def entry(self, parent, key, label, browse=None):
        ttk.Label(parent, text=label).pack(anchor="w", pady=(7, 3))
        row = ttk.Frame(parent)
        row.pack(fill="x")
        self.variables[key] = tk.StringVar()
        ttk.Entry(row, textvariable=self.variables[key]).pack(side="left", fill="x", expand=True)
        if browse:
            button(row, "Browse", lambda: self.browse(key, browse), compact=True).pack(side="right", padx=(5, 0))

    def textbox(self, parent, key, label, height):
        ttk.Label(parent, text=label).pack(anchor="w", pady=(8, 3))
        self.editors[key] = tk.Text(parent, height=height, wrap="none", relief="solid", borderwidth=1, font=("monospace", 9), undo=True)
        self.editors[key].pack(fill="x")

    def refresh_list(self):
        self.listbox.delete(0, "end")
        for profile in self.profiles:
            self.listbox.insert("end", profile.name)
        self.listbox.selection_set(0)

    def fill(self, profile):
        self._tracking_operation = False
        self.source = profile.source
        values = {"name": profile.name, **profile.model, **profile.run, **profile.launch}
        for key, variable in self.variables.items():
            variable.set(values[key])
        for key, widget in self.editors.items():
            widget.delete("1.0", "end")
            widget.insert("1.0", "\n".join(values[key]) if key == "command" else json.dumps(values[key], indent=2))

    def read(self):
        values = {key: value.get() for key, value in self.variables.items()}
        options = json.loads(self.editors["options"].get("1.0", "end"))
        env = json.loads(self.editors["env"].get("1.0", "end"))
        return PolicyProfile(values["name"], {"type": values["type"], "path": values["path"], "options": options},
            {key: values[key] for key in ("max_steps", "settle_steps", "seed")},
            {"python": values["python"], "cwd": values["cwd"], "startup_timeout": values["startup_timeout"],
             "command": self.editors["command"].get("1.0", "end").strip().splitlines(), "env": env}, self.source)

    def select(self, event=None):
        selected = self.listbox.curselection()
        if selected:
            self.fill(self.profiles[selected[0]])

    def guarded(self, action):
        try:
            return action()
        except Exception as error:
            self._tracking_operation = False
            self.status.set(str(error))
            messagebox.showerror("Policy configuration", str(error), parent=self.window)

    def browse(self, key, kind):
        chooser = filedialog.askdirectory if kind == "directory" else filedialog.askopenfilename
        path = chooser(parent=self.window)
        if path:
            self.variables[key].set(path)

    def choose_script(self):
        path = filedialog.askopenfilename(parent=self.window, title="Choose the model startup script")
        if path:
            command = ["{python}" if path.endswith(".py") else "bash" if path.endswith(".sh") else path]
            if command[0] != path:
                command.append(path)
            self.editors["command"].delete("1.0", "end")
            self.editors["command"].insert("1.0", "\n".join(command))
            if not self.variables["cwd"].get():
                self.variables["cwd"].set(str(Path(path).parent))

    def import_profiles(self):
        path = filedialog.askopenfilename(parent=self.window, filetypes=(("YAML", "*.yaml *.yml"), ("All files", "*")))
        if path:
            def load():
                imported = load_profiles(path)
                if not imported:
                    raise ValueError("No remote model entries found")
                self.profiles = imported + self.profiles
                self.refresh_list()
                self.fill(imported[0])
                self.status.set(f"Imported {len(imported)} profile(s)")
            self.guarded(load)

    def save(self):
        def persist():
            profile = self.read()
            path = save_profile(profile)
            self.profiles.insert(0, profile)
            self.refresh_list()
            self.status.set(f"Saved {path}")
        self.guarded(persist)

    def operation(self, name):
        def run():
            profile = self.read() if name != "stop" else self.profiles[0]
            getattr(self.manager, name)(profile)
            self._tracking_operation = True
            self.status.set(self.manager.status)
            if name == "start":
                self.notebook.select(self.tabs["Logs"])
        self.guarded(run)

    def poll(self):
        if not self.window.winfo_exists():
            return
        self.manager.poll()
        if self._tracking_operation:
            self.status.set(self.manager.status)
        for control in (self.check_button, self.start_button):
            control.configure(state="disabled" if self.manager.busy else "normal")
        owned = self.manager.process is not None and self.manager.process.poll() is None
        self.stop_button.configure(state="normal" if owned or self.manager.busy else "disabled")
        if self.notebook.select() == str(self.tabs["Logs"]):
            text = self.manager.log_tail()
            if self.manager.metadata:
                text += "\n\nService metadata:\n" + json.dumps(self.manager.metadata, indent=2)
            if self.logs.get("1.0", "end-1c") != text:
                self.logs.configure(state="normal")
                self.logs.delete("1.0", "end")
                self.logs.insert("1.0", text)
                self.logs.see("end")
                self.logs.configure(state="disabled")
        self._after = self.window.after(250, self.poll)

    def use(self):
        def choose():
            self.result = remember_profile(self.read())
            self.close()
        self.guarded(choose)

    def close(self):
        if getattr(self, "_after", None):
            self.window.after_cancel(self._after)
        self.window.destroy()
        if self.owns_manager:
            self.manager.shutdown()


def show_policy_dialog(parent=None, current=None, manager=None):
    dialog = PolicyDialog(parent, current, manager)
    dialog.window.grab_set()
    try:
        dialog.window.wait_window()
    finally:
        try:
            dialog.window.after_cancel(dialog._after)
        except tk.TclError:
            pass
        if dialog.owns_manager:
            dialog.manager.shutdown()
    return dialog.result
