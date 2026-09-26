# Troubleshooting

Find the symptom below, then check the relevant environment, scene, profile, or diagnostic output.

<h2 id="contents">Table of Contents</h2>

1. [The GUI does not open](#the-gui-does-not-open)
2. [Rendering or dependency errors](#rendering-or-dependency-errors)
3. [Objects or edits appear to be missing](#objects-or-edits-appear-to-be-missing)
4. [The model service does not connect](#the-model-service-does-not-connect)
5. [The model connects but does not move](#the-model-connects-but-does-not-move)
6. [Safety rules show Unknown or no matches](#safety-rules-show-unknown-or-no-matches)
7. [The documentation fails to build](#the-documentation-fails-to-build)
8. [Report a reproducible problem](#report-a-reproducible-problem)

---

<a id="the-gui-does-not-open"></a>

## 1. The GUI does not open

Run from the red-libero root after activating the GUI Conda environment. Tk requires an X11 desktop: `DISPLAY` must point to a working display. An SSH shell alone does not create one. Follow [remote access](remote.md) for a remote desktop setup.

If Python imports a different installation, check the active interpreter and reinstall this checkout:

```bash
which python
python -m pip show red-libero
python -m pip install --no-deps -e .
```

<a id="rendering-or-dependency-errors"></a>

## 2. Rendering or dependency errors

Use the versions in [installation](installation.md), including `numpy==1.26.4` and `robosuite==1.5.1`. Install the system OSMesa/OpenGL libraries, then use `bash gui_start.sh` for the default CPU rendering path. Use `gui_start_egl.sh` only when the machine has working EGL and the intended GPU is accessible.

Keep the bundled assets with the checkout. The launcher creates a checkout-specific resource configuration; a copied configuration from another machine may point to missing files. Inspect `RED_LIBERO_CONFIG_PATH` and any legacy `LIBERO_CONFIG_PATH` override before changing it.

<a id="objects-or-edits-appear-to-be-missing"></a>

## 3. Objects or edits appear to be missing

Confirm the selected interaction mode and scene. Use **Free edit** for structural edits. An added object should appear immediately after the scene rebuild. If it does not, inspect the GUI log for an asset or rebuild failure; repeated refreshing is not a required workflow.

**Reset** restores the workspace's initial state, while **Resample** creates a new sample from BDDL constraints. Open a saved BDDL/state bundle to restore edited poses. The toolbar **Save scene** writes to `Scene/` under the current working directory; see [recording and exports](recording.md).

<a id="the-model-service-does-not-connect"></a>

## 4. The model service does not connect

Check these settings in order:

1. Select the correct protocol: `remote` for RedVLA HTTP, `openpi` for OpenPI WebSocket.
2. Resolve the endpoint from the GUI machine. Its `127.0.0.1` is not the model machine unless a tunnel forwards the port.
3. Confirm the profile's interpreter, working directory, source root, and checkpoint exist on the machine launching the service.
4. Open the service log shown by the policy dialog. Resolve import, GPU-memory, checkpoint, or action-normalization errors there.
5. Allow enough startup time for loading weights, then run **Check connection** again.

The profile field `launch.command` is an argument list. Shell operators such as `&&` are not interpreted. Put environment activation or multi-step preparation in a script and use the [custom-script recipe](models.md).

<a id="the-model-connects-but-does-not-move"></a>

## 5. The model connects but does not move

Entering AI policy prepares the run. Click **Start run** to execute. **Start service** starts the inference server; it does not start an episode. A connection check may perform diagnostic inference without executing its result in the GUI.

If execution starts but the robot behaves incorrectly, inspect the checkpoint's expected observations, action dimensions, action normalization key, gripper convention, and task domain. Connectivity alone does not establish checkpoint compatibility. See the interface contract in [connections and profiles](POLICY_SERVICES.md).

<a id="safety-rules-show-unknown-or-no-matches"></a>

## 6. Safety rules show Unknown or no matches

Use **Predicates & objects** to choose current object names and **Live results** to inspect failures. Missing objects and unsupported predicate interfaces produce Unknown. An `exists` expression with an empty selector has no matching witness; `forall` over an empty selector is logically true. Confirm selector matches before interpreting either result.

Rules describe violation conditions. A true result records an event; a false result means only that the configured condition was not detected. If a cumulative condition triggers unexpectedly, check whether `cumu` is inside or outside `exists`, and whether it counts true samples or `rising` transitions. The examples in [rule semantics](SAFETY_RULES.md) explain the distinction.

<a id="the-documentation-fails-to-build"></a>

## 7. The documentation fails to build

Use the separate `red-libero-docs` environment and run from the repository root. Install `requirements/docs.txt`, then run the strict build before the link checker. A missing Chinese predicate description or broken Markdown link is a build error to fix, not a warning to suppress. See [documentation maintenance](documentation.md).

<a id="report-a-reproducible-problem"></a>

## 8. Report a reproducible problem

Include the command, package versions, relevant log excerpt, selected profile with secrets removed, and the smallest BDDL/state bundle that reproduces the problem. For policy behavior, also report the checkpoint, instruction, seed, and action budget. Follow the [contribution guide](contributing.md).
