# Installation

Install **red-libero** in a dedicated Conda environment. Model inference runs in separate environments; no model weights are needed for scene editing.

<h2 id="contents">Table of Contents</h2>

1. [System requirements](#system-requirements)
2. [Create the GUI environment](#create-the-gui-environment)
3. [Add the policy client](#add-the-policy-client)
4. [Verify and launch](#verify-and-launch)
5. [Resource paths](#resource-paths)

---

<a id="system-requirements"></a>

## 1. System requirements

The documented setup targets Linux x86_64. Tk needs an X11 desktop, X11 forwarding, or a remote desktop. OSMesa renders simulation images on the CPU; EGL uses a configured GPU. Both still need a display for the GUI window.

On Ubuntu / Debian:

```bash
sudo apt-get update
sudo apt-get install -y \
  libosmesa6 libgl1 libegl1 libglib2.0-0 \
  libxrender1 libxext6 libxft2 fontconfig fonts-dejavu-core
```

Obtain the source checkout from the [project repository](https://github.com/Ethyn13/red-libero), or use a release supplied by the project. Run the following commands in the directory containing `editor_gui.py` and `environment.yml`. Keep the bundled `libero/libero/assets/` directory with the checkout.

```bash
git clone https://github.com/Ethyn13/red-libero.git
cd red-libero
```

<a id="create-the-gui-environment"></a>

## 2. Create the GUI environment

```bash
conda env create -f environment.yml
conda activate red-libero

python -m pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements/studio.txt
python -m pip install --no-deps -e .
python -m pip check
```

| Component | GUI version |
| --- | --- |
| Python | 3.10 |
| NumPy | **1.26.4** |
| robosuite | **1.5.1** |
| MuJoCo | 3.3.7 |
| PyTorch for state I/O | 2.5.1, CPU build |

The complete pins are in [requirements/studio.txt](downloads/requirements/studio.txt); the interpreter and Tk specification is [environment.yml](downloads/environment.yml). The installed distribution is `red-libero`, with public imports under `red_libero`. The `libero.libero` namespace is retained for existing VLA clients and standard BDDL identifiers.

<a id="add-the-policy-client"></a>

## 3. Add the policy client

For **AI policy**, obtain the companion RedVLA source from the [project website](https://redvla.github.io), then install its base client:

```bash
conda activate red-libero
python -m pip install -c requirements/studio.txt -e /path/to/redvla
python -m pip check
```

OpenVLA / VLA-Adapter dependencies and OpenPI's JAX dependencies belong in the selected model's environment. See [model recipes](models.md) for the serving commands.

<a id="verify-and-launch"></a>

## 4. Verify and launch

```bash
python -c "import numpy, robosuite; print(numpy.__version__, robosuite.__version__)"
bash gui_start.sh
```

The versions should be `1.26.4` and `1.5.1`. The launcher opens a supplied bowl-on-plate task. Continue with [your first scene](quickstart.md).

<a id="resource-paths"></a>

## 5. Resource paths

| Setting / directory | Purpose |
| --- | --- |
| `RED_LIBERO_PYTHON` | Explicit Python interpreter for the GUI launcher. |
| `RED_LIBERO_CONFIG_PATH` | Override the simulator resource configuration directory. |
| `.gui-runtime/red-libero-config/` | Checkout-specific configuration created by the launcher. |
| `.red-libero/workspace/` | Current and reset-baseline scene files, relative to the launch directory. |
| `.red-libero/safety_rules.bddl` | Applied safety rules beside the workspace. |

Direct Python imports use `~/.config/red-libero/<checkout-id>/config.yaml`, with `XDG_CONFIG_HOME` support. `LIBERO_CONFIG_PATH` remains a compatibility fallback. Resource paths are initialized without an interactive prompt.
