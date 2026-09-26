"""Red LIBERO resources and simulation API."""

from importlib import import_module

from .paths import get_default_paths, get_path, set_default_paths

__version__ = "0.1.0"
__all__ = ["OffScreenRenderEnv", "SegmentationRenderEnv", "benchmark", "get_path", "get_default_paths", "set_default_paths"]


def __getattr__(name):
    if name == "benchmark":
        return import_module("libero.libero.benchmark")
    if name in ("OffScreenRenderEnv", "SegmentationRenderEnv"):
        return getattr(import_module("libero.libero.envs"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
