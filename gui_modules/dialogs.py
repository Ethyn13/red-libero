"""Scene, task, and model selection dialogs."""

import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional, Tuple

from gui_modules.studio_theme import decorate_dialog

logger = logging.getLogger(__name__)
AVAILABLE_OBJECTS_LIST = [
    "--- Food Items (Hope Objects) ---",
    "alphabet_soup",
    "bbq_sauce",
    "butter",
    "cherries",
    "chocolate_pudding",
    "cookies",
    "corn",
    "cream_cheese",
    "ketchup",
    "macaroni_and_cheese",
    "mayo",
    "milk",
    "orange_juice",
    "popcorn",
    "salad_dressing",
    "tomato_sauce",
    "--- Tableware (Google Scanned) ---",
    "white_bowl",
    "akita_black_bowl",
    "plate",
    "basket",
    "chefmate_8_frypan",
    "glazed_rim_porcelain_ramekin",
    "--- Furniture (Turbosquid) ---",
    "wooden_tray",
    "black_book",
    "yellow_book",
    "red_coffee_mug",
    "porcelain_mug",
    "moka_pot",
    "wine_bottle",
    "--- Unsafe Objects: Basic Shapes ---",
    "ball",
    "water_ball",
    "block",
    "block_small",
    "block_large",
    "--- Unsafe Objects: Tableware & Tools ---",
    "fork",
    "candle",
    "bottled_water",
    "--- Unsafe Objects: Sharp/Dangerous ---",
    "kitchen_knife",
    "knife_n",
    "hammer",
    "hammer_handle",
    "scissors",
    "scissors_n",
]


def show_add_object_dialog() -> Optional[str]:
    dialog = tk.Toplevel()
    dialog.title("Add Object - Select Item")
    dialog.geometry("500x400")
    dialog.resizable(False, False)
    dialog.update_idletasks()
    x = dialog.winfo_screenwidth() // 2 - 500 // 2
    y = dialog.winfo_screenheight() // 2 - 400 // 2
    dialog.geometry(f"500x400+{x}+{y}")
    title_label = tk.Label(
        dialog,
        text="Select Object Type to Add",
        font=("Arial", 14, "bold"),
        fg="darkblue",
    )
    title_label.pack(pady=10)
    category_label = tk.Label(
        dialog,
        text="Available Object Types (including unsafe objects):",
        font=("Arial", 10),
    )
    category_label.pack(pady=5)
    combo_frame = tk.Frame(dialog)
    combo_frame.pack(pady=10, padx=20, fill=tk.X)
    selected_var = tk.StringVar()
    combo = ttk.Combobox(
        combo_frame,
        textvariable=selected_var,
        values=AVAILABLE_OBJECTS_LIST,
        state="readonly",
        font=("Arial", 10),
        width=45,
    )
    combo.pack(fill=tk.X)
    combo.set("-- Select an object type --")
    info_label = tk.Label(
        dialog,
        text="Object appears above the workspace surface and is selected.\nDrag it or edit its position in the inspector.",
        font=("Arial", 9),
        fg="gray",
    )
    info_label.pack(pady=10)
    result = {"selected": None}
    button_frame = tk.Frame(dialog)
    button_frame.pack(pady=20)

    def on_ok():
        selected = selected_var.get()
        if selected in AVAILABLE_OBJECTS_LIST and (not selected.startswith("---")):
            result["selected"] = selected
            dialog.destroy()
        else:
            messagebox.showwarning("Warning", "Please select an object type!")

    def on_cancel():
        dialog.destroy()

    ok_button = tk.Button(
        button_frame,
        text="Add Object",
        command=on_ok,
        width=15,
        bg="lightgreen",
        font=("Arial", 10, "bold"),
    )
    ok_button.pack(side=tk.LEFT, padx=10)
    cancel_button = tk.Button(
        button_frame, text="Cancel", command=on_cancel, width=15, font=("Arial", 10)
    )
    cancel_button.pack(side=tk.LEFT, padx=10)
    hint_label = tk.Label(
        dialog,
        text="Tip: Double-click item to select and add",
        font=("Arial", 8),
        fg="blue",
    )
    hint_label.pack(pady=5)

    def on_double_click(event):
        selected = selected_var.get()
        if selected in AVAILABLE_OBJECTS_LIST and (not selected.startswith("---")):
            result["selected"] = selected
            dialog.destroy()

    combo.bind("<Double-Button-1>", on_double_click)
    decorate_dialog(dialog)
    dialog.wait_window()
    return result["selected"]


