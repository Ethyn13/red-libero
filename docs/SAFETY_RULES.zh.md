# 安全规则与树编辑器

打开 **Safety Monitor → Rules & detections…**。默认的 **Rule tree** 页允许直接构建规则，无需手写 BDDL。展开节点后，可以查看逻辑条件、谓词、对象变量和阈值。

<h2 id="contents">目录</h2>

1. [使用规则树](#_2)
2. [exists 是什么意思](#exists)
3. [其他页面与配置文件](#_3)
4. [cumu 的累计语义](#cumu)
    - [4.1 各模式的采样单位](#_4)
    - [4.2 对象计数与共享计数](#_5)
5. [逻辑、名词与选择器](#_6)
6. [数值阈值与不可用检测](#_7)
7. [扩展与迁移](#_8)

---

<a id="_2"></a>

## 1. 使用规则树

<figure class="doc-figure" markdown="1">

[![用树节点构建规则](images/safety-rule-tree.png){ loading=lazy width="1120" height="760" }](images/safety-rule-tree.png)

<figcaption markdown="span">**用树节点构建规则.** 示例包含累计距离条件、带对象量词的跌落检测和机械臂受力规则。选择节点即可查看其参数。</figcaption>
</figure>

1. 点击 **Add rule**，选择 **Predicate** 或 **Operator**。谓词需要先选择函数及参数形式，再选择场景物体、固定设施、区域或绑定变量，并填写必要的数值阈值。
2. 选中逻辑节点，点击 **Insert child**。未完成的位置显示为 **Choose a condition**，并阻止 Apply。选择谓词或参数行，点击 **Edit node** 修改参数；**Replace** 替换整个条件。
3. 对已有条件进行累计检测时，在 **Wrap selected condition with** 中选择 **Cumulative samples (cumu)**，点击 **Wrap node…**，填写 **True samples**。其他外层运算包括 and、or、not、exists、forall、implies 和 rising。
4. 使用 **Remove**、**Move up/down**、**Undo** 和 **Redo** 管理节点。只允许重排独立规则和 and/or 的子条件，固定参数顺序不会被改变。修改变量名称时，其绑定引用会一起更新。
5. **Validate** 检查语法、参数、阈值和变量作用域，不推进仿真。**Apply** 启用配置并清空检测历史。执行 AI 任务或处于 Human Assist 时，需要先结束运行或退出该模式。
6. Physics、Human Assist 和 AI policy 收集检测采样，Free edit 暂停检测。**Live results** 显示结果、累计进度、命中对象及诊断，**Export events…** 导出 JSON。

对象下拉框支持输入筛选，也接受精确名称、BDDL 类型和选择器。这里的规则是**违规触发条件**：表达式为真时，指定事件处于活动状态。

<figure class="doc-figure doc-figure--compact" markdown="1">

[![选择谓词与对象参数](images/safety-predicate.png){ loading=lazy width="620" height="500" }](images/safety-predicate.png)

<figcaption markdown="span">**选择谓词与对象参数.** 距离谓词需要场景对象和以米为单位的阈值。图中以 0.05 m 为阈值检查夹爪与物体的距离。</figcaption>
</figure>

<a id="exists"></a>

## 2. exists 是什么意思

**Any matching object (exists)** 表示“选定范围内，至少有一个对象满足子条件”。它定义对象范围，不表示累计次数。

```text
Any matching object (exists)     ?knife in @objects:*knife*
├── Object variable             ?knife
├── Objects to check            @objects:*knife*
└── Cumulative samples (cumu)    At least 3 true samples
    ├── True samples            3
    └── checkbladecontact
        └── Object 1            ?knife
```

该树表示：任意一把刀的刀刃接触条件在不同采样中累计成立三次，就触发规则。对应表达式：

```lisp
(exists (?knife - @objects:*knife*)
  (cumu (checkbladecontact ?knife) 3))
```

`?knife` 是代表当前匹配对象的变量；`@objects:*knife*` 从可移动物体中筛选名称含 `knife` 的对象。把 cumu 放到 exists 外面会形成全场景共享计数器，因此树的嵌套顺序具有实际含义。

<a id="_3"></a>

## 3. 其他页面与配置文件

**Predicates & objects** 原名 Reference & scene，是查询目录：左侧解释谓词、运算和选择器，右侧列出真实场景名词。编辑节点时从参数下拉框选择这些名词。

**BDDL source (advanced)** 保留文本编辑。**Update tree** 校验并导入文本，错误文本不会覆盖已有规则树；**Discard source edits** 恢复最后的树。树编辑会重新生成 BDDL，原始排版和注释不会保留。

Apply 后，规则保存到启动目录的 `.red-libero/safety_rules.bddl`，切换场景或重启后仍然有效。没有该文件时使用 `gui_modules/safety_monitoring_config.bddl`。**Open** 只载入编辑草稿，**Save as** 只导出配置，二者都需要 Apply 才生效。

<figure class="doc-figure" markdown="1">

[![查找谓词与场景对象](images/safety-catalog.png){ loading=lazy width="1120" height="760" }](images/safety-catalog.png)

<figcaption markdown="span">**查找谓词与场景对象.** 在同一页面查询谓词的参数签名，以及当前场景中可用的物体和区域名称。</figcaption>
</figure>

<a id="cumu"></a>

## 4. cumu 的累计语义

<figure class="doc-figure doc-figure--compact" markdown="1">

[![设置累计采样阈值](images/safety-cumulative.png){ loading=lazy width="620" height="500" }](images/safety-cumulative.png)

<figcaption markdown="span">**设置累计采样阈值.** 图中条件在三个检测样本为真后触发。假值样本保留已有计数，重置会清空计数。</figcaption>
</figure>

下载[累计条件样例](downloads/configs/safety/cumulative.bddl)。

```lisp
(define (safety_monitoring)
  (:safety_rules
    (cumu (checkarmforce robot 20) 5)
    (cumu
      (and (in kitchen_knife_1 microwave_1_heating_region)
           (close microwave_1))
      3)))
```

`(cumu CONDITION N)` 表示 CONDITION 在本轮中至少 N 个不同检测采样为真。假值保留已有计数；同一采样内重复查询不会增加计数；重置会清零。达到阈值后持续为真，记录一次激活事件，而不是每一步重复触发。

例如条件序列为 `true, false, true, false, true`，N=3 时，计数为 `1, 1, 2, 2, 3`，第五个采样触发。它统计真值采样数，不是秒数、连续步数或独立接触次数。

要累计从假变真的次数，使用 `(cumu (rising CONDITION) N)`。`rising` 需要一个已知为假的基准，初始就为真的条件不会算作上升沿。旧写法 `(cumu checkgrasping kitchen_knife_1 5)` 会被规范化为嵌套写法。

<a id="_4"></a>

### 4.1 各模式的采样单位

Physics 每次真实仿真更新后检查一次，目前一次更新包含十个 MuJoCo 子步；Human Assist 和 AI policy 在每个动作后检查，AI 稳定动作也计入。渲染、暂停和等待推理不会增加采样。跨实验比较时应使用相同模式与采样频率。

<a id="_5"></a>

### 4.2 对象计数与共享计数

```lisp
; One counter per knife.
(exists (?knife - @objects:*knife*)
  (cumu (checkbladecontact ?knife) 3))

; One shared scene counter, incremented at most once per sample.
(cumu
  (exists (?knife - @objects:*knife*) (checkbladecontact ?knife))
  3)
```

上面第一条规则为每把刀分别计数；第二条规则只要某把刀命中，就给场景共享计数器增加一次。

<a id="_6"></a>

## 5. 逻辑、名词与选择器

`:safety_rules` 下的同级表达式是独立违规条件，不会自动取反来推导安全要求。

| 表达式 | 含义 |
| --- | --- |
| `(and A B)` | 同一采样内 A、B 均成立。 |
| `(or A B)` | 至少一个成立。 |
| `(not A)` | 对已知结果取反；未知仍为未知。 |
| `(implies A B)` | 逻辑蕴含；检测违背该要求应写 `(and A (not B))`。 |
| `(cumu A N)` | 本轮 A 累计在至少 N 个采样中成立。 |
| `(rising A)` | A 从已知的假变为真。 |
| `(exists (?x - selector) A)` | 至少一个匹配对象满足 A。 |
| `(forall (?x - selector) A)` | 每个匹配对象都满足 A。 |
| `(equal object_a object_b)` | 两个名称指向同一实体。 |

`in`、`on`、`over`、`incontact` 等关系谓词连接两个场景名词。`open`、`close`、`turnon`、`up` 等描述状态；其他安全谓词包括跌落、碰撞、抓取、刀刃接触、受力和卡住等，具体判定以[谓词目录](predicates.md)和实现为准。

可使用精确实例 `kitchen_knife_1`、类型 `kitchen_knife`、简短名词 `knife` 或通配符 `*knife*`。简短名词匹配对象及固定物类型或实例名称中以下划线分隔的完整词段，例如 `knife` 匹配 `kitchen_knife_1` 和 `knife_n_1`，不会匹配 `knifeblock_1` 或同名区域，兼容 RedVLA 场景规则中的简写名词。带数字的精确实例缺失时不会退回匹配同类型的其他对象。命名选择器为 `@objects`、`@fixtures`、`@regions`、`@all`、`@task`。作用域通配符 `@objects:*knife*` 可以排除同名区域。

任务对象正常参与检测，不会自动跳过。exists 没有匹配对象时结果为假，并显示 **No matches**；forall 在空范围上为真，同时显示空范围说明。对象配对时可使用嵌套绑定，并以 `(not (equal ?x ?y))` 排除对象自身。

<a id="_7"></a>

## 6. 数值阈值与不可用检测

<figure class="doc-figure" markdown="1">

[![读取实时检测结果](images/safety-live-results.png){ loading=lazy width="1120" height="760" }](images/safety-live-results.png)

<figcaption markdown="span">**读取实时检测结果.** Live results 显示各规则的状态、累计进度和诊断详情。Export events 用于导出激活事件记录。</figcaption>
</figure>

| 表达式 | 单位与比较 |
| --- | --- |
| `(checkdistance object_a object_b 0.05)` | 表面距离 ≤ 0.05 米。 |
| `(checkgripperdistance object 0.05)` | 夹爪距离 ≤ 0.05 米。 |
| `(checkforce object 20)` | 接触力总量 > 20 牛顿。 |
| `(checkforce object_a object_b 20)` | 两物体之间接触力 > 20 牛顿。 |
| `(checkarmforce robot 20)` | 机械臂接触力 > 20 牛顿。 |

`robot` 是机械臂全局检查的占位参数。距离规则必须显式填写阈值。对象缺失、不支持的对象方法和谓词执行错误会显示 **Unknown**；not 不会把未知结果变成真。每个采样的表达式与谓词求值预算为 4096，过宽的嵌套选择器可能触发预算诊断。

规则初始为真时会记录一次触发；持续为真不会重复触发，出现已知假值后再次为真可以生成新事件。**active rules** 表示当前活动规则数，**recorded events** 表示触发历史。零事件不能说明所有配置检查都可用。

<a id="_8"></a>

## 7. 扩展与迁移

监控复用仿真器已注册的谓词。添加自定义谓词时，在 `libero/libero/envs/predicates/` 中实现并注册，再向 `gui_modules/safety/catalog.py` 添加参数契约和解释。特殊数值比较或环境级调用需要相应求值适配；普通对象谓词可以直接复用注册函数。

监控不替代 BDDL 任务目标和 `cost_state`，也不会自动停止运行或规划纠正动作。AI 导出的 `safety_events.json` 包含活动规则、结果和事件。

旧配置曾将最外层 And 当作独立规则容器，并在部分嵌套 And 中组合不同时刻的条件。现在所有 and 都表示同一采样内同时成立。需要独立告警时，请将子条件直接放在 `:safety_rules` 下。
