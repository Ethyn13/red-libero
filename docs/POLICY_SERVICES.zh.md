# VLA 连接与配置

Scene Studio 复用 **RedVLA 的模型工厂、观测转换和传输客户端**。GUI 管理当前 red-libero 场景，模型权重位于独立进程及 Python 环境。一个 profile 将连接配置与可选的服务启动器绑定。

| 模型 | GUI 协议 | 模型进程 |
| --- | --- | --- |
| OpenVLA | `remote` / HTTP | OpenVLA 环境中的 `redvla serve --model openvla`。 |
| VLA-Adapter / Pro / OpenVLA-OFT | `remote` / HTTP | 对应上游环境中的 RedVLA 服务后端。 |
| π0 / π0.5 | `openpi` / WebSocket | 使用匹配配置和权重的 OpenPI 服务。 |
| 自定义 VLA | 支持的任一协议 | RedVLA `PolicyModel` 服务或兼容 OpenPI 的服务。 |

<h2 id="contents">目录</h2>

1. [独立 Conda 环境](#conda)
2. [在 Choose model 中配置](#choose-model)
3. [服务生命周期](#_1)
4. [YAML profile](#yaml-profile)
5. [导入 RedVLA 评测配置](#redvla)
6. [观测与动作约定](#_2)

---

<a id="conda"></a>

## 1. 独立 Conda 环境

GUI 环境按[安装指南](installation.md)配置，使用 Python 3.10、NumPy 1.26.4 和 robosuite 1.5.1。保持 red-libero 代码与资产在同一源码目录。策略客户端安装方式：

```bash
conda activate red-libero
python -m pip install -c requirements/studio.txt -e /path/to/redvla
```

各模型及其权重按照上游要求准备。OpenVLA 和 VLA-Adapter 的模型环境也需要安装基础 RedVLA 包：

```bash
/path/to/anaconda3/envs/vla-adapter/bin/python -m pip install -e /path/to/redvla
```

GUI 不会从模型环境导入模型后端。彼此冲突的 Torch、Transformers 和 JAX 依赖应放在各自模型环境。具体启动命令见[模型示例](models.md)。

<a id="choose-model"></a>

## 2. 在 Choose model 中配置

1. 打开 **Choose model**，从 `configs/policies/` 选择模板，或点击 **Import YAML**。
2. 在 **Connection** 设置协议、地址和超时。RedVLA 服务使用 HTTP，OpenPI 使用 WebSocket。
3. 在 **Launch** 选择模型环境中的 Python、仓库工作目录及命令参数。每行一个参数，`{python}` 会展开成指定解释器。**Choose startup script** 支持 Python、Shell 和可执行文件。环境 JSON 中可填写 `CUDA_VISIBLE_DEVICES`。
4. 替换权重路径，填写权重统计信息中真实存在的归一化键。模板中的 `libero_spatial` 是例子，不会自动与任务匹配。
5. 使用 **Start service** 在后台启动并检查就绪状态，**Logs** 查看日志。已有服务使用 **Check connection**。连接检查可能调用诊断推理，但不会执行 GUI 机器人或占用 HTTP episode。
6. 点击 **Use profile** 保存并选择配置，进入 **AI policy** 后点击 **Start run**。进入 AI 模式不会连接模型、重置 episode 或开始录制，也不会推进仿真。

保存的 profile 位于 `configs/policies/local/`，选择记录与服务日志位于 `.gui-runtime/`，均被 Git 忽略。修改 profile 不会更新已运行服务；修改启动参数后需要停止原托管服务再启动。

<a id="_1"></a>

## 3. 服务生命周期

启动器直接执行参数列表，不经过 Shell 字符串插值。它将模型解释器目录加入 `PATH` 并设置 `CONDA_PREFIX`，但不执行 Conda 激活钩子。有激活要求的模型可以使用 `conda run --no-capture-output` 或显式激活的前台脚本。服务脚本不要自行 daemonize。GUI 专用的 Tk 预加载变量会从子环境移除。

**Stop owned service** 只终止当前 GUI 启动的进程及其 Linux 进程组，不会停止通过地址发现的外部服务。关闭配置窗口保留托管服务；关闭 GUI 会清理其托管服务。启动失败、超时和取消也会清理对应进程。

托管启动要求回环地址，并在 **GUI 所在主机**执行。另一台机器上的服务应在那里启动，再使用可访问地址或 SSH 隧道连接。认证变量为 HTTP 的 `REDVLA_API_TOKEN` 和 OpenPI 的 `OPENPI_API_KEY`，不要将凭据直接写进公开配置。

<a id="yaml-profile"></a>

## 4. YAML profile

```yaml
version: 1
name: My VLA
model:
  type: remote
  path: http://127.0.0.1:8001
  options: {timeout: 120}
run: {max_steps: 520, settle_steps: 10, seed: 0}
launch:
  python: /path/to/anaconda3/envs/my-vla/bin/python
  cwd: /path/to/my-vla
  command: ['{python}', /path/to/start_server.py, --port, '8001']
  env: {CUDA_VISIBLE_DEVICES: '0'}
  startup_timeout: 180
```

连接已有服务时，省略 `launch`。Python 与工作目录路径支持绝对路径、用户目录、环境变量 `${MODEL_ROOT}` 和相对于 YAML 的路径。命令参数从指定工作目录执行。环境覆盖值必须是字符串，因此 GPU 编号应加引号。

```bash
conda activate red-libero
bash gui_start.sh /path/to/task.bddl --policy-profile configs/policies/local/My-VLA.yaml
```

`--vla-model` 是兼容别名，同样要求 YAML 文件。

<a id="redvla"></a>

## 5. 导入 RedVLA 评测配置

**Import YAML** 支持评测器的 `models` 映射。远程类型 `remote`、`openpi`、`pi0`、`pi05` 可转成 GUI profile；本地权重加载配置会被拒绝，需要先在独立环境启动服务。GUI 只导入连接设置和默认预算，不导入任务列表或攻击配置。

```yaml
models:
  adapter:
    type: remote
    path: http://127.0.0.1:8001
    options: {timeout: 120}
  pi0:
    type: openpi
    path: ws://127.0.0.1:8000
    options: {replan_steps: 8, inference_timeout: 120}
defaults:
  max_steps: 520
```

<a id="_2"></a>

## 6. 观测与动作约定

GUI 从当前同一个仿真器获得 256×256 的双摄像头图像和本体状态。RedVLA 的 `from_libero` 按约定将图像转换为 RGB 并旋转 180°，生成 8 维末端与夹爪状态。模型服务负责预处理和归一化，OpenPI 客户端按配置调整图像尺寸和重规划长度。

返回动作必须是有限值的 `[T, 7]` LIBERO OSC 指令，并使用正确的夹爪约定。GUI 不会再次归一化，也不会再次反转夹爪符号。完整动作块按顺序入队，包括超过八步的动作块。

网络操作在后台线程，仿真、检测、观测和绘制在 GUI 线程。Pause 冻结执行；退出 AI 模式会恢复 Start run 时的场景，迟到的网络返回不能继续推进场景。网络请求关闭可能需要等待配置的超时。

运行在任务成功、环境终止、预算耗尽或错误时停止。稳定步数计入 `max_steps`。`seed` 作为 HTTP 推理上下文传递，具体是否使用取决于后端；标准 OpenPI 不传递该字段。它不会重新采样当前编辑场景。

缺失配置或连接失败不会产生占位动作。HTTP episode 租约阻止多个客户端同时占用一个模型 episode。并发评测应使用独立服务；标准 OpenPI 也应在运行时为当前 GUI 独占服务。
