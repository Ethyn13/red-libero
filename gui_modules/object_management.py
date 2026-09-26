"""Prepare structural edits without mutating the active scene from a worker."""

import logging
import tempfile
import threading
from copy import deepcopy
from pathlib import Path

from libero.libero.envs import OffScreenRenderEnv

from gui_modules.scene_state import capture_state, restore_state

logger = logging.getLogger(__name__)


def _prune_expression(expression, removed):
    if not isinstance(expression, list):
        return None if expression in removed else expression
    if any(isinstance(item, str) and item in removed for item in expression):
        return None
    children = [_prune_expression(item, removed) for item in expression]
    if children == expression:
        return expression
    if expression and str(expression[0]).lower() in ("and", "or"):
        children = [item for item in children if item is not None]
        return children if len(children) > 1 else None
    return None


class ObjectManager:
    @staticmethod
    def _remove_object_from_bddl(editor, obj_name):
        parsed = editor.parsed_dict
        for obj_type, names in list(parsed["objects"].items()):
            if obj_name in names:
                names.remove(obj_name)
                if not names:
                    del parsed["objects"][obj_type]
        removed_regions = {
            name
            for name, region in parsed.get("regions", {}).items()
            if region.get("target") == obj_name
        }
        # Placement regions can be shared; keep them unless the owner was removed.
        for name in removed_regions:
            del parsed["regions"][name]
        removed = {obj_name, *removed_regions}
        for field in ("initial_state", "goal_state", "cost_state"):
            parsed[field] = [
                result
                for expression in parsed.get(field, [])
                if (result := _prune_expression(expression, removed)) is not None
            ]
        parsed["obj_of_interest"] = [
            name for name in parsed.get("obj_of_interest", []) if name != obj_name
        ]
        if "moving_objects" in parsed:
            parsed["moving_objects"] = [
                obj for obj in parsed["moving_objects"] if obj.get("name") != obj_name
            ]

    @staticmethod
    def start_change(editor, *, obj_name=None, obj_type=None):
        """Capture state on the GUI thread and queue one background rebuild."""
        if not editor.free_mode or editor.ai_mode or editor.data_collection_mode:
            return False
        if (
            getattr(editor, "_object_change_pending", False)
            or editor._new_env_ready is not None
        ):
            return False
        if obj_name is not None:
            info = editor.object_info.get(obj_name)
            if not info or info.get("is_fixture"):
                return False
        from gui_modules.frame_updater import FrameUpdater

        FrameUpdater.process_joint_changes(editor)
        new_editor = deepcopy(editor.editor)
        state = capture_state(editor.env.sim)
        goal_before = deepcopy(new_editor.parsed_dict.get("goal_state", []))
        is_delete = obj_name is not None
        if obj_name is not None:
            ObjectManager._remove_object_from_bddl(new_editor, obj_name)
        else:
            if not obj_type:
                return False
            counter = 1
            while f"{obj_type}_{counter}" in editor.object_info:
                counter += 1
            obj_name = f"{obj_type}_{counter}"
            target = editor.env.env.workspace_name
            if not new_editor.add_object_with_region(
                obj_name=obj_name,
                obj_type=obj_type,
                position=(0.0, 0.0),
                region_half_len=0.05,
                target=target,
                add_to_interest=False,
            ):
                return False
        with tempfile.NamedTemporaryFile(
            dir=editor.workspace_dir,
            prefix="object-edit-",
            suffix=".bddl",
            delete=False,
        ) as file:
            staged_bddl = Path(file.name)
        try:
            new_editor.save(str(staged_bddl))
        except Exception:
            staged_bddl.unlink(missing_ok=True)
            raise
        editor._object_change_pending = True
        editor.is_dragging = False
        payload = {
            "operation": "object_change",
            "new_editor": new_editor,
            "staged_bddl": staged_bddl,
            "changed_object": obj_name,
            "is_delete": is_delete,
            "goals_changed": goal_before
            != new_editor.parsed_dict.get("goal_state", []),
        }
        worker = threading.Thread(
            target=ObjectManager._prepare_change,
            args=(editor, payload, state),
            daemon=True,
        )
        try:
            worker.start()
        except Exception:
            editor._object_change_pending = False
            staged_bddl.unlink(missing_ok=True)
            raise
        return True

    @staticmethod
    def _prepare_change(editor, payload, state):
        new_env = None
        try:
            new_env = OffScreenRenderEnv(
                bddl_file_name=str(payload["staged_bddl"]),
                camera_heights=editor.window_height,
                camera_widths=editor.window_width,
                camera_names="agentview",
                render_gpu_device_id=0,
            )
            new_env.seed(0)
            new_env.reset()
            restore_state(new_env.sim, state)
            if not payload["is_delete"]:
                model = new_env.sim.model
                body = model.body_name2id(payload["changed_object"] + "_main")
                joint = model.body_jntadr[body]
                if model.body_jntnum[body] < 1 or model.jnt_type[joint] != 0:
                    raise ValueError("The added object does not have a free joint")
                v = model.jnt_dofadr[joint]
                # Keep the workspace sampler's height and object-specific orientation.
                new_env.sim.data.qvel[v : v + 6] = 0
                new_env.sim.forward()
            payload["env"] = new_env
        except Exception as error:
            logger.exception("Cannot prepare object edit")
            payload["error"] = str(error)
            if new_env is not None:
                try:
                    new_env.close()
                except Exception:
                    logger.exception("Cannot close failed candidate environment")
        finally:
            with editor._env_switch_lock:
                editor._new_env_ready = payload
