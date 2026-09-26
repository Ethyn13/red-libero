#!/usr/bin/env bash
# Optional Debian/Ubuntu x86_64 fix for Conda Tk builds without Xft.
# Extract packages into the project, without sudo or Conda changes.
set -euo pipefail
studio_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$(uname -m)" != x86_64 ]] || ! command -v apt-get >/dev/null; then
    echo "This helper supports Debian/Ubuntu x86_64. Use an Xft-enabled Tk on other systems." >&2
    exit 2
fi
studio_prefix="${RED_LIBERO_TK_PREFIX:-$studio_dir/.gui-runtime/tk}"
mkdir -p "$studio_prefix"
studio_prefix="$(cd -- "$studio_prefix" && pwd)"
studio_download="$(mktemp -d -t red-libero-tk.XXXXXXXX)"
trap 'rm -rf -- "$studio_download"' EXIT
cd "$studio_download"
apt-get download libtk8.6 libtcl8.6
for package in ./*.deb; do
    dpkg-deb -x "$package" "$studio_prefix"
done
echo "Installed project-local Tk at $studio_prefix. Launch with gui_start.sh."
echo "Set RED_LIBERO_USE_LOCAL_TK=0 to use your environment's original Tk."
