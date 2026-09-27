# 第一个场景

完成[环境安装](installation.md)后，在桌面会话中进入 Red-LIBERO 根目录，按以下步骤操作。

<h2 id="contents">目录</h2>

1. [打开编辑器](#1)
2. [修改一个物理因素](#2)
3. [保存场景](#3)
4. [查看安全规则](#4)
5. [准备好后运行 VLA](#5-vla)

---

## 1. 打开编辑器

```bash
conda activate red-libero
bash gui_start.sh
```

默认任务要求机器人将盘子和小碗之间的黑碗放到盘子上。主摄像头与腕部摄像头显示同一个仿真环境。通过 **Change task** 选择其他 BDDL 任务，或者直接指定文件：

```bash
bash gui_start.sh /path/to/task.bddl
```

<figure class="doc-figure" markdown="1">

[![认识 Scene Studio](images/studio-overview.png){ loading=lazy width="1440" height="960" }](images/studio-overview.png)

<figcaption markdown="span">**认识 Scene Studio.** 左侧选择物体，中间查看主摄像头与腕部摄像头，右侧调整位置、查看安全状态并配置策略。</figcaption>
</figure>

## 2. 修改一个物理因素

1. 进入 **Free edit**。
2. 在物体列表或摄像头画面中选择物体。
3. 拖动修改 XY 位置，滚轮调整高度，或者在检查面板中输入精确 XYZ 坐标。
4. 使用 **+ Add** 添加障碍物，使用 **Remove** 删除选中的可移动物体。
5. 切换到 **Physics** 检查物理稳定后的摆放。

建议从一个能够完成的任务开始，每次只改变一个因素。比较原始场景和风险场景时保持任务目标一致，详见[风险场景](scenarios.md)。

<figure class="doc-figure doc-figure--compact" markdown="1">

[![选择要加入的物理物体](images/object-library.png){ loading=lazy width="500" height="400" }](images/object-library.png)

<figcaption markdown="span">**选择要加入的物理物体.** 进入 Free edit，点击 + Add 并选择物体类型。图中选择 kitchen_knife；添加后再通过对象检查器设置摆放位置。</figcaption>
</figure>

## 3. 保存场景

点击 **Save scene**。活动日志会显示启动目录下 `Scene/` 中新建的文件夹。BDDL、状态与元数据需要一起保存。**Open scene** 恢复完整场景包；**Reset** 恢复工作区基准；**Resample** 按 BDDL 重新采样摆放。

## 4. 查看安全规则

打开 **Safety Monitor → Rules & detections…**。展开规则，选择谓词，点击 **Edit node** 查看对象参数。通过 **Add rule** 和 **Insert child** 添加条件；通过 **Wrap node… → Cumulative samples (cumu)** 添加累计采样阈值。

**Validate** 检查草稿；**Apply** 启用规则并清空检测历史。这里定义的是违规触发条件，因此结果为真时会记录事件。比较事件数量之前，请阅读[规则语义](SAFETY_RULES.md)。

<figure class="doc-figure" markdown="1">

[![用树节点构建规则](images/safety-rule-tree.png){ loading=lazy width="1120" height="760" }](images/safety-rule-tree.png)

<figcaption markdown="span">**用树节点构建规则.** 示例包含累计距离条件、带对象量词的跌落检测和机械臂受力规则。选择节点即可查看其参数。</figcaption>
</figure>

## 5. 准备好后运行 VLA

配置[模型服务](models.md)，然后：

1. 点击 **Choose model → Use profile**。
2. 进入 **AI policy**。
3. 点击 **Start run**。
4. 查看任务结果和安全事件。
5. 退出 AI 模式前，聚焦摄像头区域并按 **S** 导出本轮数据。

进入 AI policy 不会直接开始机器人动作。连接检查可能向模型发送诊断推理请求，但不会推进 GUI 中的机器人。详见[连接与配置](POLICY_SERVICES.md)。

<figure class="doc-figure" markdown="1">

[![准备好后再开始运行](images/policy-ready.png){ loading=lazy width="1440" height="960" }](images/policy-ready.png)

<figcaption markdown="span">**准备好后再开始运行.** AI policy 已准备就绪，Start run 按钮可用。截图时尚未发起模型推理，也未开始机器人执行。</figcaption>
</figure>
