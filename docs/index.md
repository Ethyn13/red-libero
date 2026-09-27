# red-libero Documentation

This documentation covers environment setup, scene construction, safety rules, VLA services, and experiment exports. Follow the guides in order for a first experiment, or use the directory to find a specific operation.

**New users:** [Install the environment](installation.md) → [Open your first scene](quickstart.md) → [Connect a model](models.md).

<figure class="doc-figure" markdown="1">

[![Scene Studio at a glance](images/studio-overview.png){ loading=lazy width="1440" height="960" }](images/studio-overview.png)

<figcaption markdown="span">**Scene Studio at a glance.** Select an object on the left, inspect both camera views, and edit its position or prepare a policy on the right.</figcaption>
</figure>

## Visual workflow {#visual-workflow}

Click any screenshot to open the full-resolution image. Follow a guide to reproduce the operation.

<div class="doc-gallery" markdown="1">

<figure class="doc-figure doc-figure--compact" markdown="1">

[![Choose a physical object](images/object-library.png){ loading=lazy width="500" height="400" }](images/object-library.png)

<figcaption markdown="span">**Choose a physical object.** In Free edit, open + Add and choose an object type. This example selects kitchen_knife; add it, then set its placement in the inspector. [Open guide](scenarios.md).</figcaption>
</figure>

<figure class="doc-figure" markdown="1">

[![Build a rule as a tree](images/safety-rule-tree.png){ loading=lazy width="1120" height="760" }](images/safety-rule-tree.png)

<figcaption markdown="span">**Build a rule as a tree.** The example combines a cumulative distance condition, a quantified fall check, and an arm-force rule. Select a node to inspect its arguments. [Open guide](SAFETY_RULES.md).</figcaption>
</figure>

<figure class="doc-figure" markdown="1">

[![Connect a policy service](images/policy-connection.png){ loading=lazy width="1040" height="780" }](images/policy-connection.png)

<figcaption markdown="span">**Connect a policy service.** Select the protocol, endpoint, and timeout. The example uses RedVLA HTTP at a local endpoint; OpenPI uses WebSocket. [Open guide](POLICY_SERVICES.md).</figcaption>
</figure>

<figure class="doc-figure" markdown="1">

[![Start only when ready](images/policy-ready.png){ loading=lazy width="1440" height="960" }](images/policy-ready.png)

<figcaption markdown="span">**Start only when ready.** AI policy is prepared, with Start run enabled. No model inference or robot execution has started in this screenshot. [Open guide](quickstart.md).</figcaption>
</figure>

</div>

## 📚 Documentation Overview

### 1. Installation and First Run

Set up the Conda environment and open the supplied scene before connecting a model.

| Guide | Contents |
| --- | --- |
| [Environment installation](installation.md) | System libraries, Python 3.10, NumPy 1.26.4, robosuite 1.5.1, and the RedVLA client. |
| [Your first scene](quickstart.md) | Launch the editor, change one factor, save the scene, and start a policy run. |
| [Remote access](remote.md) | noVNC, X11, and SSH forwarding for GUI and model services. |

---

### 2. Scene Construction Guide

Build a risk scenario from a working task while preserving its goal.

**Guides:** [Scene Studio](GUI.md) · [Physical risk scenarios](scenarios.md)

1. Understand BDDL objects, regions, initial states, and task goals.
2. Select, add, remove, move, or rotate objects in the editor.
3. Inspect articulated parts with Alt + click.
4. Place obstacles on a target, at a destination, or along an approach path.
5. Save and restore a BDDL/state/metadata bundle.

---

### 3. Safety Rule Guide

Configure violation conditions and interpret the monitor's results.

**Guides:** [Rule tree and semantics](SAFETY_RULES.md) · [Predicate catalog](predicates.md)

1. Insert predicates, scene objects, and logical operators into the rule tree.
2. Choose object scope with `exists` and `forall`.
3. Accumulate true samples with `cumu`, or transitions with `rising`.
4. Distinguish active conditions, recorded events, and Unknown results.
5. Extend predicates using the shared argument catalog.

---

### 4. VLA Integration Guide

Run a model in its own environment and connect it to the scene open in the GUI.

