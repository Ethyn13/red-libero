# 环境安装

使用独立的 Conda 环境安装 **Red-LIBERO**。模型推理使用各自的环境；编辑场景时无需加载模型权重。

<h2 id="contents">目录</h2>

1. [系统要求](#_2)
2. [创建 GUI 环境](#gui)
3. [安装策略客户端](#_3)
4. [检查并启动](#_4)
5. [资源路径](#_5)

---

<a id="_2"></a>

## 1. 系统要求

本文配置面向 Linux x86_64。Tk 窗口需要 X11 桌面、X11 转发或远程桌面。OSMesa 使用 CPU 渲染仿真图像，EGL 使用已配置的 GPU；两者都不能代替 GUI 所需的显示服务。

Ubuntu / Debian 系统依赖：

```bash
sudo apt-get update
sudo apt-get install -y \
  libosmesa6 libgl1 libegl1 libglib2.0-0 \
  libxrender1 libxext6 libxft2 fontconfig fonts-dejavu-core
```

从[项目仓库](https://github.com/Ethyn13/Red-LIBERO)或项目发布包获取源码。以下命令均在包含 `editor_gui.py` 和 `environment.yml` 的目录执行。请保留随源码提供的 `libero/libero/assets/` 资产目录。

```bash
git clone https://github.com/Ethyn13/Red-LIBERO.git
cd Red-LIBERO
```

<a id="gui"></a>

## 2. 创建 GUI 环境

```bash
conda env create -f environment.yml
conda activate red-libero

python -m pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements/studio.txt
python -m pip install --no-deps -e .
python -m pip check
```

| 组件 | GUI 环境版本 |
| --- | --- |
| Python | 3.10 |
| NumPy | **1.26.4** |
| robosuite | **1.5.1** |
| MuJoCo | 3.3.7 |
| 用于状态读写的 PyTorch | 2.5.1，CPU 版本 |

完整版本锁定见 [requirements/studio.txt](downloads/requirements/studio.txt)，解释器与 Tk 配置见 [environment.yml](downloads/environment.yml)。安装后的发行包名称为 `Red-LIBERO`，公开导入入口为 `red_libero`。为兼容已有 VLA 客户端和 BDDL 标识符，保留 `libero.libero` 命名空间。

<a id="_3"></a>

## 3. 安装策略客户端

要使用 **AI policy**，先从[项目主页](https://redvla.github.io)获取配套 RedVLA 源码，再安装基础客户端：

```bash
conda activate red-libero
python -m pip install -c requirements/studio.txt -e /path/to/redvla
python -m pip check
```

OpenVLA / VLA-Adapter 的模型依赖，以及 OpenPI 的 JAX 依赖，应分别安装到模型环境。服务启动方式见[模型启动示例](models.md)。

<a id="_4"></a>

## 4. 检查并启动

```bash
python -c "import numpy, robosuite; print(numpy.__version__, robosuite.__version__)"
bash gui_start.sh
```

输出版本应为 `1.26.4` 与 `1.5.1`。启动器默认打开一个将碗放到盘子上的任务。下一步阅读[第一个场景](quickstart.md)。

<a id="_5"></a>

## 5. 资源路径

| 配置项 / 目录 | 作用 |
| --- | --- |
| `RED_LIBERO_PYTHON` | 指定启动 GUI 的 Python 解释器。 |
| `RED_LIBERO_CONFIG_PATH` | 覆盖仿真资源配置目录。 |
| `.gui-runtime/red-libero-config/` | 启动器为当前源码创建的资源配置。 |
| `.red-libero/workspace/` | 当前场景和重置基准文件，相对于启动目录。 |
| `.red-libero/safety_rules.bddl` | 已应用的安全规则，位于工作区旁。 |

直接导入 Python 包时，默认使用 `~/.config/red-libero/<checkout-id>/config.yaml`，并支持 `XDG_CONFIG_HOME`。旧变量 `LIBERO_CONFIG_PATH` 保留为兼容回退项。初始化资源路径时不会要求交互式输入。
