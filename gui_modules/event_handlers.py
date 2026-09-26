"""Dispatch mouse and keyboard input to editor controllers."""

import logging

import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)


class KeyboardHandler:
    @staticmethod
    def mirror_numpad_key(key: str, event=None, editor_instance=None) -> tuple:
        EXCLUDED_KEYS = {"5", "+", "-"}
        if key in EXCLUDED_KEYS:
            return (key, False)
        NUMPAD_SHIFT_MAP = {
            "left": "4",
            "right": "6",
            "up": "8",
            "down": "2",
            "home": "7",
            "end": "1",
            "pageup": "9",
            "pagedown": "3",
        }
        NUMPAD_NO_MIRROR_MAP = {"insert": "0"}
        if key in NUMPAD_NO_MIRROR_MAP:
            return (NUMPAD_NO_MIRROR_MAP[key], False)
        if key in NUMPAD_SHIFT_MAP:
            return (NUMPAD_SHIFT_MAP[key], True)
        if key.startswith("shift+"):
            base_key = key[6:]
            if base_key in EXCLUDED_KEYS:
                return (base_key, False)
            return (base_key, True)
        return (key, False)

    @staticmethod
    def handle_6dof_control(editor_instance, key: str, event=None) -> bool:
        if not editor_instance.selected_object:
            return False
        (base_key, is_mirrored) = KeyboardHandler.mirror_numpad_key(
            key, event, editor_instance
        )
        mirror_factor = -1 if is_mirrored else 1
        trans_step = 0.02
        rot_step = 0.05
        (dx, dy, dz) = (0, 0, 0)
        (droll, dpitch, dyaw) = (0, 0, 0)
        handled = False
        if base_key == "8":
            dx = -trans_step * mirror_factor
            handled = True
        elif base_key == "2":
            dx = trans_step * mirror_factor
            handled = True
        elif base_key == "4":
            dy = trans_step * mirror_factor
            handled = True
        elif base_key == "6":
            dy = -trans_step * mirror_factor
            handled = True
        elif base_key == "5":
            dz = trans_step * mirror_factor
            handled = True
        elif base_key == "0":
            dz = -trans_step * mirror_factor
            handled = True
        elif base_key == "7":
            dyaw = rot_step * mirror_factor
            handled = True
        elif base_key == "9":
            dyaw = -rot_step * mirror_factor
            handled = True
        elif base_key == "*":
            droll = rot_step * mirror_factor
            handled = True
        elif base_key == "/":
            droll = -rot_step * mirror_factor
            handled = True
        elif base_key == "1":
            dpitch = rot_step * mirror_factor
            handled = True
        elif base_key == "3":
            dpitch = -rot_step * mirror_factor
            handled = True
        if handled:
            editor_instance.move_object_6dof(
                editor_instance.selected_object,
                dx,
                dy,
                dz,
                droll=droll,
                dpitch=dpitch,
                dyaw=dyaw,
            )
        return handled

    @staticmethod
    def handle_global_keys(editor_instance, key: str) -> bool:
        from . import help_text

        if key == "escape":
            plt.close(editor_instance.fig)
            return True
        elif key == "h":
            print(help_text.get_help_text())
            return True
        elif key == " ":
            KeyboardHandler._handle_mode_switch(editor_instance)
            return True
        elif key == "shift+s" or key == "S":
            editor_instance.save_scene_to_folder()
            return True
        elif key == "shift+i" or key == "I":
            editor_instance.load_scene_from_folder()
            return True
        elif key == "shift+r" or key == "R":
            editor_instance.reset_scene()
            editor_instance._init_hotkey_panel()
            editor_instance.fig.canvas.draw()
            return True
        elif key == "shift+e" or key == "E":
            editor_instance.resample_scene()
            editor_instance._init_hotkey_panel()
            editor_instance.fig.canvas.draw()
            return True
        elif key == "shift+a" or key == "A":
            if editor_instance.free_mode:
                editor_instance.add_object()
            return True
        elif key == "shift+delete":
            if editor_instance.free_mode:
                if editor_instance.selected_object:
                    editor_instance.delete_object(editor_instance.selected_object)
                else:
                    editor_instance._show_delete_dialog()
            return True
        elif key == "shift+j" or key == "J":
            editor_instance.show_all_joints_info()
            return True
        elif key == "shift+m" or key == "M":
            editor_instance.switch_vla_model()
            return True
        elif key == "shift+t" or key == "T":
            editor_instance.switch_bddl_task()
            return True
        elif key == "ctrl+c":
            if (
                not editor_instance.free_mode
                and (not editor_instance.data_collection_mode)
                and (not editor_instance.ai_mode)
            ):
                editor_instance.start_calibration()
            return True
        elif key == "ctrl+v":
            editor_instance.view_calibration_history()
            return True
        elif key == "ctrl+a":
            editor_instance.accept_calibration()
            return True
        elif key == "alt+k":
            editor_instance.list_calibrations()
            return True
        return False

    @staticmethod
    def _handle_mode_switch(editor_instance):
        if editor_instance.ai_mode:
            return
        if not editor_instance.free_mode and (not editor_instance.data_collection_mode):
            editor_instance.free_mode = True
            editor_instance.keyboard_control_active = True
        elif editor_instance.free_mode and (not editor_instance.data_collection_mode):
            editor_instance.free_mode = False
            if not editor_instance.ai_mode:
                editor_instance.enter_data_collection_mode()
            return
        elif editor_instance.data_collection_mode:
            editor_instance.exit_data_collection_mode(save=True)
            editor_instance.keyboard_control_active = True
            editor_instance.apply_physics_settling()
        editor_instance._init_hotkey_panel()