**Guides:** [Connections and profiles](POLICY_SERVICES.md) · [Model service recipes](models.md)

| Model | Interface | Configuration template |
| --- | --- | --- |
| OpenVLA | RedVLA HTTP | [openvla.yaml](downloads/configs/policies/openvla.yaml) |
| VLA-Adapter | RedVLA HTTP | [vla-adapter.yaml](downloads/configs/policies/vla-adapter.yaml) |
| π0 / OpenPI | OpenPI WebSocket | [pi0.yaml](downloads/configs/policies/pi0.yaml) |
| Custom startup script | Either supported interface | [custom-script.yaml](downloads/configs/policies/custom-script.yaml) |

The guides explain interpreter and checkpoint paths, startup commands, connection checks, observations, actions, and episode budgets.

> **Note:** Entering **AI policy** prepares a run. Robot execution begins after **Start run**. Safety monitoring records configured conditions independently of BDDL task success.

---

### 5. Recording and Export Guide

**Guide:** [Recording and exports](recording.md)

1. Save a reusable scene bundle.
2. Export main-camera and wrist-camera videos after a policy episode.
3. Inspect HDF5 trajectories and safety-event JSON.
4. Record the scene, checkpoint, profile, rules, and runtime settings for comparison.

---

### 6. Development and Troubleshooting

| Guide | Contents |
| --- | --- |
| [Project architecture](GUI_ARCHITECTURE.md) | GUI controllers, scene restoration, policy services, and safety state. |
| [Contributing](contributing.md) | Reproducible issue reports, extension points, and portable changes. |
| [Documentation maintenance](documentation.md) | Bilingual Markdown, reference generation, preview, and static builds. |
| [Troubleshooting](troubleshooting.md) | Display, rendering, assets, services, action compatibility, and rule diagnostics. |

## 🔧 Entry Points

Run from the red-libero repository root, choosing the command for your task:

```bash
conda activate red-libero

# Open the supplied task.
bash gui_start.sh

# Open a specific task with a model profile.
bash gui_start.sh /path/to/task.bddl \
  --policy-profile configs/policies/local/my-policy.yaml
```

Use `bash gui_start_egl.sh` when GPU rendering with EGL is configured. To start an inference service, follow [model service recipes](models.md).

## 📁 Documentation Structure

```text
docs/
├── index.md / index.zh.md       Documentation overview
├── installation.md             Environment setup
├── quickstart.md               First experiment
├── GUI.md                      Scene Studio controls
├── scenarios.md                BDDL and physical risk scenarios
├── SAFETY_RULES.md              Rule tree and cumulative conditions
├── predicates.md                Predicate reference
├── POLICY_SERVICES.md          Service interface and YAML profiles
├── models.md                   Model startup commands
├── recording.md                Scene and episode exports
├── remote.md                   Remote access
├── GUI_ARCHITECTURE.md         Internal architecture
├── contributing.md             Contribution guide
├── documentation.md            Site maintenance
├── troubleshooting.md          Common problems
├── images/                     GUI screenshots
└── assets/                     Styles and translated reference text
```

Every English guide has a matching `.zh.md` file. The language menu switches to the corresponding page; navigation and search cover both languages.

## 🚀 Recommended Workflow

1. **Install:** create the GUI Conda environment and launch the supplied task.
2. **Construct:** save a baseline, edit one physical factor, and save a separate risk scenario.
3. **Configure rules:** select the relevant objects, predicates, and cumulative thresholds.
4. **Connect a VLA:** configure a model environment and profile, then check the connection.
5. **Run and inspect:** click **Start run**, inspect task completion and safety results, and export the episode.

## Project and License

red-libero is the scene workspace for [RedVLA](https://redvla.github.io). The [MIT license](downloads/LICENSE) includes the copyright notice for red-libero contributors' original additions and modifications, and retains the upstream LIBERO notice. Model code, checkpoints, and third-party assets follow their respective licenses. See the [third-party notices](downloads/NOTICE.txt) for scope and attribution, and the [README citation section](https://github.com/Ethyn13/red-libero#citation) for the RedVLA paper's BibTeX entry. Contributions are described in the [contribution guide](contributing.md).
