# Contributing

Contributions should make scenes easier to reproduce and model behavior easier to inspect. Keep each change focused on an observable behavior and include the corresponding documentation.

<h2 id="contents">Table of Contents</h2>

1. [Report a problem](#report-a-problem)
2. [Develop a change](#develop-a-change)
3. [Extend safety predicates](#extend-safety-predicates)
4. [Keep commits portable](#keep-commits-portable)

---

<a id="report-a-problem"></a>

## 1. Report a problem

Include the task or minimal scene bundle, reproduction steps, expected and actual behavior, project revision, package versions, renderer, and relevant log excerpt. For policy problems, include the protocol, checkpoint identifier, normalization key, timeout settings, and a profile with credentials and local paths removed.

Distinguish BDDL task success, environment cost, and Safety Monitor annotations. A rule reporting **Unknown** is different from a known false condition. A connection check is different from an executed episode.

<a id="develop-a-change"></a>

## 2. Develop a change

1. Use the [documented Conda environment](installation.md).
2. Find the responsible module in [architecture](GUI_ARCHITECTURE.md).
3. Preserve task goals and unrelated scene state when changing editor operations.
4. Keep simulation / Tk access on the GUI thread and network inference in workers.
5. Update both English and Chinese documentation when behavior changes. Keep source code and GUI labels in English.
6. Run checks appropriate to the change and record the result in the change description.

Existing local simulator tests and GUI checks are ignored by Git and may not be present in a public checkout. They are not prerequisites for installing or using Scene Studio. Documentation checks are included with the source and require only the docs environment.

<a id="extend-safety-predicates"></a>

## 3. Extend safety predicates

Implement and register the simulator predicate, then describe its argument contract in `gui_modules/safety/catalog.py`. The rule editor uses this contract for argument selection and validation. Ordinary numeric arguments are passed as numbers. Add an evaluator adapter only when a predicate needs a special environment-level call or comparison.

Document units, thresholds, statefulness, and reset behavior. Update the Chinese description in `docs/assets/predicates.zh.json`; the documentation build checks that the bilingual catalog covers every registered monitor predicate.

<a id="keep-commits-portable"></a>

## 4. Keep commits portable

Exclude checkpoints, Conda environments, datasets, scene recordings, runtime logs, machine-local profiles, credentials, and generated documentation output. `.gitignore` already covers the normal local output directories. Preserve upstream license notices and third-party asset attribution.

The current source remote is linked from the site's **Source** button. See the [RedVLA website](https://redvla.github.io) for project information and [documentation maintenance](documentation.md) for site contributions.
