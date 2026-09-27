# Remote access

Scene Studio is a Linux desktop application. Run it on a local desktop, over configured X11 forwarding, or in a VNC / noVNC desktop. The GUI launcher does not provision the remote desktop itself.

<h2 id="contents">Table of Contents</h2>

1. [Forward an existing noVNC desktop](#forward-an-existing-novnc-desktop)
2. [X11 forwarding](#x11-forwarding)
3. [Model on a different host](#model-on-a-different-host)
4. [Preview these docs remotely](#preview-these-docs-remotely)

---

<a id="forward-an-existing-novnc-desktop"></a>

## 1. Forward an existing noVNC desktop

If your server already provides noVNC on loopback port 6085:

```bash
ssh -N -L 6085:127.0.0.1:6085 user@gui-host
```

Open `http://127.0.0.1:6085/vnc.html?autoconnect=true&resize=scale` locally. Start the editor inside that desktop's authenticated display session. Its `DISPLAY` and `XAUTHORITY` must match the desktop; setting `DISPLAY` alone does not create a session.

The example port is configurable. VNC, noVNC, the window manager, and SSH forwarding are infrastructure separate from the editor process. Restarting only the editor can retain the desktop connection.

<a id="x11-forwarding"></a>

## 2. X11 forwarding

```bash
ssh -X user@gui-host
conda activate red-libero
cd /path/to/Red-LIBERO
bash gui_start.sh
```

Your client needs an X server, and SSH forwarding must be enabled on the host. OSMesa and EGL are rendering backends, not window-display servers.

<a id="model-on-a-different-host"></a>

## 3. Model on a different host

Create this tunnel from the **machine running the GUI**:

```bash
ssh -N -L 8002:127.0.0.1:8002 user@model-host
```

Use `http://127.0.0.1:8002` in the GUI profile. Omit `launch` and use **Check connection** for an externally managed server. Managed launch starts a process on the GUI host; it does not execute commands on another host over SSH.

For authentication, use `REDVLA_API_TOKEN` for RedVLA HTTP or `OPENPI_API_KEY` for OpenPI in the GUI environment. Keep machine-specific paths and credentials out of shared YAML templates.

<a id="preview-these-docs-remotely"></a>

## 4. Preview these docs remotely

In the documentation environment, run `python -m mkdocs serve -a 127.0.0.1:8765`. Forward that port:

```bash
ssh -N -L 8765:127.0.0.1:8765 user@gui-host
```

Then visit `http://127.0.0.1:8765/`. See [documentation maintenance](documentation.md) for the separate build environment.
