"""Load and restore simulator snapshots paired with BDDL tasks."""

import logging
import shutil
from pathlib import Path

import numpy as np
import torch
import yaml

logger = logging.getLogger(__name__)


def load_init_state_with_verification(editor_instance, init_state_file: str):
    try:
        if not Path(init_state_file).exists():
            logger.debug(
                f"Load init state with verification: init_state_file={init_state_file}"
            )
            return
        shutil.copy2(init_state_file, str(editor_instance.current_state))
        meta_file = Path(init_state_file).with_suffix(".meta.yaml")
        metadata = None
        if meta_file.exists():
            with open(meta_file, "r", encoding="utf-8") as f:
                metadata = yaml.safe_load(f)
            if "metadata" in metadata:
                logger.debug(
                    f"Load init state with verification: metadata['metadata']['timestamp']={metadata['metadata']['timestamp']}"
                )
                logger.debug(
                    f"Load init state with verification: metadata['metadata']['scene_name']={metadata['metadata']['scene_name']}"
                )
            elif "timestamp" in metadata:
                logger.debug(
                    f"Load init state with verification: metadata['timestamp']={metadata['timestamp']}"
                )
                logger.debug(
                    f"Load init state with verification: metadata.get('scene_name', 'Unknown')={metadata.get('scene_name', 'Unknown')}"
                )
            if "objects" in metadata:
                logger.debug(
                    f"Load init state with verification: len(metadata['objects'])={len(metadata['objects'])}"
                )
            if "fixtures" in metadata:
                logger.debug(
                    f"Load init state with verification: len(metadata['fixtures'])={len(metadata['fixtures'])}"
                )
        bddl_file = Path(init_state_file).with_suffix(".bddl")
        if bddl_file.exists():
            shutil.copy2(str(bddl_file), str(editor_instance.current_bddl))
            from bddl_editor import BDDLEditor
            from libero.libero.envs import OffScreenRenderEnv

            env_args = {
                "bddl_file_name": str(editor_instance.current_bddl),
                "camera_heights": editor_instance.window_height,
                "camera_widths": editor_instance.window_width,
                "camera_names": "agentview",
                "render_gpu_device_id": 0,
            }
            old_env = editor_instance.env
            try:
                new_env = OffScreenRenderEnv(**env_args)
                new_env.seed(0)
                new_env.reset()
                editor_instance.env = new_env
                editor_instance.editor = BDDLEditor(str(editor_instance.current_bddl))
                editor_instance._load_objects()
                try:
                    old_env.close()
                except:
                    pass
            except Exception as e:
                logger.warning(f"Load init state with verification failed: e={e}")
                editor_instance.env = old_env
                return
        state_tensor = torch.load(str(editor_instance.current_state))
        if isinstance(state_tensor, torch.Tensor):
            state_array = state_tensor.numpy()
        else:
            state_array = state_tensor
        current_qpos_size = len(editor_instance.env.sim.data.qpos)
        if len(state_array) < current_qpos_size * 2:
            logger.debug(
                f"Load init state with verification: len(state_array)={len(state_array)}, current_qpos_size * 2={current_qpos_size * 2}"
            )
            return
        editor_instance.env.sim.set_state_from_flattened(state_array)
        editor_instance.env.sim.forward()
        for obj_name, info in editor_instance.object_info.items():
            try:
                body_id = info["body_id"]
                actual_pos = editor_instance.env.sim.data.body_xpos[body_id].copy()
                editor_instance.object_info[obj_name]["pos"] = tuple(actual_pos)
            except:
                pass
        if metadata:
            all_meta_objects = {}
            all_meta_objects.update(metadata.get("objects", {}))
            all_meta_objects.update(metadata.get("fixtures", {}))
            max_error = 0.0
            error_count = 0
            for obj_name, meta_obj in all_meta_objects.items():
                if obj_name in editor_instance.object_info:
                    body_id = editor_instance.object_info[obj_name]["body_id"]
                    current_pos = editor_instance.env.sim.data.body_xpos[body_id]
                    saved_pos = np.array(
                        [
                            meta_obj["position"]["x"],
                            meta_obj["position"]["y"],
                            meta_obj["position"]["z"],
                        ]
                    )
                    error = np.linalg.norm(current_pos - saved_pos)
                    max_error = max(max_error, error)
                    if error > 0.001:
                        error_count += 1
                        logger.debug(
                            f"Load init state with verification: obj_name={obj_name}, error * 1000={error * 1000:.2f}"
                        )
            if not error_count == 0:
                logger.debug(
                    f"Load init state with verification: error_count={error_count}"
                )
                logger.debug(
                    f"Load init state with verification: max_error * 1000={max_error * 1000:.2f}"
                )
        logger.debug(
            f"Load init state with verification: state_array.shape={state_array.shape}"
        )
        logger.debug(
            f"Load init state with verification: len(editor_instance.object_info)={len(editor_instance.object_info)}"
        )
    except Exception as e:
        logger.warning(f"Load init state with verification failed: e={e}")
        import traceback

        traceback.print_exc()
