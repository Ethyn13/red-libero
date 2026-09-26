"""Shared colors, typography, and ttk styles for Scene Studio."""

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

COLORS = {
    "bg": "#edf1f5",
    "surface": "#ffffff",
    "header": "#172936",
    "text": "#243745",
    "muted": "#71818e",
    "line": "#dce4ea",
    "accent": "#137f78",
    "accent_hover": "#0c6862",
    "accent_soft": "#e5f3f0",
    "danger": "#b24d43",
    "warning": "#aa731e",
    "warning_soft": "#fff3de",
}


def apply_theme(root):
    families = set(tkfont.families(root))
    family = next(
        (f for f in ("Inter", "Lato", "Segoe UI", "DejaVu Sans") if f in families),
        "sans",
    )
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        tkfont.nametofont(name).configure(family=family, size=10)
    root.option_add("*Font", (family, 10))
    root.option_add("*tearOff", False)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TFrame", background=COLORS["surface"])
    style.configure("TLabel", background=COLORS["surface"], foreground=COLORS["text"])
    style.configure(
        "TEntry",
        fieldbackground="white",
        foreground=COLORS["text"],
        bordercolor=COLORS["line"],
        lightcolor=COLORS["line"],
        darkcolor=COLORS["line"],
        padding=7,
    )
    style.map("TEntry", bordercolor=[("focus", COLORS["accent"])])
    style.configure(
        "TCombobox", padding=6, fieldbackground="white", arrowcolor=COLORS["muted"]
    )
    style.configure(
        "Treeview",
        background="white",
        fieldbackground="white",
        foreground=COLORS["text"],
        rowheight=34,
        borderwidth=0,
        font=(family, 10),
    )
    style.map(
        "Treeview",
        background=[("selected", COLORS["accent_soft"])],
        foreground=[("selected", COLORS["accent"])],
    )
    style.configure(
        "Treeview.Heading",
        background=COLORS["bg"],
        foreground=COLORS["muted"],
        relief="flat",
        font=(family, 9, "bold"),
    )
    style.configure(
        "Vertical.TScrollbar",
        background=COLORS["line"],
        troughcolor="white",
        borderwidth=0,
        arrowsize=10,
    )
    return family


def button(parent, text, command, primary=False, compact=False):
    bg = COLORS["accent"] if primary else COLORS["surface"]
    hover = COLORS["accent_hover"] if primary else COLORS["bg"]
    item = tk.Button(
        parent,
        text=text,
        command=command,
        background=bg,
        foreground="white" if primary else COLORS["text"],
        activebackground=hover,
        activeforeground="white" if primary else COLORS["text"],
        disabledforeground="#a7b3bc",
        relief="flat",
        borderwidth=0,
        highlightthickness=1,
        highlightbackground=bg if primary else COLORS["line"],
        highlightcolor=COLORS["accent"],
        padx=10 if compact else 15,
        pady=6 if compact else 9,
        cursor="hand2",
        takefocus=True,
    )
    item.bind(
        "<Enter>",
        lambda e: item.configure(bg=hover) if item["state"] != "disabled" else None,
    )
    item.bind("<Leave>", lambda e: item.configure(bg=bg))
    return item


def decorate_dialog(dialog):

    def apply():
        if not dialog.winfo_exists():
            return
        dialog.configure(bg=COLORS["surface"])
        parent = dialog.master
        if parent is not None:
            dialog.transient(parent.winfo_toplevel())

        def walk(widget):
            kind = widget.winfo_class()
            try:
                if kind in (
                    "Frame",
                    "Label",
                    "LabelFrame",
                    "Checkbutton",
                    "Radiobutton",
                ):
                    widget.configure(bg=COLORS["surface"])
                if kind in ("Label", "LabelFrame", "Checkbutton", "Radiobutton"):
                    previous = str(widget.cget("fg")).lower()
                    widget.configure(
                        fg=COLORS["danger"]
                        if previous in ("red", "darkred")
                        else COLORS["text"]
                    )
                if kind in ("Entry", "Listbox", "Text"):
                    widget.configure(
                        bg="white",
                        fg=COLORS["text"],
                        relief="flat",
                        highlightthickness=1,
                        highlightbackground=COLORS["line"],
                        highlightcolor=COLORS["accent"],
                    )
                if kind == "Button":
                    widget.configure(
                        bg=COLORS["bg"],
                        fg=COLORS["text"],
                        relief="flat",
                        borderwidth=0,
                        activebackground=COLORS["accent_soft"],
                        activeforeground=COLORS["accent"],
                        padx=12,
                        pady=7,
                    )
            except tk.TclError:
                pass
            for child in widget.winfo_children():
                walk(child)

        walk(dialog)

    dialog.after_idle(apply)
