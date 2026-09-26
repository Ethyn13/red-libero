"""Write policy episodes and safety annotations in RLDS-compatible form."""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import h5py
import numpy as np
import robosuite.utils.transform_utils as T

logger = logging.getLogger(__name__)


class RLDSExporter:
    def __init__(self, output_dir: Optional[str] = None):
        if output_dir is None:
            current_file = Path(__file__).resolve()
            project_root = current_file.parent.parent
            output_dir = os.path.join(project_root, "datasets", "rlds")
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.episode_data = []
        self.current_episode = None

    def start_episode(
        self,
        task_instruction: str,
        problem_name: str,
        bddl_file_name: str,
        env_info: Dict[str, Any],
        model_xml: str,
        init_state: np.ndarray,
    ):
        self.current_episode = {
            "task_instruction": task_instruction,
            "problem_name": problem_name,
            "bddl_file_name": bddl_file_name,
            "env_info": env_info,
            "model_xml": model_xml,
            "init_state": init_state,
            "observations": [],
            "actions": [],
            "states": [],
            "robot_states": [],
            "rewards": [],
            "dones": [],
            "timestamps": [],
        }
        logger.debug(f"Start episode: problem_name={problem_name}")

    def add_step(
        self,
        observation: Dict[str, np.ndarray],
        action: np.ndarray,
        state: np.ndarray,
        robot_state: np.ndarray,
        reward: float = 0.0,
        done: bool = False,
    ):
        if self.current_episode is None:
            raise ValueError("Call start_episode() first.")
        self.current_episode["observations"].append(observation)
        self.current_episode["actions"].append(action)
        self.current_episode["states"].append(state)
        self.current_episode["robot_states"].append(robot_state)
        self.current_episode["rewards"].append(reward)
        self.current_episode["dones"].append(done)
        self.current_episode["timestamps"].append(datetime.now().timestamp())

    def end_episode(self, success: bool = False):
        if self.current_episode is None:
            return
        if len(self.current_episode["dones"]) > 0:
            self.current_episode["dones"][-1] = 1
            if success:
                self.current_episode["rewards"][-1] = 1.0
        self.current_episode["success"] = success
        num_steps = len(self.current_episode["actions"]) if self.current_episode else 0
        self.episode_data.append(self.current_episode)
        self.current_episode = None
        logger.debug(f"End episode: success={success}, num_steps={num_steps}")

    def save_to_hdf5(
        self,
        filename: Optional[str] = None,
        task_name: Optional[str] = None,
        success: bool = False,
        violation_count: int = 0,
    ) -> str:
        if len(self.episode_data) == 0:
            raise ValueError("No episode data to save.")
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            success_status = "True" if success else "False"
            if task_name:
                clean_task_name = (
                    task_name.replace(" ", "_")
                    .replace("/", "_")
                    .replace("\\", "_")[:50]
                )
                filename = f"{clean_task_name}_{success_status}_{violation_count}_{timestamp}.hdf5"
            else:
                filename = f"{success_status}_{violation_count}_{timestamp}.hdf5"
        output_path = self.output_dir / filename
        logger.debug(f"Save to hdf5: output_path={output_path}")
        with h5py.File(output_path, "w") as f:
            grp = f.create_group("data")
            now = datetime.now()
            grp.attrs["date"] = f"{now.month}-{now.day}-{now.year}"
            grp.attrs["time"] = f"{now.hour}:{now.minute}:{now.second}"
            grp.attrs["num_demos"] = len(self.episode_data)
            first_ep = self.episode_data[0]
            grp.attrs["env"] = first_ep.get("env_info", {}).get("env_name", "libero")
            grp.attrs["env_info"] = json.dumps(first_ep["env_info"])
            grp.attrs["bddl_file_name"] = first_ep["bddl_file_name"]
            grp.attrs["problem_info"] = json.dumps(
                {
                    "problem_name": first_ep["problem_name"],
                    "language_instruction": first_ep["task_instruction"],
                    "domain_name": first_ep.get("env_info", {}).get(
                        "domain_name", "libero"
                    ),
                }
            )
            grp.attrs["macros_image_convention"] = "opengl"
            grp.attrs["tag"] = "libero-v1"
            total_samples = 0
            for i, ep in enumerate(self.episode_data):
                ep_grp = grp.create_group(f"demo_{i}")
                ep_grp.attrs["model_file"] = ep["model_xml"]
                ep_grp.attrs["num_samples"] = len(ep["actions"])
                ep_grp.attrs["init_state"] = ep["init_state"]
                ep_grp.attrs["success"] = ep.get("success", False)
                ep_grp.attrs["task_instruction"] = ep["task_instruction"]
                obs_grp = ep_grp.create_group("obs")
                agentview_images = []
                eye_in_hand_images = []
                gripper_states = []
                joint_states = []
                ee_states = []
                ee_positions = []
                ee_orientations = []
                for obs in ep["observations"]:
                    if "agentview_rgb" in obs:
                        agentview_images.append(obs["agentview_rgb"])
                    if "eye_in_hand_rgb" in obs:
                        eye_in_hand_images.append(obs["eye_in_hand_rgb"])
                    if "gripper_states" in obs:
                        gripper_states.append(obs["gripper_states"])
                    if "joint_states" in obs:
                        joint_states.append(obs["joint_states"])
                    if "ee_states" in obs:
                        ee_states.append(obs["ee_states"])
                    if "ee_pos" in obs:
                        ee_positions.append(obs["ee_pos"])
                    if "ee_ori" in obs:
                        ee_orientations.append(obs["ee_ori"])
                if agentview_images:
                    first_shape = agentview_images[0].shape
                    if first_shape[:2] != (256, 256):
                        logger.debug(f"Save to hdf5: first_shape={first_shape}")
                    obs_grp.create_dataset(
                        "agentview_rgb",
                        data=np.stack(agentview_images, axis=0),
                        dtype=np.uint8,
                    )
                if eye_in_hand_images:
                    first_shape = eye_in_hand_images[0].shape
                    if first_shape[:2] != (256, 256):
                        logger.debug(f"Save to hdf5: first_shape={first_shape}")
                    obs_grp.create_dataset(
                        "eye_in_hand_rgb",
                        data=np.stack(eye_in_hand_images, axis=0),
                        dtype=np.uint8,
                    )
                if gripper_states:
                    obs_grp.create_dataset(
                        "gripper_states", data=np.stack(gripper_states, axis=0)
                    )
                if joint_states:
                    obs_grp.create_dataset(
                        "joint_states", data=np.stack(joint_states, axis=0)
                    )
                if ee_states:
                    ee_states_arr = np.stack(ee_states, axis=0)
                    obs_grp.create_dataset("ee_states", data=ee_states_arr)
                    if ee_states_arr.shape[1] == 6:
                        obs_grp.create_dataset("ee_pos", data=ee_states_arr[:, :3])
                        obs_grp.create_dataset("ee_ori", data=ee_states_arr[:, 3:])
                elif ee_positions and ee_orientations:
                    obs_grp.create_dataset(
                        "ee_pos", data=np.stack(ee_positions, axis=0)
                    )
                    obs_grp.create_dataset(
                        "ee_ori", data=np.stack(ee_orientations, axis=0)
                    )
                ep_grp.create_dataset("actions", data=np.array(ep["actions"]))
                ep_grp.create_dataset("states", data=np.array(ep["states"]))
                ep_grp.create_dataset(
                    "robot_states", data=np.stack(ep["robot_states"], axis=0)
                )
                ep_grp.create_dataset(
                    "rewards", data=np.array(ep["rewards"]).astype(np.uint8)
                )
                ep_grp.create_dataset(
                    "dones", data=np.array(ep["dones"]).astype(np.uint8)
                )
                total_samples += len(ep["actions"])
            grp.attrs["total"] = total_samples
        logger.debug(f"Save to hdf5: output_path={output_path}")
        logger.debug(f"Save to hdf5: len(self.episode_data)={len(self.episode_data)}")
        logger.debug(f"Save to hdf5: total_samples={total_samples}")
        self.episode_data = []
        return str(output_path)

    def save_dataset_info(
        self,
        rlds_path: str,
        safety_events_path: Optional[str] = None,
        video_path: Optional[str] = None,
    ) -> str:
        rlds_file = Path(rlds_path)
        datasets_root = self.output_dir.parent
        dataset_info = {
            "rlds_file": rlds_file.name,
            "rlds_path": str(rlds_file.relative_to(datasets_root))
            if rlds_file.is_relative_to(datasets_root)
            else str(rlds_file),
            "created_at": datetime.now().isoformat(),
            "safety_events": None,
            "video": None,
            "metadata": {},
        }
        if safety_events_path:
            safety_file = Path(safety_events_path)
            dataset_info["safety_events"] = {
                "file": safety_file.name,
                "path": str(safety_file.relative_to(datasets_root))
                if safety_file.is_relative_to(datasets_root)
                else str(safety_file),
            }
            if safety_file.exists():
                try:
                    with open(safety_events_path, "r", encoding="utf-8") as f:
                        safety_data = json.load(f)
                        if isinstance(safety_data, dict) and "summary" in safety_data:
                            dataset_info["safety_events"]["summary"] = safety_data[
                                "summary"
                            ]
                except Exception as e:
                    logger.warning(f"Save dataset info failed: e={e}")
        if video_path:
            video_file = Path(video_path)
            dataset_info["video"] = {
                "file": video_file.name,
                "path": str(video_file.relative_to(datasets_root))
                if video_file.is_relative_to(datasets_root)
                else str(video_file),
            }
        try:
            with h5py.File(rlds_path, "r") as f:
                if "data" in f:
                    grp = f["data"]
                    dataset_info["metadata"] = {
                        "num_demos": int(grp.attrs.get("num_demos", 0)),
                        "total_samples": int(grp.attrs.get("total", 0)),
                        "env": grp.attrs.get("env", "unknown"),
                        "date": grp.attrs.get("date", ""),
                        "time": grp.attrs.get("time", ""),
                    }
        except Exception as e:
            logger.warning(f"Save dataset info failed: e={e}")
        annotation_dir = self.output_dir.parent / "rlds_annotation"
        annotation_dir.mkdir(parents=True, exist_ok=True)
        info_file = annotation_dir / f"{rlds_file.stem}_info.json"
        with open(info_file, "w", encoding="utf-8") as f:
            json.dump(dataset_info, f, indent=2, ensure_ascii=False)
        logger.debug(f"Save dataset info: info_file={info_file}")
        return str(info_file)

    def clear(self):
        self.episode_data = []
        self.current_episode = None


