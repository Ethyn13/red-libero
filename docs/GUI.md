# Scene Studio guide

Scene Studio is the default Tk/ttk interface for `editor_gui.py`. It displays two simulator cameras and provides scene editing, safety monitoring, and interactive policy execution.


<h2 id="contents">Table of Contents</h2>

1. [Launch](#launch)
2. [Workspace](#workspace)
3. [Modes](#modes)
4. [Mouse and keyboard](#mouse-and-keyboard)
5. [Save and restore scenes](#save-and-restore-scenes)
6. [Model services](#model-services)
7. [Fonts](#fonts)
8. [Validation](#validation)

---

<a id="launch"></a>

## 1. Launch

Complete the [installation steps](installation.md), then launch from the repository root in a desktop session:

```bash
conda activate red-libero
bash gui_start.sh
```

Choose a task, model profile, or renderer:

```bash
bash gui_start.sh /path/to/task.bddl
bash gui_start.sh /path/to/task.bddl --policy-profile configs/policies/local/my-policy.yaml
bash gui_start_egl.sh /path/to/task.bddl
bash gui_start.sh --classic-ui
```

`RED_LIBERO_PYTHON=/path/to/conda/envs/red-libero/bin/python` selects an explicit interpreter. The launcher does not install packages or activate a fixed environment. It defaults to OSMesa and prepares checkout-specific asset paths under `.gui-runtime/red-libero-config/`. Set `RED_LIBERO_CONFIG_PATH` to choose a different configuration directory; `LIBERO_CONFIG_PATH` remains a fallback for existing clients. Working BDDL/state files live in `.red-libero/workspace/`.

OSMesa and EGL render simulation images; the Tk window still needs a desktop display. Use an existing local desktop, X11 forwarding, or a remote desktop. Paths and local model endpoints refer to the machine running the GUI.

<a id="workspace"></a>

## 2. Workspace

<figure class="doc-figure" markdown="1">

[![Scene Studio at a glance](images/studio-overview.png){ loading=lazy width="1440" height="960" }](images/studio-overview.png)

<figcaption markdown="span">**Scene Studio at a glance.** Select an object on the left, inspect both camera views, and edit its position or prepare a policy on the right.</figcaption>
</figure>

| Area | Controls |
| --- | --- |
| Toolbar | Open scene, Save scene, Change task, Reset, Resample, and mode selection. |
| Scene objects | Filter by name/type and select an object or fixture. |
| Task instruction | Edit the instruction passed to a policy in this session. This does not rewrite BDDL language or goals. |
| Main camera | Select and move objects; inspect articulated parts. |
| Wrist camera | Observe the gripper and nearby objects during a run. |
| Object inspector | Edit XYZ coordinates in metres and toggle supported joints. |
| Safety monitor | Inspect events from the current safety configuration; monitoring pauses in Free edit. |
| Policy & execution | Choose a service, start a run, pause/resume, and replay a completed trajectory. |
| Session activity | Inspect operation feedback and export paths. Detailed logs remain in the launching terminal. |

A 1440 x 900 or larger window is convenient. The layout also supports 1280 x 800 with a scrollable right panel.

<a id="modes"></a>

## 3. Modes

| Mode | Behavior |
| --- | --- |
| Physics | Run the physics simulation and inspect objects. |
| Free edit | Edit object poses and scene structure. Add / Remove are available in this mode. |
| Human | Use the existing manual end-effector controls. Scene structure editing is disabled. |
| AI policy | Prepare the selected policy without simulation advancement, inference, or recording. Click Start run to begin. |

Returning from Free edit to Physics allows the scene to settle. To test the current edited placement directly, select AI policy from Free edit and use the profile's settling-step setting.

During AI execution, model requests run in a worker thread while simulation and display updates remain on the GUI thread. Pause freezes execution. Replay becomes available after recording an episode. Leave and re-enter AI policy to prepare a new run; leaving restores the scene captured when Start run was clicked.

<a id="mouse-and-keyboard"></a>

## 4. Mouse and keyboard

Focus the camera area before using scene shortcuts. Typing in the instruction, filter, or coordinate fields does not trigger scene shortcuts. F1 opens the full keyboard guide.

| Input | Action |
| --- | --- |
| Left-click / drag / wheel | Select a parent object / move it in XY / adjust height. |
| Alt + left-click | Select a specific articulated part. |
| Right-click / Alt + right-click | Toggle the selected parent joint / the clicked part's joint. |
| NumPad 2/8, 6/4, 5/0 | Translate along X, Y, Z. |
| NumPad 7/9, 1/3, multiply/divide | Rotate yaw, pitch, roll. |
| Shift+S / Shift+I | Save / open a scene outside AI mode. |
| Shift+R / Shift+E | Reset / resample outside AI mode. |
| Shift+A / Shift+Delete | Add / remove an object in Free edit. |
| Shift+T / Shift+M | Change task / choose model outside AI mode. |
| Ctrl+Enter | Enter AI policy from Physics. |
| Enter, in AI mode | Start the prepared run. |
| P / R, in AI mode | Pause or resume / replay. |
| S, after an AI episode | Export videos, safety events, and HDF5 trajectory. |
| Space | Cycle manual modes or leave AI mode. |

<figure class="doc-figure" markdown="1">

[![Inspect an articulated part](images/articulated-object.png){ loading=lazy width="1440" height="960" }](images/articulated-object.png)

<figcaption markdown="span">**Inspect an articulated part.** The middle cabinet drawer is selected and open. Alt + click selects the part; Toggle joint state changes that joint.</figcaption>
</figure>

<a id="save-and-restore-scenes"></a>

## 5. Save and restore scenes

The toolbar's Save scene exports BDDL, simulator state, and metadata together in `Scene/<task>_<timestamp>/` under the current working directory. This toolbar export currently uses `Scene/` even when `--save-dir` configures another editor save directory.

```text
scene.bddl
scene.pruned_init
scene.meta.yaml
```

Use Open scene to load a saved bundle. Keep the BDDL and state paired: a state from a different object layout may be incompatible. Reset restores the workspace's initial state. Resample creates a new sample from the BDDL constraints.

Scene export is separate from policy-episode export. After an AI run, press S while the camera is focused and before leaving AI mode. Recordings go to the repository's `datasets/video/`, `datasets/rlds/`, and `datasets/rlds_annotation/` directories. The HDF5 files are this project's trajectory format, not a TFDS RLDS dataset.

<a id="model-services"></a>

## 6. Model services

See [Connecting VLA policies](POLICY_SERVICES.md) for the full profile schema, separate model environments, service lifecycle, and protocol contract. `--policy-profile` takes a YAML file. The compatibility alias `--vla-model` also takes YAML, not a weights directory.

Entering AI policy only prepares the run. Starting a service or checking a connection does not execute the robot; a connection check may send a diagnostic inference request. Click Start run explicitly when ready.

<a id="fonts"></a>

## 7. Fonts

Some Conda Tk builds display bitmap fonts without antialiasing. On Debian/Ubuntu x86_64, the optional helper can provide a project-local Tk build with Xft support:

```bash
bash scripts/setup_gui_fonts.sh
```

It downloads `libtk8.6` and `libtcl8.6` from the machine's configured APT sources and extracts them under `.gui-runtime/tk/`, without sudo. The GUI launcher uses these libraries only for its process. System Xft/fontconfig libraries and suitable fonts must already be available. Set `RED_LIBERO_USE_LOCAL_TK=0` to disable this override.

<a id="validation"></a>

## 8. Validation

For maintainers who have the ignored local validation scripts, run the real Tk/MuJoCo checks in a dedicated desktop or Xvfb display with the GUI environment and RedVLA client installed. These scripts are not required to install or use the GUI:

```bash
python scripts/check_studio_ui.py --output-dir .ui-validation
python scripts/check_studio_ui.py --output-dir .ui-validation --classic
```

These checks edit temporary scenes, exercise controls, and save screenshots and JSON results. They do not load model weights or estimate model success rates. Font-related environment overrides, if used, must be supplied to the check process as well as the launcher.

The layout is implemented in `gui_modules/studio_ui.py`; styles are in `gui_modules/studio_theme.py`. Architecture notes are available in [GUI_ARCHITECTURE.md](GUI_ARCHITECTURE.md).
