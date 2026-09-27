# Scene Studio internals

Scene Studio controllers live in `gui_modules`. Public controller imports:

```python
from gui_modules.ai_mode import AIController
from gui_modules.safety_monitor import SafetyMonitor
```

<h2 id="contents">Table of Contents</h2>

1. [Responsibilities](#responsibilities)
2. [GUI thread and environment replacement](#gui-thread-and-environment-replacement)
3. [Safety state](#safety-state)
4. [Predicates](#predicates)
5. [Policy services](#policy-services)
6. [Validation](#validation)

---

<a id="responsibilities"></a>

## 1. Responsibilities

| Component | Responsibility |
| --- | --- |
| `studio_ui.py`, `studio_theme.py`, `dialogs.py` | Layout, styling, and selection dialogs |
| `event_handlers.py`, `frame_updater.py` | Input dispatch and GUI refresh |
| `object_management.py`, `joint_control.py`, `coordinate_utils.py` | Object creation/removal, joint inspection, and coordinate conversion |
| `editor_gui.py`, `init_state_io.py` | Selection, movement, calibration, scene serialization, and verified state loading |
| `ai_mode.py` | Model lifecycle and execution coordination |
| `policy/profiles.py`, `policy/client.py`, `policy/service.py`, `policy/dialog.py` | YAML profiles, RedVLA transports, owned service lifecycle, and connection UI |
| `safety_monitor.py` | Episode state, event storage, object matching, and reset |
| `safety/expressions.py`, `safety/catalog.py` | Validated expressions, scene bindings, predicate contracts, and cumulative state |
| `safety/dialog.py` | Rule application, source synchronization, reference, and live diagnostics |
| `safety/tree_model.py`, `safety/tree_editor.py` | Rule tree structure, scoped insertion, node editing, and validation |

<a id="gui-thread-and-environment-replacement"></a>

## 2. GUI thread and environment replacement

Scene selection, movement, calibration, BDDL import, and snapshot restoration use the implementations in `MatplotlibGUIEditor`. `FrameUpdater` dispatches queued import/restore requests to those editor methods on the GUI thread. Environment replacement binds the old OpenGL context before releasing its resources, then activates the new context on the GUI thread. Safety monitors are rebound after import or restoration. The former duplicate helper modules have been removed.

Policy transport runs in a worker that never accesses the simulator or Tk. The editor update loop captures observations, applies actions, checks safety, and draws the current scene. Leaving AI cancels further actions and restores the entry snapshot by name. Late network replies cannot mutate the environment. No backup environment or synthetic policy is used.

<a id="safety-state"></a>

## 3. Safety state

Call `SafetyMonitor.reset()` at episode boundaries. It clears events, transition history, and cumulative counters without an implicit settling window. Every logical operator, including the root, preserves its meaning. Independent rules are siblings inside `:safety_rules`. `and` requires simultaneous truth; it does not combine unrelated historical states. `cumu` counts true samples across gaps, with cached evaluation preventing duplicate increments within a sample. See [Safety rules](SAFETY_RULES.md) for syntax and migration details.

Physics mode checks once after an actual simulation update. Human Assist and AI policy check after each action. Rendering, rule validation, model connection checks, and opening a dialog do not count as samples. All modes use the same monitor instance for their active environment; environment replacement rebinds the selected rule configuration. Task BDDL cost and goal evaluation remain separate from these monitor annotations.


<a id="predicates"></a>

## 4. Predicates

`libero/libero/envs/predicates/base_predicates.py` retains the upstream LIBERO classes. Red-LIBERO extensions live in `custom_predicates.py`; `__init__.py` registers them. Historical imports of custom predicates from `base_predicates` remain supported through lazy exports.

Add new custom predicates to `custom_predicates.py` and register them in `VALIDATE_PREDICATE_FN_DICT`. Add a predicate to `TEMPORAL_PREDICATE_FN_LIST` only when it uses the existing temporal evaluation path. Contact-only grasp strategies share their object lookup and finger-contact sampling in `grasping.py`; the advanced strategy retains its separate lift and distance criteria.

<a id="policy-services"></a>

## 5. Policy services

Use RedVLA's lightweight package in the GUI environment and keep model stacks in separate environments. `configs/policies/` contains portable templates; `configs/policies/local/` contains ignored machine-specific profiles. The launcher runs argv without a shell, strips GUI-specific preload settings, and manages only its own child process group. See [Policy services](POLICY_SERVICES.md) for the interface, configuration, and lifecycle details.

<a id="validation"></a>

## 6. Validation

For maintainers with the ignored local test files, run from the repository root in the GUI Conda environment:

```bash
python -m pytest tests/test_gui_controllers.py -q
python -m compileall -q gui_modules libero/libero/envs/predicates
python scripts/check_studio_ui.py --output-dir /tmp/red-libero-ui-check
```

The controller tests cover contact strategies, predicate compatibility, cumulative sample counts, simultaneous logic, bindings, thresholds, unknown states, reset, policy initialization, and renderer replacement. The UI check requires a desktop or dedicated Xvfb `DISPLAY` and uses a temporary workspace. It exercises real simulator rendering, the cumulative rule builder, rule application, and editor actions without loading model weights.
