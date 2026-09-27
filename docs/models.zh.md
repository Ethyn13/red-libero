# 模型启动示例

先准备兼容 LIBERO 的模型权重和上游模型环境。Red-LIBERO 通过服务连接模型，不负责安装模型依赖，也不会转换不兼容的权重。

<h2 id="contents">目录</h2>

1. [选择通信协议](#_2)
2. [OpenVLA](#openvla)
3. [VLA-Adapter](#vla-adapter)
4. [使用 OpenPI 接入 π0](#openpi-0)
5. [绑定启动脚本](#_3)
6. [在 Scene Studio 中运行](#scene-studio)

---

<a id="_2"></a>

## 1. 选择通信协议

| 模型 | 配置类型 | 地址示例 | 下载模板 |
| --- | --- | --- | --- |
| OpenVLA | `remote` | `http://127.0.0.1:8002` | [openvla.yaml](downloads/configs/policies/openvla.yaml) |
| VLA-Adapter | `remote` | `http://127.0.0.1:8001` | [vla-adapter.yaml](downloads/configs/policies/vla-adapter.yaml) |
| π0 / OpenPI | `openpi` | `ws://127.0.0.1:8000` | [pi0.yaml](downloads/configs/policies/pi0.yaml) |
| 自定义脚本 | 使用支持的任一协议 | 在配置中指定 | [custom-script.yaml](downloads/configs/policies/custom-script.yaml) |

将模板复制到 Git 忽略的 `configs/policies/local/`，替换所有 `/path/to/...`。完整配置与服务生命周期见[连接与配置](POLICY_SERVICES.md)。

<a id="openvla"></a>

## 2. OpenVLA

已验证的模型环境使用 Python 3.10、Torch 2.2.0 和 Transformers 4.40.1。这些是对应源码版本的参考配置；其他上游版本应使用其要求的依赖。

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

GUI 设置 `model.type: remote`，地址为 `http://127.0.0.1:8002`。`--source-root` 指向源码，`--checkpoint` 指向权重。归一化键必须存在于权重统计信息中，并与目标任务套件匹配。

<a id="vla-adapter"></a>

## 3. VLA-Adapter

使用所选 VLA-Adapter 源码和权重要求的 Conda 环境：

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

选择 `remote`，地址为 `http://127.0.0.1:8001`。GUI 按顺序执行模型返回的动作块。归一化键和动作约定应以权重说明为准，不应仅根据目录名称推断。

<a id="openpi-0"></a>

## 4. 使用 OpenPI 接入 π0

为 [OpenPI 源码](https://github.com/Physical-Intelligence/openpi)及其客户端准备独立 Conda 环境。已验证的 π0 服务使用 Python 3.11、JAX/JAXlib 0.5.3、Flax 0.10.2 和 `pi0_libero` 权重。这些参考版本不代表所有 OpenPI 版本的依赖要求。

```bash
conda activate openpi
cd /path/to/openpi
CUDA_VISIBLE_DEVICES=0 python scripts/serve_policy.py \
  --port=8000 policy:checkpoint \
  --policy.config=pi0_libero \
  --policy.dir=/path/to/pi0_libero_checkpoint
```

选择 `openpi`，地址为 `ws://127.0.0.1:8000`。在 `model.options` 中设置 `replan_steps`、`image_size` 和 `inference_timeout`。首次请求的 JAX 编译可能比后续推理耗时更长。π0.5 使用相同传输协议，但需要对应的 OpenPI 配置。

<a id="_3"></a>

## 5. 绑定启动脚本

在 **Choose model → Launch** 中选择模型环境的 Python 和工作目录。**Choose startup script** 支持 Python 脚本、Shell 脚本和可执行文件。启动命令的每一行表示一个参数。

如果环境依赖 Conda 激活钩子，可以使用前台运行的 Shell 脚本：

```bash
#!/usr/bin/env bash
set -euo pipefail
exec /path/to/anaconda3/bin/conda run --no-capture-output \
  -n my-model python /path/to/my_server.py --port 8001
```

将 `launch.command` 设置为 `['bash', '/path/to/start_model.sh']`。服务需要实现 RedVLA HTTP 或 OpenPI WebSocket 协议；普通 HTTP 预测接口不能直接互换。

<a id="scene-studio"></a>

## 6. 在 Scene Studio 中运行

1. 打开 **Choose model**，导入已填写的 YAML。
2. 使用 **Start service** 启动托管服务；已有服务则使用 **Check connection**。
3. 等待 **Ready**，检查日志，再点击 **Use profile**。
4. 进入 **AI policy**，点击 **Start run**。
5. 退出模式前保存本轮数据。

GUI 在 BDDL 目标成功、环境终止、预算耗尽或发生错误时停止。安全监控独立记录事件，不会自动终止策略，也不会执行纠正动作。