class MouseHandler:
    @staticmethod
    def handle_mouse_press(editor_instance, event):
        if getattr(editor_instance, "_object_change_pending", False):
            return
        if event.inaxes != editor_instance.ax or event.xdata is None or event.ydata is None:
            return
        if event.button not in (1, 3):
            return
        (x, y) = (int(event.xdata), int(event.ydata))
        if editor_instance.calibration_mode:
            editor_instance.handle_calibration_click(x, y)
            return
        (world_x, world_y) = editor_instance.screen_to_world(x, y)
        modifiers = getattr(event, "modifiers", None)
        alt_pressed = (
            "alt" in modifiers if modifiers is not None
            else "alt" in (event.key or "").lower().split("+")
        )
        result = editor_instance.get_object_at_position(
            x, y, select_parent=not alt_pressed
        )
        if result:
            (obj_name, body_id) = result
        else:
            (obj_name, body_id) = (None, None)
        if event.button == 3 and obj_name:
            mode_hint = " (selected part)" if alt_pressed else " (parent object)"
            body_name = editor_instance.env.sim.model.body_id2name(body_id)
            logger.debug(
                f"Handle mouse press: mode_hint={mode_hint}, obj_name={obj_name}, body_name={body_name}"
            )
            editor_instance.quick_toggle_state(
                obj_name, body_id if alt_pressed else None
            )
            return
        mode_hint = " [part selection]" if alt_pressed else " [whole-object selection]"
        logger.debug(
            f"Handle mouse press: x={x}, y={y}, world_x={world_x:.3f}, world_y={world_y:.3f}, mode_hint={mode_hint}"
        )
        if obj_name:
            selected_body_id = body_id if alt_pressed else None
            if (
                editor_instance.selected_object == obj_name
                and editor_instance.selected_body_id == selected_body_id
            ):
                body_name = editor_instance.env.sim.model.body_id2name(body_id)
                logger.debug(
                    f"Handle mouse press: obj_name={obj_name}, body_name={body_name}"
                )
                editor_instance._remove_highlight(editor_instance.selected_object)
                editor_instance.selected_object = None
                editor_instance.selected_body_id = None
                editor_instance.is_dragging = False
            else:
                if editor_instance.selected_object:
                    editor_instance._remove_highlight(editor_instance.selected_object)
                editor_instance.selected_object = obj_name
                editor_instance.selected_body_id = selected_body_id
                editor_instance.is_dragging = not alt_pressed
                info = editor_instance.object_info[obj_name]
                body_id_for_pos = info["body_id"]
                obj_pos = editor_instance.env.sim.data.body_xpos[body_id_for_pos]
                editor_instance.drag_plane_height = obj_pos[2]
                body_name = editor_instance.env.sim.model.body_id2name(body_id)
                editor_instance._apply_highlight(obj_name, specific_body_id=selected_body_id)
                logger.debug(
                    f"Handle mouse press: obj_name={obj_name}, body_name={body_name}, body_id={body_id}"
                )
                pos = info["pos"]
                logger.debug(f"Handle mouse press: obj_name={obj_name}")
                logger.debug(
                    f"Handle mouse press: pos[0]={pos[0]:.3f}, pos[1]={pos[1]:.3f}, pos[2]={pos[2]:.3f}"
                )
                logger.debug(
                    f"Handle mouse press: editor_instance.drag_plane_height={editor_instance.drag_plane_height:.3f}"
                )
        else:
            if editor_instance.selected_object:
                logger.debug(
                    f"Handle mouse press: editor_instance.selected_object={editor_instance.selected_object}"
                )
                editor_instance._remove_highlight(editor_instance.selected_object)
            editor_instance.selected_object = None
            editor_instance.selected_body_id = None
            editor_instance.is_dragging = False

    @staticmethod
    def handle_mouse_release(editor_instance, event):
        if editor_instance.is_dragging:
            logger.debug(
                f"Handle mouse release: editor_instance.selected_object={editor_instance.selected_object}"
            )
            editor_instance._workspace_needs_save = True
        editor_instance.is_dragging = False

    @staticmethod
    def handle_mouse_scroll(editor_instance, event):
        if getattr(editor_instance, "_object_change_pending", False):
            return
        if not editor_instance.selected_object:
            return
        if editor_instance.selected_object not in editor_instance.object_info:
            return
        z_delta = event.step * 0.02
        info = editor_instance.object_info[editor_instance.selected_object]
        body_id = info["body_id"]
        current_pos = editor_instance.env.sim.data.body_xpos[body_id].copy()
        new_z = current_pos[2] + z_delta
        is_floor_scene = False
        try:
            problem_name = editor_instance.editor.parsed_dict.get("problem_name", "")
            if problem_name:
                problem_name_lower = problem_name.lower()
                if "floor" in problem_name_lower:
                    is_floor_scene = True
        except:
            pass
        if not is_floor_scene:
            try:
                fixtures = editor_instance.editor.get_all_fixtures()
                if fixtures:
                    for fixture_type, fixture_names in fixtures.items():
                        if fixture_type.lower() == "floor" and fixture_names:
                            is_floor_scene = True
                            break
            except:
                pass
        if not is_floor_scene:
            if current_pos[2] < 0.3:
                is_floor_scene = True
        if is_floor_scene:
            min_z = 0.0
            max_z = 1.5
        else:
            min_z = 0.8
            max_z = 2.0
        if not hasattr(editor_instance, "_last_floor_scene_check"):
            editor_instance._last_floor_scene_check = None
        if editor_instance._last_floor_scene_check != is_floor_scene:
            scene_type = "Floor" if is_floor_scene else "Table"
            logger.debug(
                f"Handle mouse scroll: scene_type={scene_type}, min_z={min_z:.1f}, max_z={max_z:.1f}"
            )
            editor_instance._last_floor_scene_check = is_floor_scene
        new_z = max(min_z, min(new_z, max_z))
        editor_instance.move_object(
            editor_instance.selected_object, current_pos[0], current_pos[1], new_z
        )
        direction = "↑" if event.step > 0 else "↓"
        logger.debug(
            f"Handle mouse scroll: direction={direction}, editor_instance.selected_object={editor_instance.selected_object}, new_z={new_z:.3f}"
        )

    @staticmethod
    def handle_mouse_move(editor_instance, event):
        if getattr(editor_instance, "_object_change_pending", False):
            return
        if not editor_instance.is_dragging or not editor_instance.selected_object:
            return
        if event.inaxes != editor_instance.ax:
            return
        if event.xdata is None or event.ydata is None:
            return
        (x, y) = (int(event.xdata), int(event.ydata))
        if editor_instance.drag_plane_height is not None:
            world_pos_3d = editor_instance.get_3d_position_from_mouse(
                x, y, editor_instance.drag_plane_height
            )
            if world_pos_3d is not None:
                import numpy as np

                if np.random.rand() < 0.05:
                    logger.debug(
                        f"Handle mouse move: x={x}, y={y}, world_pos_3d[0]={world_pos_3d[0]:.3f}, world_pos_3d[1]={world_pos_3d[1]:.3f}, world_pos_3d[2]={world_pos_3d[2]:.3f}"
                    )
                editor_instance.move_object(
                    editor_instance.selected_object,
                    world_pos_3d[0],
                    world_pos_3d[1],
                    world_pos_3d[2],
                )
            else:
                (world_x, world_y) = editor_instance.screen_to_world(x, y)
                editor_instance.move_object(
                    editor_instance.selected_object, world_x, world_y
                )
        else:
            (world_x, world_y) = editor_instance.screen_to_world(x, y)
            editor_instance.move_object(
                editor_instance.selected_object, world_x, world_y
            )
