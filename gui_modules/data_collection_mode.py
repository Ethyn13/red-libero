"""Collect demonstrations from keyboard-driven robot control."""

import datetime
import logging
import time
from pathlib import Path
from typing import Any, Dict

import numpy as np

logger = logging.getLogger(__name__)


class DataCollectionController:
    def __init__(self, editor_instance):
        self.editor = editor_instance
        self.is_collecting = False
        self.collection_data = {
            "states": [],
            "actions": [],
            "observations": [],
            "timestamps": [],
            "costs": [],
            "rewards": [],
        }
        self.start_time = None
        self.step_count = 0
        self.cumulative_cost = 0
        self.task_completion_hold_count = -1
        self.collection_dir = Path("demonstration_data")
        self.current_episode_dir = None
        self.cost_list = []
        self.step_list = []
        self.keyboard_device = None
        self._init_keyboard_device()

    def _init_keyboard_device(self):
        self.pressed_keys = set()
        self.gripper_state = -1

    def start_collection(self) -> bool:
        try:
            if (
                hasattr(self.editor, "physics_safety_monitor")
                and self.editor.physics_safety_monitor
            ):
                self.editor.physics_safety_monitor.reset()
                self.editor.physics_safety_monitor.reload_config()
            self.is_collecting = True
            self.start_time = time.time()
            self.step_count = 0
            self.cumulative_cost = 0
            self.task_completion_hold_count = -1
            self.collection_data = {
                "states": [],
                "actions": [],
                "observations": [],
                "timestamps": [],
                "costs": [],
                "rewards": [],
            }
            self.cost_list = []
            self.step_list = []
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            episode_name = f"episode_{timestamp}"
            self.current_episode_dir = self.collection_dir / episode_name
            self.current_episode_dir.mkdir(parents=True, exist_ok=True)
            self._save_state_snapshot()
            model_xml = self.editor.env.sim.model.get_xml()
            with open(self.current_episode_dir / "model.xml", "w") as f:
                f.write(model_xml)
            self.gripper_state = -1
            logger.debug(f"  📂 Episode directory: {self.current_episode_dir}")
            logger.debug(
                f"  💡 Current task: {self.editor.get_current_task_instruction()}"
            )
            return True
        except Exception as e:
            logger.warning(f"❌ Failed to start data collection: {e}")
            import traceback

            traceback.print_exc()
            return False

    def handle_numpad_input(self, key: str, event=None) -> bool:
        if not self.is_collecting:
            return True
        from gui_modules.event_handlers import KeyboardHandler

        (base_key, is_mirrored) = KeyboardHandler.mirror_numpad_key(
            key, event, self.editor
        )
        mirror_factor = -1 if is_mirrored else 1
        base_pos_step = 0.5
        base_rot_step = 0.5
        pos_sensitivity = 1.5
        rot_sensitivity = 1.5
        pos_step = base_pos_step * pos_sensitivity
        rot_step = base_rot_step * rot_sensitivity
        action = np.zeros(7)
        action[6] = self.gripper_state
        if base_key == "8":
            action[0] = -pos_step * mirror_factor
        elif base_key == "2":
            action[0] = pos_step * mirror_factor
        elif base_key == "4":
            action[1] = pos_step * mirror_factor
        elif base_key == "6":
            action[1] = -pos_step * mirror_factor
        elif base_key == "5":
            action[2] = pos_step * mirror_factor
        elif base_key == "0":
            action[2] = -pos_step * mirror_factor
        elif base_key == "7":
            action[5] = rot_step * mirror_factor
        elif base_key == "9":
            action[5] = -rot_step * mirror_factor
        elif base_key == "1":
            action[4] = rot_step * mirror_factor
        elif base_key == "3":
            action[4] = -rot_step * mirror_factor
        elif base_key == "*":
            action[3] = rot_step * mirror_factor
        elif base_key == "/":
            action[3] = -rot_step * mirror_factor
        elif key == "enter":
            self.gripper_state = -self.gripper_state
            action[6] = self.gripper_state
            logger.debug(f"Gripper toggled to: {self.gripper_state}")
        elif key == "-":
            action[6] = self.gripper_state
            logger.debug(f"Gripper hold: {self.gripper_state}")
        elif key == "+":
            action[6] = 0
        else:
            return True
        try:
            self.collect_step(action)
            if self.step_count % 10 == 0:
                logger.debug(
                    f"📊 Collected {self.step_count} steps | Cost: {self.cumulative_cost:.2f}"
                )
        except Exception as e:
            logger.warning(f"⚠️ Action execution failed: {e}")
            import traceback

            traceback.print_exc()
        return True

    def collect_step(self, action: np.ndarray) -> bool:
        if not self.is_collecting:
            return False
        try:
            current_state = self.editor.env.sim.get_state().flatten()
            obs = self._get_observation()
            (obs_next, reward, done, info) = self.editor.env.step(action)
            self.collection_data["states"].append(current_state)
            self.collection_data["actions"].append(action.copy())
            self.collection_data["observations"].append(obs)
            self.collection_data["timestamps"].append(time.time() - self.start_time)
            self.collection_data["rewards"].append(reward)
            cost = 0
            if (
                hasattr(self.editor, "physics_safety_monitor")
                and self.editor.physics_safety_monitor
            ):
                safety_events = self.editor.physics_safety_monitor.check_step(
                    self.step_count
                )
                logger.debug(f"Collect step: step_count={self.step_count}")
                logger.debug(f"Collect step: len(safety_events)={len(safety_events)}")
                if safety_events:
                    cost = len(safety_events)
                    self.cumulative_cost += cost
                    logger.debug(f"Collect step: cost={cost}")
                    logger.debug(
                        f"Collect step: cumulative_cost={self.cumulative_cost}"
                    )
                else:
                    logger.debug(
                        f"Collect step: cumulative_cost={self.cumulative_cost}"
                    )
            self.collection_data["costs"].append(cost)
            self.cost_list.append(self.cumulative_cost)
            self.step_list.append(self.step_count)
            self.step_count += 1
            try:
                if (
                    hasattr(self.editor.env, "_check_success")
                    and self.editor.env._check_success()
                ):
                    if self.task_completion_hold_count > 0:
                        self.task_completion_hold_count -= 1
                    else:
                        self.task_completion_hold_count = 10
                else:
                    self.task_completion_hold_count = -1
                if self.task_completion_hold_count == 0:
                    return self.stop_collection(success=True)
            except:
                pass
            return True
        except Exception as e:
            logger.warning(f"❌ Collection step failed: {e}")
            import traceback

            traceback.print_exc()
            return False

    def stop_collection(self, success: bool = True) -> bool:
        if not self.is_collecting:
            return False
        try:
            self.is_collecting = False
            logger.debug(f"  📊 Steps executed: {self.step_count}")
            logger.debug(f"  💰 Cumulative cost: {self.cumulative_cost:.2f}")
            if self.current_episode_dir and self.current_episode_dir.exists():
                import shutil

                try:
                    shutil.rmtree(self.current_episode_dir)
                except:
                    pass
            return True
        except Exception as e:
            logger.warning(f"❌ Failed to stop collection: {e}")
            import traceback

            traceback.print_exc()
            return False

    def _get_observation(self) -> Dict[str, Any]:
        obs = {}
        if (
            hasattr(self.editor, "cached_image")
            and self.editor.cached_image is not None
        ):
            obs["agentview_image"] = self.editor.cached_image.copy()
        if (
            hasattr(self.editor, "cached_wrist_image")
            and self.editor.cached_wrist_image is not None
        ):
            obs["robot0_eye_in_hand_image"] = self.editor.cached_wrist_image.copy()
        try:
            if hasattr(self.editor.env, "robots") and len(self.editor.env.robots) > 0:
                obs["robot0_joint_pos"] = self.editor.env.sim.data.qpos[:7].copy()
                obs["robot0_joint_vel"] = self.editor.env.sim.data.qvel[:7].copy()
                obs["robot0_gripper_qpos"] = self.editor.env.sim.data.qpos[7:9].copy()
        except Exception:
            pass
        return obs

    def _save_state_snapshot(self):
        state = self.editor.env.sim.get_state().flatten()
        state_file = self.current_episode_dir / f"state_{self.step_count}.npz"
        env_name = "unknown"
        if hasattr(self.editor, "bddl_file"):
            env_name = Path(self.editor.bddl_file).stem
        elif hasattr(self.editor, "env") and hasattr(self.editor.env, "name"):
            env_name = self.editor.env.name
        np.savez(state_file, states=[state], actions=[], env=env_name)

    def cancel_collection(self):
        if not self.is_collecting:
            return
        self.is_collecting = False
        if self.current_episode_dir and self.current_episode_dir.exists():
            import shutil

            try:
                shutil.rmtree(self.current_episode_dir)
                logger.debug(
                    f"  🗑️  Deleted temporary directory: {self.current_episode_dir}"
                )
            except:
                pass

    def get_status_text(self) -> str:
        if not self.is_collecting:
            return "Not Collecting"
        return f"Steps:{self.step_count} | Cost:{self.cumulative_cost:.1f}"

    def end_collection(self, save_data: bool = True) -> bool:
        return self.stop_collection(success=save_data)
