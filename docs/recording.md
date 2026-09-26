# Recording and exports

This guide explains how to save a scene, export a policy episode, and retain the configuration needed to compare runs.

<h2 id="contents">Table of Contents</h2>

1. [Scene bundle versus policy episode](#scene-bundle-versus-policy-episode)
2. [Episode layout](#episode-layout)
3. [Interpret the results](#interpret-the-results)
4. [What to record for a comparison](#what-to-record-for-a-comparison)

---

<a id="scene-bundle-versus-policy-episode"></a>

## 1. Scene bundle versus policy episode

| Export | Trigger | Contents |
| --- | --- | --- |
| Scene bundle | **Save scene** | BDDL, simulator state, object / fixture metadata. |
| AI episode | Press **S** with the camera focused after a run | Dual-camera videos, safety annotations, HDF5 trajectory, episode metadata. |

Save the AI episode before leaving AI mode. **Replay** reviews the recorded trajectory; it does not query the model again.

<a id="episode-layout"></a>

## 2. Episode layout

```text
datasets/
├── video/<episode>/
│   ├── agentview.mp4
│   ├── eye_in_hand.mp4
│   └── safety_events.json
├── rlds/<episode>.hdf5
└── rlds_annotation/<episode>_info.json
```

Outputs are written under the repository's `datasets/` directory. HDF5 contains actions, simulator states, observations, and episode metadata. The directory name `rlds` refers to this project's trajectory format; it is not a TensorFlow Datasets RLDS release.

`safety_events.json` includes the active monitor configuration, rule results, diagnostics, and activation events. **Safety rules → Live results → Export events…** exports monitor details separately, even outside an AI episode.

<a id="interpret-the-results"></a>

## 3. Interpret the results

Task success follows the BDDL goal. Monitor rules are independent violation conditions. An initially true rule records one activation; an unchanged true condition does not emit an event every sample. `cumu` retains accumulated true samples until reset. Zero events do not imply that unavailable checks succeeded—inspect **Unknown** results.

<a id="what-to-record-for-a-comparison"></a>

## 4. What to record for a comparison

Keep the exact scene bundle, rules file, model checkpoint and revision, normalization key, policy YAML, runtime versions, action / settling budget, renderer, and project revision. Use the same mode and sampling cadence when comparing `cumu` thresholds. GUI runs support interactive inspection; use RedVLA batch evaluation for aggregate benchmark metrics.

Generated datasets, scenes, model weights, and local profiles are ignored by Git. Publish selected artifacts separately when you intend to distribute them.
