# red-libero 文档目录

本文档涵盖环境配置、场景构建、安全规则、VLA 服务接入和实验数据导出。可以按下方指南完成一次实验，也可以根据目录查找具体操作。

**首次使用：** [安装环境](installation.md) → [打开第一个场景](quickstart.md) → [连接模型](models.md)。

## 📚 完整文档概览

### 1. 环境配置与首次运行

配置 Conda 环境，先打开内置场景，再接入模型。

| 指南 | 内容 |
| --- | --- |
| [环境安装](installation.md) | 系统依赖、Python 3.10、NumPy 1.26.4、robosuite 1.5.1，以及 RedVLA 客户端。 |
| [第一个场景](quickstart.md) | 启动编辑器、修改单个因素、保存场景和开始策略运行。 |
| [远程访问](remote.md) | noVNC、X11，以及 GUI 与模型服务的 SSH 端口转发。 |

---

### 2. 场景构建指南

从能够完成的任务出发，保留任务目标，构建物理风险场景。

**文档：** [Scene Studio 使用指南](GUI.md) · [物理风险场景](scenarios.md)

1. 理解 BDDL 中的对象、区域、初始状态和任务目标。
2. 在编辑器中选择、添加、删除、移动和旋转物体。
3. 使用 Alt + click 检查组合物体的部件。
4. 在目标物体上、目的地或接近路径中放置障碍物。
5. 保存和恢复包含 BDDL、状态及元数据的场景包。

---

### 3. 安全规则指南

配置违规触发条件，并解释监视器的检测结果。

**文档：** [规则树与检测语义](SAFETY_RULES.md) · [谓词目录](predicates.md)

1. 向规则树插入谓词、场景对象和逻辑运算符。
2. 使用 `exists` 与 `forall` 选择检测对象范围。
3. 使用 `cumu` 累计成立采样，结合 `rising` 统计状态转换。
4. 区分当前活动条件、已记录事件与 Unknown 结果。
5. 通过共享参数目录接入自定义谓词。

---

### 4. VLA 接入指南

在独立环境中运行模型，通过服务接口连接 GUI 中当前打开的场景。

**文档：** [连接与配置](POLICY_SERVICES.md) · [模型启动示例](models.md)

| 模型 | 接口 | 配置模板 |
| --- | --- | --- |
| OpenVLA | RedVLA HTTP | [openvla.yaml](downloads/configs/policies/openvla.yaml) |
| VLA-Adapter | RedVLA HTTP | [vla-adapter.yaml](downloads/configs/policies/vla-adapter.yaml) |
| π0 / OpenPI | OpenPI WebSocket | [pi0.yaml](downloads/configs/policies/pi0.yaml) |
| 自定义启动脚本 | 使用支持的任一接口 | [custom-script.yaml](downloads/configs/policies/custom-script.yaml) |

指南包括解释器与权重路径、启动命令、连接检查、观测与动作约定，以及运行步数预算。

> **说明：** 进入 **AI policy** 只准备运行，点击 **Start run** 后才执行机器人动作。安全监控记录配置的违规条件，与 BDDL 任务成功判定相互独立。

---

### 5. 录制与导出指南

**文档：** [录制与导出](recording.md)

1. 保存可复用的场景包。
2. 在策略运行结束后导出主摄像头与腕部摄像头视频。
3. 查看 HDF5 轨迹及安全事件 JSON。
4. 记录场景、权重、模型配置、安全规则和运行环境，便于比较实验。

---

### 6. 开发与问题排查

| 指南 | 内容 |
| --- | --- |
| [项目架构](GUI_ARCHITECTURE.md) | GUI 控制器、场景恢复、策略服务与安全状态。 |
| [贡献指南](contributing.md) | 可复现的问题报告、扩展接口与可移植的改动。 |
| [文档站维护](documentation.md) | 双语 Markdown、参考内容生成、预览与静态构建。 |
| [常见问题](troubleshooting.md) | 桌面、渲染、资产、模型服务、动作兼容性与规则诊断。 |

## 🔧 命令入口

在 red-libero 仓库根目录运行，按需选择对应启动命令：

```bash
conda activate red-libero

# Open the supplied task.
bash gui_start.sh

# Open a specific task with a model profile.
bash gui_start.sh /path/to/task.bddl \
  --policy-profile configs/policies/local/my-policy.yaml
```

机器已配置 EGL 时，可使用 `bash gui_start_egl.sh` 进行 GPU 渲染。启动推理服务请使用[模型启动示例](models.md)中对应模型的命令。

## 📁 文档目录结构

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

每篇英文指南都有对应的 `.zh.md` 中文文件。站点顶部语言菜单会切换到当前页面的对应语言，导航和搜索均支持中英文。

## 🚀 推荐使用流程

1. **安装环境：** 创建 GUI Conda 环境，启动内置任务。
2. **构建场景：** 保存基准场景，修改一个物理因素，另存风险场景。
3. **配置规则：** 选择相关对象、检测谓词与累计阈值。
4. **连接 VLA：** 配置模型环境与 YAML 文件，检查服务连接。
5. **运行与分析：** 点击 **Start run**，查看任务完成与安全检测结果，导出本轮数据。

## 项目与许可证

red-libero 是 [RedVLA](https://redvla.github.io) 的场景工作台。[MIT 许可证](downloads/LICENSE)保留上游 LIBERO 的版权声明。模型代码、权重与第三方资产分别遵循其自身许可证。许可范围和来源说明见[第三方声明](downloads/NOTICE.txt)；引用配套 RedVLA 论文可使用 [CITATION.cff](downloads/CITATION.cff)。参与开发请阅读[贡献指南](contributing.md)。
