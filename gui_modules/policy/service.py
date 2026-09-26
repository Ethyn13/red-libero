"""Launch and inspect model services without loading model stacks into Tk."""

from __future__ import annotations

import atexit
from datetime import datetime
import os
from pathlib import Path
from queue import Empty, Queue
import signal
import socket
import subprocess
import threading
import time
from urllib.parse import urlparse

from gui_modules.policy.client import probe
from gui_modules.policy.profiles import ROOT, expand


def launch_spec(profile):
    settings = profile.launch
    if not settings["command"]:
        raise ValueError("Configure a launch command, or connect to an existing service")
    endpoint = urlparse(profile.model["path"])
    if endpoint.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Managed launch requires a local endpoint; start remote services on their host and use Check connection")
    python = Path(expand(settings["python"])).resolve()
    cwd = Path(expand(settings["cwd"])).resolve()
    if not settings["python"] or not python.is_file():
        raise ValueError("Choose the Python executable inside the model's Conda environment")
    if not settings["cwd"] or not cwd.is_dir():
        raise ValueError("Choose an existing service working directory")
    command = [expand(arg.replace("{python}", str(python))) for arg in settings["command"]]
    env = dict(os.environ)
    for key in ("LD_PRELOAD", "PYTHONHOME", "PYTHONPATH", "TCL_LIBRARY", "TK_LIBRARY"):
        env.pop(key, None)
    env["PATH"] = str(python.parent) + os.pathsep + env.get("PATH", "")
    env["CONDA_PREFIX"] = str(python.parent.parent)
    env["PYTHONUNBUFFERED"] = "1"
    env.update({key: expand(value) for key, value in settings["env"].items()})
    return command, cwd, env


def terminate(process):
    if process is None or process.poll() is not None:
        return
    if os.name == "posix":
        os.killpg(process.pid, signal.SIGTERM)
    else:
        process.terminate()
    try:
        process.wait(timeout=4)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait(timeout=4)


class ServiceManager:
    def __init__(self, log_dir=None):
        self.log_dir = Path(log_dir or ROOT / ".gui-runtime" / "policy-services")
        self.process = None
        self.process_key = None
        self.log_path = None
        self.status = "Not checked"
        self.profile_key = None
        self.metadata = None
        self.busy = False
        self.ready = False
        self._generation = 0
        self._cancel = threading.Event()
        self._results = Queue()
        self._lock = threading.Lock()
        self._closed = False
        atexit.register(self.shutdown)

    def _job(self, profile, label, operation):
        if self._closed:
            raise RuntimeError("Service manager has closed")
        self._cancel.set()
        self._cancel = threading.Event()
        self._generation += 1
        generation, cancel = self._generation, self._cancel
        self.profile_key = profile.key
        self.status, self.busy, self.ready = label, True, False

        def run():
            try:
                result = operation(cancel)
                self._results.put((generation, result, None))
            except Exception as error:
                self._results.put((generation, None, str(error)))
        threading.Thread(target=run, daemon=True).start()

    def check(self, profile):
        if self.busy:
            raise RuntimeError("Wait for the current service operation, or stop the service")
        self._job(profile, "Checking connection...", lambda cancel: probe(profile))

    def start(self, profile):
        if self.busy:
            raise RuntimeError("A service operation is already in progress")
        if self.process is not None and self.process.poll() is None:
            raise RuntimeError("Stop the service started by this GUI before launching another")
        command, cwd, env = launch_spec(profile)

        def launch(cancel):
            endpoint = urlparse(profile.model["path"])
            port = endpoint.port or (443 if endpoint.scheme in ("https", "wss") else 80)
            try:
                with socket.create_connection((endpoint.hostname, port), timeout=1):
                    raise RuntimeError("The endpoint port is already occupied; use Check connection or choose another port")
            except OSError:
                pass
            self.log_dir.mkdir(parents=True, exist_ok=True)
            path = self.log_dir / f"service-{datetime.now():%Y%m%d-%H%M%S-%f}.log"
            with self._lock:
                if cancel.is_set() or self._closed:
                    raise RuntimeError("Service startup cancelled")
                with path.open("wb") as log:
                    options = {"start_new_session": True} if os.name == "posix" else {"creationflags": subprocess.CREATE_NO_WINDOW}
                    process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, **options)
                self.process, self.process_key, self.log_path = process, profile.key, path
            deadline = time.monotonic() + profile.launch["startup_timeout"]
            last_error = "Service has not responded"
            try:
                while not cancel.is_set():
                    if process.poll() is not None:
                        raise RuntimeError(f"Service exited with code {process.returncode}. See the service log.")
                    try:
                        return probe(profile)
                    except Exception as error:
                        last_error = str(error)
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"Service startup timed out: {last_error}")
                    cancel.wait(.5)
                raise RuntimeError("Service startup cancelled")
            except BaseException:
                terminate(process)
                raise
        self._job(profile, "Starting service...", launch)

    def stop(self, profile):
        def stop_owned(cancel):
            with self._lock:
                process = self.process
            terminate(process)
            return {"stopped": True}
        self._job(profile, "Stopping owned service...", stop_owned)

    def poll(self):
        messages = []
        while True:
            try:
                generation, result, error = self._results.get_nowait()
            except Empty:
                break
            if generation != self._generation:
                continue
            self.busy = False
            self.metadata = result
            self.ready = error is None and not result.get("stopped", False)
            self.status = f"Connection failed: {error}" if error else "Ready" if self.ready else "Stopped"
            messages.append((self.status, error is not None))
        if not self.busy and self.ready and self.process_key == self.profile_key and self.process is not None and self.process.poll() is not None:
            self.ready = False
            self.status = f"Service exited with code {self.process.returncode}"
            messages.append((self.status, True))
        return messages

    def log_tail(self, limit=16000):
        if self.log_path is None or not self.log_path.is_file():
            return "No service has been launched by this GUI. External service logs remain on their host."
        with self.log_path.open("rb") as stream:
            stream.seek(max(0, self.log_path.stat().st_size - limit))
            return stream.read().decode("utf-8", errors="replace")

    def shutdown(self):
        self._cancel.set()
        with self._lock:
            self._closed = True
            process = self.process
        try:
            terminate(process)
        except (OSError, subprocess.SubprocessError):
            pass
