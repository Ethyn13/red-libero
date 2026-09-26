#!/usr/bin/env bash
# Use an activated project environment, or set RED_LIBERO_PYTHON.
set -euo pipefail
studio_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
studio_python="${RED_LIBERO_PYTHON:-python}"
export MUJOCO_GL="${MUJOCO_GL:-osmesa}"
export PYOPENGL_PLATFORM="${PYOPENGL_PLATFORM:-$MUJOCO_GL}"
if [[ -z "${DISPLAY:-}" && " $* " != *" --help "* ]]; then
    echo "Scene Studio requires a display. Open a desktop terminal or connect using ssh -X/-Y." >&2
    exit 2
fi
if ! command -v "$studio_python" >/dev/null 2>&1; then
    echo "Python not found: $studio_python. Activate your environment or set RED_LIBERO_PYTHON." >&2
    exit 2
fi
# Optional project-local Xft Tk. The launcher does not install dependencies.
studio_tk="${RED_LIBERO_TK_PREFIX:-$studio_dir/.gui-runtime/tk}"
studio_tk_lib="$studio_tk/usr/lib/x86_64-linux-gnu"
if [[ "${RED_LIBERO_USE_LOCAL_TK:-1}" == 1 && -f "$studio_tk_lib/libtk8.6.so" && -f "$studio_tk_lib/libtcl8.6.so" ]]; then
    export LD_PRELOAD="$studio_tk_lib/libtcl8.6.so:$studio_tk_lib/libtk8.6.so${LD_PRELOAD:+:$LD_PRELOAD}"
    export TCL_LIBRARY="$studio_tk/usr/share/tcltk/tcl8.6"
    export TK_LIBRARY="$studio_tk/usr/share/tcltk/tk8.6"
fi
# Keep the GUI and compatibility clients on the same resource configuration.
export RED_LIBERO_CONFIG_PATH="${RED_LIBERO_CONFIG_PATH:-${LIBERO_CONFIG_PATH:-$studio_dir/.gui-runtime/red-libero-config}}"
export LIBERO_CONFIG_PATH="$RED_LIBERO_CONFIG_PATH"
"$studio_python" - "$studio_dir" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from red_libero.paths import ensure_config
ensure_config()
PY
studio_args=("$@")
if [[ $# -eq 0 || "$1" == -* ]]; then
    studio_args=("$studio_dir/libero/libero/bddl_files/libero_spatial/pick_up_the_black_bowl_between_the_plate_and_the_ramekin_and_place_it_on_the_plate.bddl" "${studio_args[@]}")
fi
echo "red-libero · Scene Studio | renderer: $MUJOCO_GL | Python: $studio_python"
exec "$studio_python" "$studio_dir/editor_gui.py" "${studio_args[@]}"