class RLDSDataCollector:
    def __init__(self, exporter: RLDSExporter):
        self.exporter = exporter
        self.is_collecting = False
        self.step_count = 0

    def start_collection(
        self, env, task_instruction: str, problem_name: str, bddl_file_name: str
    ):
        self.is_collecting = True
        self.step_count = 0
        env_info = {
            "env_name": env.name if hasattr(env, "name") else "libero",
            "domain_name": problem_name.split("_")[0]
            if "_" in problem_name
            else "libero",
        }
        model_xml = env.sim.model.get_xml() if hasattr(env, "sim") else ""
        init_state = (
            env.sim.get_state().flatten() if hasattr(env, "sim") else np.array([])
        )
        self.exporter.start_episode(
            task_instruction=task_instruction,
            problem_name=problem_name,
            bddl_file_name=bddl_file_name,
            env_info=env_info,
            model_xml=model_xml,
            init_state=init_state,
        )
        logger.debug(f"Start collection: task_instruction={task_instruction}")

    def collect_step(
        self,
        env,
        observation: Dict[str, Any],
        action: np.ndarray,
        reward: float = 0.0,
        done: bool = False,
        state: Optional[np.ndarray] = None,
    ):
        if not self.is_collecting:
            return
        try:
            obs_dict = {}
            agentview_img = None
            if "agentview_image" in observation:
                agentview_img = observation["agentview_image"]
            elif "agentview_rgb" in observation:
                agentview_img = observation["agentview_rgb"]
            if agentview_img is not None:
                if not isinstance(agentview_img, np.ndarray):
                    agentview_img = np.array(agentview_img)
                if agentview_img.dtype != np.uint8:
                    agentview_img = np.clip(agentview_img, 0, 255).astype(np.uint8)
                if agentview_img.shape[:2] != (256, 256):
                    from PIL import Image

                    agentview_img = np.array(
                        Image.fromarray(agentview_img).resize(
                            (256, 256), Image.Resampling.LANCZOS
                        )
                    )
                if len(agentview_img.shape) == 2:
                    agentview_img = np.stack([agentview_img] * 3, axis=-1)
                elif agentview_img.shape[2] == 4:
                    agentview_img = agentview_img[:, :, :3]
                agentview_img = agentview_img[::-1, :, :]
                obs_dict["agentview_rgb"] = agentview_img
            eye_in_hand_img = None
            if "robot0_eye_in_hand_image" in observation:
                eye_in_hand_img = observation["robot0_eye_in_hand_image"]
            elif "eye_in_hand_rgb" in observation:
                eye_in_hand_img = observation["eye_in_hand_rgb"]
            if eye_in_hand_img is not None:
                if not isinstance(eye_in_hand_img, np.ndarray):
                    eye_in_hand_img = np.array(eye_in_hand_img)
                if eye_in_hand_img.dtype != np.uint8:
                    eye_in_hand_img = np.clip(eye_in_hand_img, 0, 255).astype(np.uint8)
                if eye_in_hand_img.shape[:2] != (256, 256):
                    from PIL import Image

                    eye_in_hand_img = np.array(
                        Image.fromarray(eye_in_hand_img).resize(
                            (256, 256), Image.Resampling.LANCZOS
                        )
                    )
                if len(eye_in_hand_img.shape) == 2:
                    eye_in_hand_img = np.stack([eye_in_hand_img] * 3, axis=-1)
                elif eye_in_hand_img.shape[2] == 4:
                    eye_in_hand_img = eye_in_hand_img[:, :, :3]
                eye_in_hand_img = eye_in_hand_img[::-1, :, :]
                obs_dict["eye_in_hand_rgb"] = eye_in_hand_img
            if "robot0_gripper_qpos" in observation:
                obs_dict["gripper_states"] = observation["robot0_gripper_qpos"]
            if "robot0_joint_pos" in observation:
                obs_dict["joint_states"] = observation["robot0_joint_pos"]
            if "robot0_eef_pos" in observation and "robot0_eef_quat" in observation:
                eef_pos = observation["robot0_eef_pos"]
                eef_quat = observation["robot0_eef_quat"]
                eef_ori = T.quat2axisangle(eef_quat)
                obs_dict["ee_states"] = np.concatenate([eef_pos, eef_ori])
                obs_dict["ee_pos"] = eef_pos
                obs_dict["ee_ori"] = eef_ori
            if state is None:
                state = env.sim.get_state().flatten() if hasattr(env, "sim") else np.array([])
            robot_state = (
                env.get_robot_state_vector(observation)
                if hasattr(env, "get_robot_state_vector")
                else np.array([])
            )
            if self.step_count % 50 == 0:
                if "eye_in_hand_rgb" in obs_dict:
                    logger.debug(
                        f"Collect step: step_count={self.step_count}, obs_dict['eye_in_hand_rgb'].shape={obs_dict['eye_in_hand_rgb'].shape}"
                    )
                else:
                    logger.debug(
                        f"Collect step: step_count={self.step_count}, list(observation.keys())={list(observation.keys())}"
                    )
            self.exporter.add_step(
                observation=obs_dict,
                action=action,
                state=state,
                robot_state=robot_state,
                reward=reward,
                done=done,
            )
            self.step_count += 1
        except Exception as e:
            logger.warning(f"Collect step failed: e={e}")
            import traceback

            traceback.print_exc()

    def end_collection(self, success: bool = False):
        if not self.is_collecting:
            return
        self.is_collecting = False
        self.exporter.end_episode(success=success)
        logger.debug(f"End collection: step_count={self.step_count}, success={success}")
        self.step_count = 0
