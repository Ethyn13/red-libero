"""Portable service profiles sharing RedVLA's model configuration schema."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import re
from urllib.parse import urlparse

import yaml


ROOT = Path(__file__).resolve().parents[2]
PROFILE_DIR = ROOT / "configs" / "policies"
LOCAL_DIR = PROFILE_DIR / "local"


def positive(value, name, *, zero=False):
    number = float(value)
    if not math.isfinite(number) or number < 0 or (not zero and number == 0):
        raise ValueError(f"{name} must be {'non-negative' if zero else 'positive'} and finite")
    return number


def expand(value):
    value = os.path.expandvars(os.path.expanduser(str(value)))
    if re.search(r"\$\{[^}]+\}", value):
        raise ValueError(f"Set the environment variable referenced by {value}")
    return value


@dataclass
class PolicyProfile:
    name: str
    model: dict
    run: dict = field(default_factory=dict)
    launch: dict = field(default_factory=dict)
    source: str = ""

    def __post_init__(self):
        self.name = str(self.name).strip()
        if not self.name:
            raise ValueError("A profile name is required")
        self.model = dict(self.model)
        kind = self.model.get("type", "remote")
        kind = "openpi" if kind in ("pi0", "pi05") else kind
        if kind not in ("remote", "openpi"):
            raise ValueError("Use remote or openpi. Run model weights in their own service environment.")
        endpoint = str(self.model.get("path", "")).strip()
        parsed = urlparse(endpoint)
        schemes = ("http", "https") if kind == "remote" else ("ws", "wss")
        if parsed.scheme not in schemes or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError(f"Use a {'/'.join(schemes)} endpoint without embedded credentials")
        try:
            parsed.port
        except ValueError as error:
            raise ValueError("Invalid endpoint port") from error
        options = dict(self.model.get("options") or {})
        for key in ("timeout", "connect_timeout", "inference_timeout"):
            if key in options:
                options[key] = positive(options[key], key)
        if "replan_steps" in options and (int(options["replan_steps"]) != options["replan_steps"] or int(options["replan_steps"]) < 1):
            raise ValueError("replan_steps must be a positive integer")
        self.model = {"type": kind, "path": endpoint, "options": options}
        self.run = {"max_steps": 520, "settle_steps": 10, "seed": 0, **self.run}
        for key in ("max_steps", "settle_steps", "seed"):
            value = self.run[key]
            if isinstance(value, bool) or int(value) != float(value):
                raise ValueError(f"{key} must be an integer")
            self.run[key] = int(value)
        if not 1 <= self.run["max_steps"] <= 100000:
            raise ValueError("max_steps must be between 1 and 100000")
        if not 0 <= self.run["settle_steps"] < self.run["max_steps"]:
            raise ValueError("settle_steps must be non-negative and smaller than max_steps")
        if not 0 <= self.run["seed"] < 2**32:
            raise ValueError("seed must be between 0 and 2**32 - 1")
        self.launch = {"python": "", "cwd": "", "command": [], "env": {}, "startup_timeout": 180, **self.launch}
        command = self.launch["command"]
        if not isinstance(command, list) or not all(isinstance(arg, str) and arg for arg in command):
            raise ValueError("launch.command must be a list of nonempty arguments, not a shell command")
        if not isinstance(self.launch["env"], dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in self.launch["env"].items()):
            raise ValueError("launch.env must map environment variable names to strings")
        self.launch["startup_timeout"] = positive(self.launch["startup_timeout"], "startup_timeout")
        json.dumps(self.to_dict(), allow_nan=False)

    @property
    def key(self):
        return json.dumps(self.to_dict(), sort_keys=True)

    def to_dict(self):
        return {"version": 1, "name": self.name, "model": self.model, "run": self.run, "launch": self.launch}


def load_profiles(path):
    path = Path(path).expanduser().resolve()
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("Expected a YAML mapping")
    if "models" in document:
        defaults = document.get("defaults", {})
        run = {key: defaults[key] for key in ("max_steps", "settle_steps") if key in defaults}
        return [PolicyProfile(str(name), model, run, source=str(path)) for name, model in document["models"].items()]
    if document.get("version", 1) != 1:
        raise ValueError("Unsupported policy profile version")
    launch = dict(document.get("launch") or {})
    for key in ("python", "cwd"):
        value = launch.get(key)
        if value and not value.startswith(("~", "$")) and not Path(value).is_absolute():
            launch[key] = str((path.parent / value).resolve())
    return [PolicyProfile(document.get("name", path.stem), document.get("model", {}),
                          document.get("run") or {}, launch, str(path))]


def save_profile(profile, directory=LOCAL_DIR):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", profile.name).strip("-") or "policy"
    destination = directory / f"{stem}.yaml"
    temporary = destination.with_suffix(".yaml.tmp")
    temporary.write_text(yaml.safe_dump(profile.to_dict(), sort_keys=False), encoding="utf-8")
    temporary.replace(destination)
    profile.source = str(destination)
    return destination


def available_profiles():
    profiles, errors = [], []
    for folder in (PROFILE_DIR, LOCAL_DIR):
        for path in sorted([*folder.glob("*.yaml"), *folder.glob("*.yml")]):
            try:
                profiles.extend(load_profiles(path))
            except Exception as error:
                errors.append(f"{path.name}: {error}")
    order = {"VLA-Adapter": 0, "OpenVLA": 1, "pi0 (OpenPI)": 2, "Custom startup script": 3}
    profiles.sort(key=lambda p: (0 if Path(p.source).parent == LOCAL_DIR else 1, order.get(p.name, -1), p.name))
    return profiles, errors


def remember_profile(profile):
    path = save_profile(profile)
    state = ROOT / ".gui-runtime" / "policy-selection.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"profile": str(path)}), encoding="utf-8")
    return str(path)


def last_profile():
    try:
        path = json.loads((ROOT / ".gui-runtime" / "policy-selection.json").read_text())["profile"]
        load_profiles(path)
        return path
    except (OSError, ValueError, KeyError, TypeError):
        return None
