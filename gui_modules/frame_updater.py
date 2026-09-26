"""Refresh camera views and editor status on the GUI thread."""

import logging
import sys

logger = logging.getLogger(__name__)


class FrameUpdater:
    @staticmethod
    def _activate_renderer(env):
        context = getattr(getattr(env, "sim", None), "_render_context_offscreen", None)
        if context is not None:
            context.gl_ctx.make_current()

    @staticmethod
    def _replace_environment(editor_instance, new_env):
        """Release the old renderer in its own GL context, then activate the new one."""
        old_env = editor_instance.env
        if old_env is new_env:
            return
        try:
            if old_env is not None:
                FrameUpdater._activate_renderer(old_env)
                old_env.close()
        except Exception as exc:
            logger.warning("Cannot close previous environment: %s", exc)
        editor_instance.env = new_env
        FrameUpdater._activate_renderer(new_env)

    @staticmethod
    def _immediate_refresh(editor_instance):
        try:
            main, wrist = editor_instance.render_dual_frames()
            editor_instance.im.set_data(main)
            editor_instance.im_wrist.set_data(wrist)
            studio = getattr(editor_instance, "studio", None)
            if studio:
                studio.refresh()
            editor_instance.fig.canvas.draw()
        except Exception:
            logger.exception("Cannot refresh the scene after an environment change")

    @staticmethod
    def handle_environment_switch(editor_instance):
        if (
            not hasattr(editor_instance, "_new_env_ready")
            or editor_instance._new_env_ready is None
        ):
            return False
        with editor_instance._env_switch_lock:
            if editor_instance._new_env_ready is None:
                return False
            new_env_data = editor_instance._new_env_ready
            operation_type = new_env_data.get(
                "type", new_env_data.get("operation", "add_delete")
            )
            if operation_type in ["snapshot_load", "snapshot_restore_only"]:
                editor_instance._handle_snapshot_restore(new_env_data)
                if hasattr(editor_instance, "_init_physics_safety_monitor"):
                    editor_instance._init_physics_safety_monitor()
                editor_instance._new_env_ready = None
                editor_instance._workspace_needs_save = True
                editor_instance._force_refresh_frames = 0
                FrameUpdater._immediate_refresh(editor_instance)
                return True
            if operation_type == "import_bddl":
                editor_instance._handle_bddl_import(new_env_data)
                if hasattr(editor_instance, "_init_physics_safety_monitor"):
                    editor_instance._init_physics_safety_monitor()
                editor_instance._new_env_ready = None
                editor_instance._workspace_needs_save = True
                editor_instance._force_refresh_frames = 0
                FrameUpdater._immediate_refresh(editor_instance)
                return True
            if operation_type == "load_scene_folder":
                FrameUpdater._handle_scene_folder_load(editor_instance, new_env_data)
                editor_instance._new_env_ready = None
                editor_instance._workspace_needs_save = True
                editor_instance._force_refresh_frames = 0
                FrameUpdater._immediate_refresh(editor_instance)
                return True
            if operation_type == "switch_bddl_task":
                FrameUpdater._handle_bddl_task_switch(editor_instance, new_env_data)
                editor_instance._new_env_ready = None
                editor_instance._workspace_needs_save = True
                editor_instance._force_refresh_frames = 0
                FrameUpdater._immediate_refresh(editor_instance)
                return True
            FrameUpdater._handle_object_change(editor_instance, new_env_data)
            editor_instance._new_env_ready = None
            editor_instance._workspace_needs_save = True
            editor_instance._force_refresh_frames = 0
            FrameUpdater._immediate_refresh(editor_instance)
            return True

    @staticmethod
    def _handle_object_change(editor_instance, payload):
        from pathlib import Path

        staged = Path(payload["staged_bddl"])
        studio = getattr(editor_instance, "studio", None)
        try:
            if "error" in payload:
                if studio:
                    studio.log(f"Object edit failed: {payload['error']}", error=True)
                return
            staged.replace(editor_instance.current_bddl)
            FrameUpdater._replace_environment(editor_instance, payload["env"])
            editor_instance.editor = payload["new_editor"]
            editor_instance.editor.source_file = str(editor_instance.current_bddl)
            editor_instance.env.env.bddl_file_name = str(editor_instance.current_bddl)
            editor_instance.selected_object = None
            editor_instance.selected_body_id = None
            editor_instance.is_dragging = False
            editor_instance._original_colors.clear()
            editor_instance._pending_joint_changes.clear()
            editor_instance._load_objects()
            if not payload["is_delete"]:
                editor_instance.selected_object = payload["changed_object"]
                editor_instance.keyboard_control_active = True
                editor_instance._apply_highlight(payload["changed_object"])
                if studio:
                    studio.search.set("")
            editor_instance._init_physics_safety_monitor()
            editor_instance.reset_task_monitoring()
            editor_instance._auto_save_workspace_state(save_as_initial=True)
            if studio:
                action = "Removed" if payload["is_delete"] else "Added"
                studio.log(f"{action} {payload['changed_object']}.")
                if payload["goals_changed"]:
                    studio.log("Removed goal conditions referencing the deleted object; review the task goals.")
        finally:
            staged.unlink(missing_ok=True)
            editor_instance._object_change_pending = False

    @staticmethod
    def _handle_scene_folder_load(editor_instance, env_data):
        sys.stdout.flush()
        try:
            new_env = env_data["new_env"]
            new_editor = env_data["new_editor"]
            new_bddl_file = env_data["new_bddl_file"]
            env_data.get("has_pruned_init", False)
            FrameUpdater._replace_environment(editor_instance, new_env)
            editor_instance.editor = new_editor
            editor_instance.bddl_file = new_bddl_file
            if hasattr(editor_instance, "_init_physics_safety_monitor"):
                editor_instance._init_physics_safety_monitor()
            if hasattr(editor_instance, "_get_instruction_from_bddl"):
                try:
                    new_instruction = editor_instance._get_instruction_from_bddl()
                    if new_instruction and hasattr(editor_instance, "set_instruction"):
                        editor_instance.set_instruction(new_instruction)
                        logger.debug(
                            f"Handle scene folder load: new_instruction={new_instruction}"
                        )
                except Exception as e:
                    logger.warning(f"Handle scene folder load failed: e={e}")
            editor_instance._load_objects()
            for _ in range(5):
                editor_instance.env.sim.render(
                    editor_instance.window_width,
                    editor_instance.window_height,
                    camera_name="agentview",
                )
            editor_instance.env.sim.forward()
            editor_instance._auto_save_workspace_state(save_as_initial=True)
            logger.debug(f"Handle scene folder load: new_bddl_file={new_bddl_file}")
            logger.debug(
                f"Handle scene folder load: len(editor_instance.object_info)={len(editor_instance.object_info)}"
            )
            sys.stdout.flush()
        except Exception as e:
            logger.warning(f"Handle scene folder load failed: e={e}")
            import traceback

            traceback.print_exc()

    @staticmethod
    def _handle_bddl_task_switch(editor_instance, env_data):
        sys.stdout.flush()
        try:
            new_env = env_data["new_env"]
            new_editor = env_data["new_editor"]
            new_bddl_file = env_data["new_bddl_file"]
            new_instruction = env_data.get("new_instruction", "")
            FrameUpdater._replace_environment(editor_instance, new_env)
            editor_instance.editor = new_editor
            editor_instance.bddl_file = new_bddl_file
            if hasattr(editor_instance, "_init_physics_safety_monitor"):
                editor_instance._init_physics_safety_monitor()
            if new_instruction and hasattr(editor_instance, "set_instruction"):
                editor_instance.set_instruction(new_instruction)
                logger.debug(
                    f"Handle bddl task switch: new_instruction={new_instruction}"
                )
            editor_instance._load_objects()
            for _ in range(5):
                editor_instance.env.sim.render(
                    editor_instance.window_width,
                    editor_instance.window_height,
                    camera_name="agentview",
                )
            editor_instance.env.sim.forward()
            import shutil

            shutil.copy2(str(new_bddl_file), str(editor_instance.current_bddl))
            editor_instance._auto_save_workspace_state(save_as_initial=True)
            if hasattr(editor_instance, "reset_task_monitoring"):
                editor_instance.reset_task_monitoring()
            from pathlib import Path

            logger.debug(
                f"Handle bddl task switch: Path(new_bddl_file).stem.replace('_', ' ')={Path(new_bddl_file).stem.replace('_', ' ')}"
            )
            logger.debug(
                f"Handle bddl task switch: Path(new_bddl_file).name={Path(new_bddl_file).name}"
            )
            logger.debug(
                f"Handle bddl task switch: len(editor_instance.object_info)={len(editor_instance.object_info)}"
            )
            sys.stdout.flush()
        except Exception as e:
            logger.warning(f"Handle bddl task switch failed: e={e}")
            import traceback

            traceback.print_exc()

    @staticmethod
    def process_joint_changes(editor_instance):
        if (
            not hasattr(editor_instance, "_pending_joint_changes")
            or not editor_instance._pending_joint_changes
        ):
            return False
        for change in editor_instance._pending_joint_changes:
            try:
                qpos_addr = change["qpos_addr"]
                target_pos = change["target_pos"]
                joint_name = change["joint_name"]
                current_pos = editor_instance.env.sim.data.qpos[qpos_addr]
                model = editor_instance.env.sim.model
                joint_id = model.joint_name2id(joint_name)
                dof_addr = model.jnt_dofadr[joint_id]
                editor_instance.env.sim.data.qpos[qpos_addr] = target_pos
                editor_instance.env.sim.data.qvel[dof_addr] = 0.0
                editor_instance.env.sim.forward()
                logger.debug(
                    f"Process joint changes: joint_name={joint_name}, current_pos={current_pos:.3f}, target_pos={target_pos:.3f}"
                )
            except Exception as e:
                logger.warning(f"Process joint changes failed: e={e}")
                import traceback

                traceback.print_exc()
        editor_instance._pending_joint_changes = []
        editor_instance._workspace_needs_save = True
        return True

    @staticmethod
    def auto_save_workspace(editor_instance):
        if (
            not hasattr(editor_instance, "_workspace_needs_save")
            or not editor_instance._workspace_needs_save
        ):
            return False
        try:
            editor_instance._auto_save_workspace_state()
            editor_instance._workspace_needs_save = False
            return True
        except Exception:
            return False

    @staticmethod
    def run_physics_simulation(editor_instance):
        if editor_instance.free_mode or editor_instance.is_dragging:
            return
        try:
            robot_qpos_size = 9
            robot_qpos = editor_instance.env.sim.data.qpos[:robot_qpos_size].copy()
            robot_qvel = editor_instance.env.sim.data.qvel[:robot_qpos_size].copy()
            num_substeps = 10
            for _ in range(num_substeps):
                editor_instance.env.sim.step()
                editor_instance.env.sim.data.qpos[:robot_qpos_size] = robot_qpos
                editor_instance.env.sim.data.qvel[:robot_qpos_size] = robot_qvel
            editor_instance.env.sim.forward()
            for obj_name, info in editor_instance.object_info.items():
                try:
                    body_id = info["body_id"]
                    actual_pos = editor_instance.env.sim.data.body_xpos[body_id].copy()
                    editor_instance.object_info[obj_name]["pos"] = tuple(actual_pos)
                except:
                    pass
            monitor = getattr(editor_instance, "physics_safety_monitor", None)
            if monitor:
                # Direct MuJoCo stepping bypasses the environment's action counter.
                if hasattr(monitor.env, "step_count"):
                    monitor.env.step_count += num_substeps
                editor_instance._physics_step_count = getattr(editor_instance, "_physics_step_count", 0) + 1
                monitor.check_step(editor_instance._physics_step_count)
        except Exception:
            pass

    @staticmethod
    def run_free_mode_forward(editor_instance):
        try:
            editor_instance.env.sim.forward()
        except:
            pass
