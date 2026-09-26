#!/usr/bin/env bash
set -euo pipefail
studio_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export MUJOCO_GL=egl
export PYOPENGL_PLATFORM=egl
# Preserve the old BDDL MODEL invocation while accepting all editor flags.
if [[ $# -ge 2 && "$1" != -* && "$2" != -* ]]; then
    studio_scene="$1"
    studio_model="$2"
    shift 2
    exec bash "$studio_dir/gui_start.sh" "$studio_scene" --vla-model "$studio_model" "$@"
fi
exec bash "$studio_dir/gui_start.sh" "$@"
