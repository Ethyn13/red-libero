"""Run policy transport in a worker and simulator operations on the GUI thread."""

from collections import deque
import logging
from queue import Empty, Queue
import threading
import time

import numpy as np

from gui_modules.policy import client
from gui_modules.policy.profiles import PolicyProfile, load_profiles
from gui_modules.scene_state import capture_state, restore_state

logger = logging.getLogger(__name__)


class AIController:
    def __init__(self, editor_instance, vla_model_path=None, preload_vla=False):
        self.editor = editor_instance
        self.profile = None
        self.error = ""
        if vla_model_path:
            try:
                self.profile = vla_model_path if isinstance(vla_model_path, PolicyProfile) else load_profiles(vla_model_path)[0]
            except Exception as error:
                self.error = f"Invalid policy profile: {error}"
        self.is_active = self.is_paused = self.is_running = False
        self.is_executing = self.execution_done = self.is_playing = False
        self.play_index, self.play_speed = 0, 1
        self.inference_count, self.total_inference_time = 0, 0.0
        self.action_history, self.trajectory_cache = [], []
        self.action_queue = deque()
        self.current_task_instruction = ""
        self.safety_monitor = None
        self.rlds_exporter = self.rlds_collector = None
        self.inference_thread = None
        self.status = "Ready to connect" if self.profile else "Choose a policy profile"
        self._cancel = threading.Event()
        self._requests, self._results = Queue(), Queue()
        self._initial = None
        self._waiting = self._connected = False
        self._steps = self._settled = 0

    def _log(self, text, error=False):
        studio = getattr(self.editor, "studio", None)
        if studio:
            studio.log(text, error=error)
        else:
            logger.log(logging.ERROR if error else logging.INFO, text)

    def enter_ai_mode(self, task_instruction=None):
        if not self.profile:
            self._log(self.error or "Choose a policy profile before entering AI policy.", error=True)
            return False
        if self.is_active:
            return True
        self.current_task_instruction = task_instruction or self.editor.get_current_instruction()
        if not self.current_task_instruction.strip():
            self._log("Define a task instruction before entering AI policy.", error=True)
            return False
        self.is_active = True
        self.is_executing = self.is_running = False
        self.is_paused = self.execution_done = self.is_playing = False
        self._initial = None
        self.safety_monitor = getattr(self.editor, "physics_safety_monitor", None)
        self.status = "Ready - click Start run"
        self.error = ""
        self._steps = self._settled = 0
        self.inference_count, self.total_inference_time = 0, 0.0
        self.action_history, self.trajectory_cache = [], []
        self.action_queue.clear()
        self.rlds_exporter = self.rlds_collector = None
        return True

    def start_run(self, task_instruction=None):
        if not self.is_active or self.is_executing or self.execution_done:
            return False
        if self.inference_thread and self.inference_thread.is_alive():
            self._log("The previous request is still closing. Wait for its network timeout before restarting.", error=True)
            return False
        self.current_task_instruction = task_instruction or self.editor.get_current_instruction()
        if not self.current_task_instruction.strip():
            self._log("Define a task instruction before entering AI policy.", error=True)
            return False
        self._initial = capture_state(self.editor.env.sim)
        self.editor.reset_task_monitoring()
        self.safety_monitor = getattr(self.editor, "physics_safety_monitor", None)
        if self.safety_monitor:
            self.safety_monitor.reset()
            self.safety_monitor.reload_config()
        self._cancel = threading.Event()
        self._requests, self._results = Queue(), Queue()
        self.action_queue.clear()
        self.action_history, self.trajectory_cache = [], []
        self.inference_count, self.total_inference_time = 0, 0.0
        self._steps = self._settled = 0
        self._waiting = self._connected = False
        self.error = ""
        self.is_active = self.is_executing = self.is_running = True
        self.is_paused = self.execution_done = self.is_playing = False
        self.status = "Connecting to policy service..."
        self.rlds_exporter = self.rlds_collector = None
        try:
            from gui_modules.rlds_exporter import RLDSExporter, RLDSDataCollector
            self.rlds_exporter = RLDSExporter()
            self.rlds_collector = RLDSDataCollector(self.rlds_exporter)
            self.rlds_collector.start_collection(self.editor.env, self.current_task_instruction,
                self.editor.editor.parsed_dict.get("problem_name", "libero"), str(self.editor.current_bddl))
        except Exception as error:
            self.rlds_collector = None
            self._log(f"Trajectory export unavailable: {error}", error=True)
        self.inference_thread = threading.Thread(target=self._worker, daemon=True, name="policy-transport")
        self.inference_thread.start()
        return True

    def _worker(self):
        policy = None
        try:
            policy = client.connect(self.profile)
            if self._cancel.is_set():
                return
            policy.prepare_for_new_episode()
            self._results.put(("ready", None))
            while not self._cancel.is_set():
                try:
                    request = self._requests.get(timeout=.1)
                except Empty:
                    continue
                if request is None or self._cancel.is_set():
                    break
                obs, step = request
                policy.set_inference_context(seed=self.profile.run["seed"], step=step)
                started = time.monotonic()
                values = client.actions(policy.predict(obs, self.current_task_instruction))
                self._results.put(("actions", (values, time.monotonic() - started)))
        except Exception as error:
            self._results.put(("error", str(error)))
        finally:
            if policy is not None:
                try:
                    policy.close()
                except Exception:
                    logger.exception("Could not close the policy session")

    def tick(self):
        if not self.is_active:
            return
        if self.execution_done:
            if self.is_playing and not self.is_paused:
                self.play_next_frame()
            return
        if not self.is_executing:
            return
        try:
            while True:
                try:
                    kind, result = self._results.get_nowait()
                except Empty:
                    break
                if kind == "error":
                    self._finish(f"Policy error: {result}", error=True)
                    return
                if kind == "ready":
                    self._connected = True
                elif kind == "actions":
                    values, elapsed = result
                    self.action_queue.extend(values)
                    self.total_inference_time += elapsed
                    self.inference_count += 1
                    self._waiting = False
            if self.is_paused or not self._connected:
                return
            if self._steps >= self.profile.run["max_steps"]:
                self._finish("Step budget reached")
                return
            if self._settled < self.profile.run["settle_steps"]:
                self._settled += 1
                self.status = f"Settling scene {self._settled}/{self.profile.run['settle_steps']}"
                self._step(np.array([0., 0., 0., 0., 0., 0., -1.]))
            elif self.action_queue:
                self.status = f"Executing {self._steps + 1}/{self.profile.run['max_steps']}"
                self._step(self.action_queue.popleft())
            elif not self._waiting:
                obs, _ = client.observation(self.editor)
                self._requests.put((obs, self._steps))
                self._waiting = True
                self.status = "Waiting for model inference..."
        except Exception as error:
            self._finish(f"Execution error: {error}", error=True)

    def _step(self, action):
        _, raw = client.observation(self.editor)
        before = self.editor.env.sim.get_state().flatten().copy() if self.rlds_collector else None
        _, reward, done, _ = self.editor.step_environment(action)
        self._steps += 1
        self.action_history.append(np.array(action, copy=True))
        sim = self.editor.env.sim
        self.trajectory_cache.append({"qpos": sim.data.qpos.copy(), "qvel": sim.data.qvel.copy(), "time": float(sim.data.time)})
        if self.safety_monitor:
            self.safety_monitor.check_step(self._steps)
        if self.rlds_collector:
            self.rlds_collector.collect_step(self.editor.env, raw, action, reward, done, state=before)
        for field, camera in (("ai_video_frames", "agentview"), ("ai_video_wrist_frames", "robot0_eye_in_hand")):
            frames = getattr(self.editor, field, None)
            if frames is not None:
                frames.append(raw[camera + "_image"][::-1].copy())
        if self.editor.task_success:
            self._finish("Task complete")
        elif done:
            self._finish("Environment episode ended")
        elif self._steps >= self.profile.run["max_steps"]:
            self._finish("Step budget reached")

    def _finish(self, status, error=False):
        self.status = status
        self.error = status if error else ""
        self.is_executing = self.is_running = False
        self.execution_done = True
        self._cancel.set()
        self._requests.put(None)
        self.action_queue.clear()
        if self.rlds_collector:
            self.rlds_collector.end_collection(success=bool(self.editor.task_success))
        self._log(status, error=error)

    def exit_ai_mode(self, reset_robot=True):
        self._cancel.set()
        self._requests.put(None)
        if self.is_executing:
            self._finish("Stopped")
        self.is_active = self.is_playing = self.is_paused = False
        if reset_robot and self._initial is not None:
            restore_state(self.editor.env.sim, self._initial)
            self.editor.reset_task_monitoring()
            self._initial = None

    def play_next_frame(self):
        if not self.execution_done or not self.is_playing:
            return False
        if self.play_index >= len(self.trajectory_cache):
            self.is_playing = False
            return False
        state = self.trajectory_cache[self.play_index]
        sim = self.editor.env.sim
        sim.data.qpos[:] = state["qpos"]
        sim.data.qvel[:] = state["qvel"]
        sim.data.time = state["time"]
        sim.forward()
        self.play_index += 1
        return True

    def replay(self):
        if self.execution_done and self.trajectory_cache:
            self.play_index = 0
            self.is_playing, self.is_paused = True, False

    def toggle_pause(self):
        if self.is_active and (self.is_executing or self.is_playing):
            self.is_paused = not self.is_paused

    def get_status_text(self):
        return "Paused" if self.is_paused else "Replaying trajectory" if self.is_playing else self.status

    def cleanup(self):
        self.exit_ai_mode(reset_robot=False)