def show_select_vla_model_dialog(current_model=None, *, parent=None, service_manager=None):
    """Choose a reusable model service profile."""
    from gui_modules.policy.dialog import show_policy_dialog
    return show_policy_dialog(parent, current_model, service_manager)


def show_select_bddl_task_dialog(
    bddl_folders: List[str] = None,
) -> Optional[Tuple[str, str]]:
    if bddl_folders is None:
        from red_libero import get_path
        BDDL_BASE = Path(get_path("bddl_files"))
        bddl_folders = [
            ("libero_spatial", "Spatial relations"),
            ("libero_goal", "Goal diversity"),
            ("libero_object", "Object diversity"),
            ("libero_10", "Long-horizon tasks"),
        ]
    else:
        BDDL_BASE = Path(bddl_folders[0]).parent
    logger.debug(f"Show select bddl task dialog: BDDL_BASE={BDDL_BASE}")
    logger.debug(
        f"Show select bddl task dialog: BDDL_BASE.exists()={BDDL_BASE.exists()}"
    )
    if BDDL_BASE.exists():
        logger.debug(
            f"Show select bddl task dialog: [f.name for f in BDDL_BASE.iterdir() if f.is_dir()][:5]={[f.name for f in BDDL_BASE.iterdir() if f.is_dir()][:5]}"
        )
    dialog = tk.Toplevel()
    dialog.title("Switch BDDL Task")
    dialog.geometry("1000x650")
    dialog.resizable(True, True)
    dialog.update_idletasks()
    x = dialog.winfo_screenwidth() // 2 - 1000 // 2
    y = dialog.winfo_screenheight() // 2 - 650 // 2
    dialog.geometry(f"1000x650+{x}+{y}")
    title_label = tk.Label(
        dialog, text="Switch BDDL Task", font=("Arial", 14, "bold"), fg="darkgreen"
    )
    title_label.pack(pady=10)
    path_info_label = tk.Label(
        dialog, text=f"BDDL Base: {BDDL_BASE}", font=("Arial", 8), fg="gray"
    )
    path_info_label.pack(pady=2)
    main_frame = tk.Frame(dialog)
    main_frame.pack(pady=10, padx=20, fill=tk.BOTH, expand=True)
    left_frame = tk.Frame(main_frame, width=210)
    left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 16))
    left_frame.pack_propagate(False)
    suite_label = tk.Label(left_frame, text="Task Suite:", font=("Arial", 11, "bold"))
    suite_label.pack(pady=5)
    suite_listbox = tk.Listbox(
        left_frame, font=("Arial", 10), selectmode=tk.SINGLE, height=8
    )
    suite_listbox.pack(fill=tk.BOTH, expand=True)
    suite_data = []
    for folder_name, description in bddl_folders:
        folder_path = BDDL_BASE / folder_name
        exists = folder_path.exists()
        status = "✓" if exists else "✗"
        if exists:
            bddl_files = list(folder_path.glob("*.bddl"))
            count = len(bddl_files)
            display_text = f"{status} {folder_name} ({count} tasks)"
        else:
            display_text = f"{status} {folder_name} (Not Found)"
            count = 0
        suite_listbox.insert(tk.END, display_text)
        suite_data.append((folder_name, folder_path, exists, count))
    right_frame = tk.Frame(main_frame)
    right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
    task_label = tk.Label(
        right_frame, text="Available Tasks:", font=("Arial", 11, "bold")
    )
    task_label.pack(pady=5)
    search_frame = tk.Frame(right_frame)
    search_frame.pack(fill=tk.X, pady=5)
    search_label = tk.Label(search_frame, text="Search:", font=("Arial", 9))
    search_label.pack(side=tk.LEFT, padx=5)
    search_var = tk.StringVar()
    search_entry = tk.Entry(search_frame, textvariable=search_var, font=("Arial", 9))
    search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
    task_list_frame = tk.Frame(right_frame)
    task_list_frame.pack(fill=tk.BOTH, expand=True)
    task_listbox = tk.Listbox(task_list_frame, font=("Arial", 9), selectmode=tk.SINGLE)
    task_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    task_scrollbar = tk.Scrollbar(task_list_frame, command=task_listbox.yview)
    task_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    task_listbox.config(yscrollcommand=task_scrollbar.set)
    task_xscroll = ttk.Scrollbar(
        right_frame, orient="horizontal", command=task_listbox.xview
    )
    task_xscroll.pack(fill=tk.X)
    task_listbox.configure(xscrollcommand=task_xscroll.set)
    task_detail = tk.Label(
        right_frame,
        text="Select a task to inspect its full name.",
        font=("Arial", 9),
        anchor="w",
        justify="left",
        wraplength=680,
    )
    task_detail.pack(fill=tk.X, pady=(8, 0))

    def show_task_detail(event):
        selection = task_listbox.curselection()
        if selection:
            task_detail.configure(text=task_listbox.get(selection[0]).strip(" •"))

    task_listbox.bind("<<ListboxSelect>>", show_task_detail)
    task_paths = []
    current_suite_tasks = []

    def load_tasks(suite_idx):
        task_listbox.delete(0, tk.END)
        task_paths.clear()
        current_suite_tasks.clear()
        if suite_idx < 0 or suite_idx >= len(suite_data):
            return
        (folder_name, folder_path, exists, count) = suite_data[suite_idx]
        if not exists or count == 0:
            task_listbox.insert(tk.END, "  No tasks found")
            return
        bddl_files = sorted(folder_path.glob("*.bddl"))
        for bddl_file in bddl_files:
            if bddl_file.name == "tasks_info.txt":
                continue
            task_name = bddl_file.stem.replace("_", " ")
            current_suite_tasks.append((task_name, str(bddl_file)))
        filter_tasks(search_var.get())

    def filter_tasks(search_text):
        task_listbox.delete(0, tk.END)
        task_paths.clear()
        search_lower = search_text.lower()
        for task_name, task_path in current_suite_tasks:
            if search_lower in task_name.lower():
                display_text = f"  • {task_name}"
                task_listbox.insert(tk.END, display_text)
                task_paths.append(task_path)

    def on_suite_select(event):
        selection = suite_listbox.curselection()
        if selection:
            load_tasks(selection[0])

    def on_search_change(*args):
        filter_tasks(search_var.get())

    suite_listbox.bind("<<ListboxSelect>>", on_suite_select)
    search_var.trace("w", on_search_change)
    for idx, (_, _, exists, _) in enumerate(suite_data):
        if exists:
            suite_listbox.selection_set(idx)
            suite_listbox.activate(idx)
            load_tasks(idx)
            break
    result = {"selected": None}
    bottom_frame = tk.Frame(dialog)
    bottom_frame.pack(pady=15)

    def on_ok():
        task_selection = task_listbox.curselection()
        if not task_selection:
            messagebox.showwarning(
                "Warning",
                "Select a task first.\n\n1. Choose a suite on the left.\n2. Choose a task on the right.",
            )
            return
        task_idx = task_selection[0]
        if task_idx >= len(task_paths):
            messagebox.showwarning("Warning", "Invalid task selection.")
            return
        task_path = task_paths[task_idx]
        task_parent = Path(task_path).parent.name
        suite_name = task_parent
        suite_names = [s[0] for s in suite_data]
        if suite_name not in suite_names:
            suite_selection = suite_listbox.curselection()
            if suite_selection:
                suite_name = suite_data[suite_selection[0]][0]
            else:
                messagebox.showwarning("Warning", "Cannot determine the task suite.")
                return
        result["selected"] = (suite_name, task_path)
        dialog.destroy()

    def on_cancel():
        dialog.destroy()

    ok_button = tk.Button(
        bottom_frame,
        text="Switch Task",
        command=on_ok,
        width=15,
        bg="lightgreen",
        font=("Arial", 10, "bold"),
    )
    ok_button.pack(side=tk.LEFT, padx=10)
    cancel_button = tk.Button(
        bottom_frame, text="Cancel", command=on_cancel, width=15, font=("Arial", 10)
    )
    cancel_button.pack(side=tk.LEFT, padx=10)
    hint_label = tk.Label(
        dialog,
        text="Select a task on the right. Double-click a task to load it.",
        font=("Arial", 9),
        fg="blue",
    )
    hint_label.pack(pady=5)
    status_label = tk.Label(dialog, text="", font=("Arial", 8), fg="darkgreen")
    status_label.pack(pady=2)

    def update_status(event=None):
        task_sel = task_listbox.curselection()
        if task_sel and task_sel[0] < len(task_paths):
            task_path = Path(task_paths[task_sel[0]])
            suite_name = task_path.parent.name
            task_name = task_path.stem.replace("_", " ")
            if len(task_name) > 60:
                task_name = task_name[:60] + "..."
            status_label.config(text=f"Selected: [{suite_name}] {task_name}")
        else:
            status_label.config(text="")

    task_listbox.bind("<<ListboxSelect>>", update_status)

    def on_double_click(event):
        on_ok()

    task_listbox.bind("<Double-Button-1>", on_double_click)
    if len(suite_data) > 0:
        suite_listbox.selection_set(0)
        load_tasks(0)
    decorate_dialog(dialog)
    dialog.wait_window()
    return result["selected"]
