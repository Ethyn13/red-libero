# Model service recipes

Prepare a LIBERO-compatible checkpoint and the upstream model environment first. Red-LIBERO connects to services; it does not install model stacks or convert incompatible checkpoints.

<h2 id="contents">Table of Contents</h2>

1. [Pick a protocol](#pick-a-protocol)
2. [OpenVLA](#openvla)
3. [VLA-Adapter](#vla-adapter)
4. [π0 with OpenPI](#0-with-openpi)
5. [Bind a startup script](#bind-a-startup-script)
6. [Run in Scene Studio](#run-in-scene-studio)

---

<a id="pick-a-protocol"></a>

## 1. Pick a protocol

| Model | Profile type | Endpoint example | Download template |
| --- | --- | --- | --- |
| OpenVLA | `remote` | `http://127.0.0.1:8002` | [openvla.yaml](downloads/configs/policies/openvla.yaml) |
| VLA-Adapter | `remote` | `http://127.0.0.1:8001` | [vla-adapter.yaml](downloads/configs/policies/vla-adapter.yaml) |
| π0 / OpenPI | `openpi` | `ws://127.0.0.1:8000` | [pi0.yaml](downloads/configs/policies/pi0.yaml) |
| Custom script | Either supported protocol | Set in your profile | [custom-script.yaml](downloads/configs/policies/custom-script.yaml) |

Copy a template to the ignored `configs/policies/local/` directory and replace every `/path/to/...` value. Follow [connections and profiles](POLICY_SERVICES.md) for the full schema and service lifecycle.

<a id="openvla"></a>

## 2. OpenVLA

The exercised integration used Python 3.10, Torch 2.2.0, and Transformers 4.40.1 in the model environment. Treat these as reference versions for that checkout; follow your upstream revision's requirements.

```bash
conda activate openvla
python -m pip install -e /path/to/redvla
CUDA_VISIBLE_DEVICES=0 python -m redvla serve \
  --model openvla \
  --source-root /path/to/openvla \
  --checkpoint /path/to/openvla-libero-spatial \
  --options '{"unnorm_key":"libero_spatial","center_crop":true}' \
  --port 8002
```

Set GUI `model.type: remote` and `model.path: http://127.0.0.1:8002`. `--source-root` points to code; `--checkpoint` points to weights. The normalization key must exist in the checkpoint statistics and match the intended task suite.

<a id="vla-adapter"></a>

## 3. VLA-Adapter

Use the Conda environment required by the chosen VLA-Adapter source and checkpoint:

```bash
conda activate vla-adapter
python -m pip install -e /path/to/redvla
CUDA_VISIBLE_DEVICES=0 python -m redvla serve \
  --model vla-adapter \
  --source-root /path/to/VLA-Adapter \
  --checkpoint /path/to/vla-adapter-libero-spatial \
  --options '{"unnorm_key":"libero_spatial","num_open_loop_steps":8}' \
  --port 8001
```

Use `remote` with `http://127.0.0.1:8001`. Action chunks are queued in order by the GUI. Check the checkpoint's normalization key and action convention instead of inferring them from its directory name.

<a id="0-with-openpi"></a>

## 4. π0 with OpenPI

Use an independent Conda environment for the [OpenPI source](https://github.com/Physical-Intelligence/openpi) and its client package. The exercised π0 service used Python 3.11, JAX/JAXlib 0.5.3, Flax 0.10.2, and `pi0_libero`. These reference versions do not describe every OpenPI revision.

```bash
conda activate openpi
cd /path/to/openpi
CUDA_VISIBLE_DEVICES=0 python scripts/serve_policy.py \
  --port=8000 policy:checkpoint \
  --policy.config=pi0_libero \
  --policy.dir=/path/to/pi0_libero_checkpoint
```

Use `openpi` with `ws://127.0.0.1:8000`. Set `replan_steps`, `image_size`, and `inference_timeout` in `model.options`. First-request JAX compilation can take longer than subsequent inference. A π0.5 checkpoint uses the same transport but requires its own matching OpenPI configuration.

<a id="bind-a-startup-script"></a>

## 5. Bind a startup script

In **Choose model → Launch**, select the model environment's Python executable and working directory. **Choose startup script** accepts Python, shell, or executable files. Each launch-command line is one argument.

For environments that require activation hooks, a foreground shell script can run:

```bash
#!/usr/bin/env bash
set -euo pipefail
exec /path/to/anaconda3/bin/conda run --no-capture-output \
  -n my-model python /path/to/my_server.py --port 8001
```

Configure `launch.command` as `['bash', '/path/to/start_model.sh']`. The server must implement RedVLA HTTP or OpenPI WebSocket; an arbitrary HTTP prediction API is not interchangeable.

<a id="run-in-scene-studio"></a>

## 6. Run in Scene Studio

1. Open **Choose model** and import the configured YAML.
2. Use **Start service** for managed launch, or **Check connection** for an existing server.
3. Wait for **Ready**, inspect logs, and choose **Use profile**.
4. Enter **AI policy**, then click **Start run**.
5. Save the episode before leaving the mode.

The GUI stops on BDDL success, environment termination, budget exhaustion, or error. Safety monitoring records annotations independently; it does not automatically stop a policy or perform corrective actions.
