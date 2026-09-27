# 远程访问

Scene Studio 是 Linux 桌面程序，可以在本地桌面、已配置的 X11 转发，或 VNC / noVNC 桌面中运行。GUI 启动器本身不会部署远程桌面服务。

<h2 id="contents">目录</h2>

1. [转发现有 noVNC 桌面](#novnc)
2. [X11 转发](#x11)
3. [模型运行在另一台主机](#_2)
4. [远程预览本文档](#_3)

---

<a id="novnc"></a>

## 1. 转发现有 noVNC 桌面

如果服务器已有监听回环地址 6085 端口的 noVNC 服务：

```bash
ssh -N -L 6085:127.0.0.1:6085 user@gui-host
```

在本地打开 `http://127.0.0.1:6085/vnc.html?autoconnect=true&resize=scale`。编辑器必须在该桌面的已认证显示会话中启动，`DISPLAY` 和 `XAUTHORITY` 需要与桌面匹配；只设置 `DISPLAY` 不会创建显示会话。

端口可以按实际配置调整。VNC、noVNC、窗口管理器和 SSH 转发是独立于编辑器的基础设施，只重启编辑器可以保留桌面连接。

<a id="x11"></a>

## 2. X11 转发

```bash
ssh -X user@gui-host
conda activate red-libero
cd /path/to/Red-LIBERO
bash gui_start.sh
```

本机需要 X Server，服务器需要启用 SSH X11 转发。OSMesa 和 EGL 是渲染后端，不是窗口显示服务。

<a id="_2"></a>

## 3. 模型运行在另一台主机

从**运行 GUI 的主机**建立隧道：

```bash
ssh -N -L 8002:127.0.0.1:8002 user@model-host
```

GUI 配置填写 `http://127.0.0.1:8002`。外部管理的服务省略 `launch`，使用 **Check connection** 连接。托管启动只会在 GUI 所在主机创建进程，不会通过 SSH 在其他机器执行命令。

启用认证时，在 GUI 环境中分别设置 RedVLA HTTP 的 `REDVLA_API_TOKEN` 或 OpenPI 的 `OPENPI_API_KEY`。本机路径和凭据不应写入公开 YAML 模板。

<a id="_3"></a>

## 4. 远程预览本文档

在文档环境中执行 `python -m mkdocs serve -a 127.0.0.1:8765`，然后转发端口：

```bash
ssh -N -L 8765:127.0.0.1:8765 user@gui-host
```

在本地访问 `http://127.0.0.1:8765/`。独立文档构建环境的配置见[文档站维护](documentation.md)。
