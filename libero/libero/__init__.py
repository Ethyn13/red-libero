"""Compatibility imports for existing VLA clients and BDDL assets."""

from red_libero.paths import (
    CONFIG_DIR,
    CONFIG_FILE,
    get_default_paths,
    get_path,
    set_default_paths,
)

libero_config_path = str(CONFIG_DIR)
config_file = str(CONFIG_FILE)
get_libero_path = get_path


def get_default_path_dict(custom_location=None):
    return get_default_paths(custom_location)


def set_libero_default_path(custom_location=None):
    set_default_paths(custom_location)
