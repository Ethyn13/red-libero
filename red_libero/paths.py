"""Resource paths for a Red-LIBERO checkout."""

import hashlib
import os
from pathlib import Path
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
RESOURCE_ROOT = ROOT / "libero" / "libero"
_CHECKOUT_ID = hashlib.sha256(str(ROOT).encode()).hexdigest()[:12]
_CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
CONFIG_DIR = Path(
    os.environ.get("RED_LIBERO_CONFIG_PATH")
    or os.environ.get("LIBERO_CONFIG_PATH")
    or _CONFIG_HOME / "red-libero" / _CHECKOUT_ID
).expanduser().resolve()
CONFIG_FILE = CONFIG_DIR / "config.yaml"


def get_default_paths(resource_root=None):
    resources = Path(resource_root).expanduser().resolve() if resource_root else RESOURCE_ROOT
    return {
        "benchmark_root": str(resources),
        "bddl_files": str(resources / "bddl_files"),
        "init_states": str(resources / "init_files"),
        "assets": str(resources / "assets"),
        "datasets": str(ROOT / "datasets"),
    }


def _write_config(paths):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=CONFIG_DIR, encoding="utf-8", delete=False) as handle:
        yaml.safe_dump(paths, handle, sort_keys=False)
        temporary = Path(handle.name)
    try:
        temporary.replace(CONFIG_FILE)
    finally:
        temporary.unlink(missing_ok=True)


def ensure_config():
    if not CONFIG_FILE.exists():
        _write_config(get_default_paths())
    paths = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
    required = set(get_default_paths())
    if not isinstance(paths, dict) or not required.issubset(paths):
        raise ValueError(f"Incomplete Red-LIBERO resource configuration: {CONFIG_FILE}")
    return paths


def get_path(key):
    paths = ensure_config()
    if key not in paths:
        raise KeyError(f"Unknown Red-LIBERO path {key!r}; available: {', '.join(paths)}")
    return paths[key]


def set_default_paths(resource_root=None):
    _write_config(get_default_paths(resource_root))


ensure_config()
