# Predicate catalog

Predicates are the leaves of a safety rule tree. A leaf receives scene entities and, when required, numeric thresholds or geometry parts. Logical operators and counters compose those leaves; see [rule tree and semantics](SAFETY_RULES.md).

The table below is generated from `gui_modules/safety/catalog.py`, the same argument catalog used by the rule editor. It documents the built-in contracts; detection behavior is implemented in `libero/libero/envs/predicates/` and the scene's object state classes.

<h2 id="contents">Table of Contents</h2>

1. [Argument types](#argument-types)
2. [Built-in predicates](#built-in-predicates)
3. [Interpret the result](#interpret-the-result)
4. [Extend the catalog](#extend-the-catalog)

---

<a id="argument-types"></a>

## 1. Argument types

| Type | Meaning |
| --- | --- |
| `object` | An exact scene entity or a bound variable, such as `?x`. The selected predicate must support that entity's state interface. |
| `number` | A numeric threshold. Distances use meters and force thresholds use newtons. |
| `robot` | The optional robot placeholder accepted by the arm checks. |
| `parts` | `all` or a list of geometry suffixes supported by that object's contact evaluator. |

Use **Predicates & objects** in the GUI to inspect available names and **Live results** to inspect unresolved inputs. An available name does not guarantee that every predicate supports that entity.

<a id="built-in-predicates"></a>

## 2. Built-in predicates

<!-- predicate-catalog:en -->

<a id="interpret-the-result"></a>

## 3. Interpret the result

These detectors implement simulator-specific checks. In particular, `fall` uses the scene object's pose-change check; it is not a general physical definition of falling. `waterfall` combines the relevant pair's contact and fall checks. Verify a detector against your asset and task before using it as an experimental metric.

`notin` is not interchangeable with `(not (in ...))`: the former requires both contact and containment to be absent. `up` uses a fixed world-height threshold, not height relative to a table. Distance predicates compare surface distance, and the supplied threshold is inclusive.

Missing entities, unsupported state interfaces, and evaluation errors produce **Unknown** diagnostics. Negating an unknown value does not establish safety. The monitor records configured violations; it does not plan corrective actions or stop a policy automatically.

<a id="extend-the-catalog"></a>

## 4. Extend the catalog

Implement the detector and its registered name, add its accepted signatures to the catalog, and add a Chinese description to `docs/assets/predicates.zh.json`. Rebuild the documentation to verify translation coverage. Follow the [contribution guide](contributing.md) and check both positive and negative examples in a controlled scene.
