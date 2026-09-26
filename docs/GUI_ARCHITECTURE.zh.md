# 项目架构

Scene Studio 的交互控制器位于 `gui_modules`，桌面入口为 `editor_gui.py`。

```python
from gui_modules.ai_mode import AIController
from gui_modules.safety_monitor import SafetyMonitor
```

<h2 id="contents">目录</h2>

1. [模块职责](#_2)
2. [GUI 线程与环境切换](#gui)
3. [安全状态](#_3)
4. [扩展谓词](#_4)
5. [策略服务](#_5)
6. [维护检查](#_6)

---

<a id="_2"></a>

## 1. 模块职责

| 模块 | 职责 |
| --- | --- |
| `studio_ui.py`、`studio_theme.py`、`dialogs.py` | 工作台布局、主题和选择窗口。 |
| `event_handlers.py`、`frame_updater.py` | 输入分发、GUI 刷新和排队操作。 |
| `object_management.py`、`joint_control.py`、`coordinate_utils.py` | 物体增删、关节检查和坐标转换。 |
| `editor_gui.py`、`init_state_io.py` | 场景编排、移动、标定、序列化及状态恢复。 |
| `ai_mode.py` | 模型生命周期与运行协调。 |
| `policy/` | YAML 配置、客户端、服务进程管理及连接界面。 |
| `safety_monitor.py` | 检测结果、事件历史和重置。 |
| `safety/expressions.py`、`safety/catalog.py` | 表达式求值、绑定、参数契约和累计状态。 |
| `safety/tree_model.py`、`safety/tree_editor.py` | 可撤销的规则树编辑、谓词与对象参数选择。 |
| `safety/dialog.py` | 规则应用、源文本同步、目录和实时诊断。 |

<a id="gui"></a>

## 2. GUI 线程与环境切换

场景选择、移动、标定、BDDL 导入及快照恢复由 `MatplotlibGUIEditor` 协调，`FrameUpdater` 在 GUI 线程派发排队请求。替换环境时先绑定旧 OpenGL 上下文并释放其资源，再在 GUI 线程激活新上下文。导入或恢复后，安全监控重新绑定当前环境。

策略后台线程只执行网络操作，不访问 Tk 或仿真器。GUI 更新循环负责捕获观测、执行动作、进行检测和绘制。离开 AI 模式时停止后续动作并按名称恢复进入运行时的场景，迟到的网络回复不能修改环境。

<a id="_3"></a>

## 3. 安全状态

在 episode 边界调用 `SafetyMonitor.reset()`，清空事件、状态转换历史和累计计数。独立规则是 `:safety_rules` 下的同级节点。and 要求同一采样内同时成立，不组合不同时间的状态。cumu 在假值间隙中保留计数，同一采样的缓存防止重复增加。

Physics 在真实仿真更新后检查；Human Assist 和 AI policy 在动作后检查。渲染、规则校验和打开窗口不产生采样。所有模式对当前环境使用相同监控实例，环境切换后重新加载选定配置。任务 BDDL 的 cost 和 goal 保持独立。

规则树与源文本通过同一个解析器进行校验，未完成子条件不能应用。树的位置和作用域会影响计数器归属，参见[规则语义](SAFETY_RULES.md)。

<a id="_4"></a>

## 4. 扩展谓词

`libero/libero/envs/predicates/base_predicates.py` 保留上游类，自定义扩展位于 `custom_predicates.py`，由 `__init__.py` 注册。历史导入通过延迟导出兼容。

添加检测逻辑时，在 `custom_predicates.py` 实现函数，并注册到 `VALIDATE_PREDICATE_FN_DICT`。然后向 `gui_modules/safety/catalog.py` 添加参数类型和解释。只有依赖既有时序执行路径的谓词才加入 `TEMPORAL_PREDICATE_FN_LIST`。涉及原始距离到布尔阈值或环境级调用时，检查 `ExpressionEvaluator._atom` 是否需要适配。

抓取检测共用 `grasping.py` 中的对象查找及手指接触采样，复杂策略保留其抬升和距离条件。扩展时应明确未知对象、不支持的状态接口和重置行为。

<a id="_5"></a>

## 5. 策略服务

GUI 环境只安装 RedVLA 基础客户端，模型依赖留在独立环境。`configs/policies/` 存放模板，`configs/policies/local/` 存放被忽略的本机配置。启动器执行参数列表，移除 GUI 专用预加载设置，仅管理自己启动的进程组，见[连接与配置](POLICY_SERVICES.md)。

<a id="_6"></a>

## 6. 维护检查

持有本地验证文件的维护者，可在 GUI 环境中运行单元检查和真实 Tk/MuJoCo 检查；`tests/` 及本地 GUI 检查脚本已被 Git 忽略。界面检查应使用独立显示会话和临时工作区，避免影响当前实验。

公开文档使用独立环境进行严格构建、双语页面检查与内部链接检查，见[文档站维护](documentation.md)。
