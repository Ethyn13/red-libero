"""Compatibility aliases for the shared Red-LIBERO resource configuration."""

from red_libero.paths import CONFIG_DIR, CONFIG_FILE, get_default_paths, get_path, set_default_paths

libero_config_path = str(CONFIG_DIR)
config_file = str(CONFIG_FILE)
get_libero_path = get_path
get_path_dict = get_default_paths
set_libero_path = set_default_paths
