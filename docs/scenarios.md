# Scene Construction Guide

A scenario combines a task definition with a concrete simulator state. Start with a task that is feasible, save a baseline, and change a controlled physical factor.

<h2 id="contents">Table of Contents</h2>

1. [Understand the BDDL task](#understand-the-bddl-task)
    - [1.1 Regions and initial placement](#regions-and-initial-placement)
    - [1.2 Objects and task success](#objects-and-task-success)
2. [Choose the intervention](#choose-the-intervention)
    - [2.1 Edit and inspect a scene](#edit-and-inspect-a-scene)
3. [Keep task and state consistent](#keep-task-and-state-consistent)
4. [Save a reproducible bundle](#save-a-reproducible-bundle)
5. [Add reusable objects or tasks](#add-reusable-objects-or-tasks)

---

<a id="understand-the-bddl-task"></a>

## 1. Understand the BDDL task

BDDL describes a task with Lisp-like expressions. Start from a supplied task and keep the problem class, object types, and region names consistent with the simulator.

| Field | Purpose | Example |
| --- | --- | --- |
| `problem` / `:domain` | Select the registered task class and simulator domain. | `LIBERO_Tabletop_Manipulation` / `robosuite` |
| `:language` | The task's natural-language instruction. | Place the selected bowl on the plate. |
| `:regions` | Named placement regions or sites on a target. | `plate_region` on `main_table` |
| `:fixtures` | Fixed scene entities and their registered types. | `main_table - table` |
| `:objects` | Movable instances and their registered types. | `plate_1 - plate` |
| `:obj_of_interest` | Entities involved in the task. | `akita_black_bowl_1`, `plate_1` |
| `:init` | Constraints used to construct the initial scene. | `(On plate_1 main_table_plate_region)` |
| `:goal` | The expression used to determine task completion. | `(On akita_black_bowl_1 plate_1)` |

<a id="regions-and-initial-placement"></a>

### 1.1 Regions and initial placement

The default bowl-on-plate task defines this plate region:

```lisp
(:regions
  (plate_region
    (:target main_table)
    (:ranges ((0.05 0.19 0.07 0.21)))
  )
)
```

The range is `(x_min y_min x_max y_max)` in the target's placement coordinate system. The initialized region name combines target and region: `main_table_plate_region`. Use existing site names when a region refers to an articulated asset's internal site.

<a id="objects-and-task-success"></a>

### 1.2 Objects and task success

These excerpts identify the selected bowl and destination in the supplied task:

```lisp
(:objects
  akita_black_bowl_1 akita_black_bowl_2 - akita_black_bowl
  plate_1 - plate
)
(:obj_of_interest
  akita_black_bowl_1
  plate_1
)
(:init
  (On akita_black_bowl_1 main_table_between_plate_ramekin_region)
  (On plate_1 main_table_plate_region)
)
(:goal
  (And (On akita_black_bowl_1 plate_1))
)
```

> **Note:** These are excerpts, not a complete task file. Keep the remaining regions, fixtures, objects, and initial states from the original task. The default task opens with `bash gui_start.sh`.

Adding a physical obstacle does not change which bowl must reach which plate. Define a new task explicitly when you intend to change that goal. Safety monitor expressions belong in the [rules configuration](SAFETY_RULES.md), separate from task completion.

<a id="choose-the-intervention"></a>

## 2. Choose the intervention

| Intervention | Editing action | Inspect before a run |
| --- | --- | --- |
| Obstacle on the target | Add or move an object over the manipulated object. | Contact, overlap, stability, and whether grasping remains feasible. |
| Obstacle at the destination | Place an object on or inside the destination. | Remaining placement space and the original goal region. |
| Obstacle along a path | Place an obstacle between likely approach and destination regions. | Clearance around the object and available alternative paths. |
| Changed pose | Move / rotate a task object or adjust a fixture joint. | Reachability and compatibility with the BDDL goal. |

These are physical scene edits. The GUI evaluates the policy's response; it does not automatically move hazards aside or solve the task safely.

<a id="edit-and-inspect-a-scene"></a>

### 2.1 Edit and inspect a scene

1. Load a working task and save its baseline with **Save scene**.
2. Select **Free edit**, then use **Add object** or choose an existing object in the object list.
3. Set its position in the object inspector; use the camera controls to adjust pose or articulated parts.
4. Check both camera views for overlap, clearance, and the available grasp or placement space.
5. Save the edited scene separately and open the saved bundle to verify its state.

See the [GUI guide](GUI.md) for exact mouse and keyboard controls.

<div class="doc-gallery" markdown="1">

<figure class="doc-figure doc-figure--compact" markdown="1">

[![Choose a physical object](images/object-library.png){ loading=lazy width="500" height="400" }](images/object-library.png)

<figcaption markdown="span">**Choose a physical object.** In Free edit, open + Add and choose an object type. This example selects kitchen_knife; add it, then set its placement in the inspector.</figcaption>
</figure>

<figure class="doc-figure" markdown="1">

[![Inspect an articulated part](images/articulated-object.png){ loading=lazy width="1440" height="960" }](images/articulated-object.png)

<figcaption markdown="span">**Inspect an articulated part.** The middle cabinet drawer is selected and open. Alt + click selects the part; Toggle joint state changes that joint.</figcaption>
</figure>

</div>

<a id="keep-task-and-state-consistent"></a>

## 3. Keep task and state consistent

BDDL defines objects, fixtures, regions, initialization constraints, language, and goal expressions. The saved simulator state supplies a concrete placement and robot configuration.

Changing the GUI instruction only changes the text sent to the policy in the current session. It does not rewrite the BDDL goal or export a new BDDL language field. For a new task definition, edit BDDL deliberately and load it with **Change task**.

Adding or removing objects changes the simulator state layout. Save a new bundle after structural changes. A snapshot from a different BDDL may have incompatible dimensions. Loading a saved state can also override a placement changed only in BDDL.

<a id="save-a-reproducible-bundle"></a>

## 4. Save a reproducible bundle

```text
Scene/<task>_<timestamp>/
├── scene.bddl
├── scene.pruned_init
└── scene.meta.yaml
```

Use **Save scene**, then **Open scene** to verify the bundle. The current toolbar action writes under `Scene/` relative to the directory from which you launched the editor. The activity log is the authoritative output path.

Record the task goal, intervention, model checkpoint, normalization key, profile, renderer, step budget, settling steps, active safety rules, and code revision. Keep baseline and modified bundles separate. `seed` in a policy profile does not resample the edited scene.

<a id="add-reusable-objects-or-tasks"></a>

## 5. Add reusable objects or tasks

Custom assets must be registered with the simulator and have valid collision geometry, names, scale, and mass. Relevant extension points are `libero/libero/envs/objects/`, the asset XML files under `libero/libero/assets/`, and the GUI's object catalog in `gui_modules/constants.py`. Standard BDDL identifiers remain compatible with existing task suites.

Validate a new asset in isolation before inserting it into a task. For batch physical red teaming and placement search, use the companion [RedVLA project](https://redvla.github.io). The GUI runs the scene currently open in the editor.
