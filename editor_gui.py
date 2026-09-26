#!/usr/bin/env python3
"""Red LIBERO scene editor and interactive VLA workspace."""

import os
import sys

# Select the GUI backend before importing pyplot.
if 'MPLBACKEND' not in os.environ:
    os.environ['MPLBACKEND'] = 'TkAgg'

import matplotlib
matplotlib.use('TkAgg', force=True)

import warnings
warnings.filterwarnings('ignore', message='Glyph .* missing from font')

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.widgets import TextBox
import matplotlib.pyplot as plt

import numpy as np
from pathlib import Path
from typing import Optional, Dict, List, Tuple


import yaml
from datetime import datetime
import torch
import shutil
import threading
import imageio

# Add the checkout root so both public and compatibility packages resolve.
sys.path.insert(0, os.path.dirname(__file__))

try:
    from red_libero import benchmark, get_path as get_libero_path, OffScreenRenderEnv
except ImportError as e:
    print(f"Cannot import red-libero: {e}")
    print(f"Current sys.path: {sys.path[:3]}")
    print(f"Script directory: {os.path.dirname(__file__)}")
    sys.exit(1)

from bddl_editor import BDDLEditor

from gui_modules import coordinate_utils, help_text, joint_control
from gui_modules.constants import AVAILABLE_OBJECTS
from gui_modules.frame_updater import FrameUpdater
from gui_modules.event_handlers import KeyboardHandler, MouseHandler
from gui_modules.object_management import ObjectManager
from gui_modules.ai_mode import AIController
from gui_modules.safety_monitor import SafetyMonitor
from gui_modules.data_collection_mode import DataCollectionController

_SCRIPT_DIR = Path(__file__).parent

class MatplotlibGUIEditor:
    """Interactive scene editor using Matplotlib and Tk."""

    def __init__(self, bddl_file_path: Optional[str] = None, custom_save_dir: Optional[str] = None, vla_model_path: Optional[str] = None, ui_style: str = "studio"):
        self.ui_style = ui_style
        self.studio = None
        self.bddl_file = bddl_file_path or self._get_default_task()

        if not self.bddl_file:
            raise ValueError("Could not load the BDDL file")

        self.custom_save_dir = custom_save_dir
        if self.custom_save_dir:
            Path(self.custom_save_dir).mkdir(parents=True, exist_ok=True)

        self.vla_model_path = vla_model_path
        if self.vla_model_path:
            print(f"VLA model path: {self.vla_model_path}")

        self.workspace_dir = Path(".red-libero") / "workspace"
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        # Keep the reset baseline separate from the current editable state.
        # initial_* changes on scene load; R restores it.
        # current_* changes during editing and resampling.
        self.initial_bddl = self.workspace_dir / "initial.bddl"
        self.initial_state = self.workspace_dir / "initial.pruned_init"
        self.current_bddl = self.workspace_dir / "current.bddl"
        self.current_state = self.workspace_dir / "current.pruned_init"

        self._workspace_needs_save = False

        self._new_env_ready = None  # The worker prepares an environment; the GUI thread installs it.
        self._env_switch_lock = threading.Lock()
        self._object_change_pending = False

        self._pending_joint_changes = []

        self._force_refresh_frames = 0

        shutil.copy2(self.bddl_file, self.initial_bddl)
        shutil.copy2(self.bddl_file, self.current_bddl)

        print(f"\n{'='*70}")
        print(f"red-libero Scene Studio - Matplotlib GUI")
        print(f"{'='*70}")
        print(f"Source BDDL: {self.bddl_file}")
        print(f"Initial BDDL: {self.initial_bddl} (press R to restore)")
        print(f"Working BDDL: {self.current_bddl} (current state)")
        if self.custom_save_dir:
            print(f"Save directory: {self.custom_save_dir}")
        print(f"{'='*70}\n")

        self.editor = BDDLEditor(str(self.current_bddl))

        self.window_width = 640
        self.window_height = 480

        print("Starting the red-libero simulator...")
        self.env = None
        self.object_info = {}

        try:
            self._init_libero_env()
        except Exception as e:
            print(f"Simulator startup failed: {e}")
            raise

        self._load_objects()

        self.selected_object = None
        self.selected_body_id = None  # Component body selected by Alt+click.
        self.is_dragging = False
        self.drag_plane_height = None  # Keep the drag plane at the selected object's depth.

        self._original_colors = {}  # {obj_name: {geom_id: original_rgba}}

        self.fig = plt.figure(figsize=(21, 7.5))
        self.fig.canvas.manager.set_window_title('red-libero Scene Studio')

        self.fig.subplots_adjust(top=0.92, bottom=0.08)

        gs = self.fig.add_gridspec(1, 3, width_ratios=[2, 2, 1], wspace=0.02)
        self.ax_wrist = self.fig.add_subplot(gs[0])
        self.ax = self.fig.add_subplot(gs[1])
        self.info_ax = self.fig.add_subplot(gs[2])

        self._init_instruction_textbox()

        # Disable Matplotlib shortcuts that conflict with editor controls.
        rcParams = plt.rcParams
        rcParams['keymap.save'] = []
        rcParams['keymap.quit'] = []
        rcParams['keymap.fullscreen'] = []
        rcParams['keymap.home'] = []
        rcParams['keymap.back'] = []
        rcParams['keymap.forward'] = []

        frame_main, frame_wrist = self.render_dual_frames()
        self.im = self.ax.imshow(frame_main)
        self.im_wrist = self.ax_wrist.imshow(frame_wrist)
        self.ax.axis('off')
        self.ax_wrist.axis('off')

        self.ax.set_title('Main View (agentview)', fontsize=10, pad=5)
        self.ax_wrist.set_title('Wrist View (eye_in_hand)', fontsize=10, pad=5)

        self.object_markers = []
        self.click_marker = None

        self.debug_mode = False

        # Initialize mode flags before building the shortcut panel.
        self.free_mode = False
        self.keyboard_control_active = False

        self.ai_mode = False
        self.ai_controller = None

        self.data_collection_mode = False
        self.data_collector = None
        self.ai_hotkeys_disabled = False


        # The environment initializer owns the physics safety monitor.
        # Do not overwrite the monitor created by _init_libero_env.

        self.ai_video_frames = []
        self.ai_video_wrist_frames = []
        self.ai_video_path = None
        self.ai_video_wrist_path = None
        self.ai_video_saved = False

        self.task_success = False
        self.episode_cost = 0.0
        self.safety_events = []
        self.cost_history = []
        self.total_steps = 0
        self.last_check_step = 0

        self.info_ax.axis('off')
        # The panel must tolerate an uninitialized physics safety monitor.
        self._init_hotkey_panel()

        self.calibration_mode = False
        self.calibration_points = []  # [(screen_x, screen_y, world_x, world_y), ...]
        self.calibration_target = None
        self._calibration_params_x = None
        self._calibration_params_y = None
        self.calibration_history = []
        self.calibration_file = Path("calibration.yaml")

        self.load_calibration_from_file()

        self.fig.canvas.mpl_connect('button_press_event', self.on_mouse_press)
        self.fig.canvas.mpl_connect('button_release_event', self.on_mouse_release)
        self.fig.canvas.mpl_connect('motion_notify_event', self.on_mouse_move)
        self.fig.canvas.mpl_connect('scroll_event', self.on_mouse_scroll)
        self.fig.canvas.mpl_connect('key_press_event', self.on_key_press)

        self.timer = self.fig.canvas.new_timer(interval=33)
        self.timer.add_callback(self.update_frame)

        from gui_modules.policy.profiles import last_profile
        from gui_modules.policy.service import ServiceManager
        self.policy_service = ServiceManager()
        self.vla_model_path = self.vla_model_path or last_profile()
        if self.vla_model_path:
            self.ai_controller = AIController(self, self.vla_model_path)
        self.fig.canvas.mpl_connect("close_event", self._close_policy)

        if self.ui_style == "studio":
            from gui_modules.studio_ui import StudioShell
            self.studio = StudioShell(self)

        self._init_hotkey_panel()
        self.fig.canvas.draw_idle()

        if self.ui_style == "classic":
            self.show_help()

    def _init_instruction_textbox(self):
        """Create an editable task instruction field initialized from BDDL."""
        if self.ui_style == "studio":
            self._current_instruction = self._get_instruction_from_bddl()
            self._textbox_editing = False
            self.instruction_textbox = None
            return

        default_instruction = self._get_instruction_from_bddl()

        # [left, bottom, width, height] in figure coordinates (0-1)
        textbox_left = 0.23
        textbox_width = 0.6
        self.instruction_ax = self.fig.add_axes([textbox_left, 0.94, textbox_width, 0.04])

        self.instruction_textbox = TextBox(
            self.instruction_ax,
            'Task Instruction: ',
            initial=default_instruction,
            textalignment='left',
            color='#ffffd0',
            hovercolor='#ffffe0',
        )
        label_pos = self.instruction_textbox.label.get_position()
        new_label_x = label_pos[0] - 0.15
        new_label_y = label_pos[1]
        self.instruction_textbox.label.set_position((new_label_x, new_label_y))
        try:
            self.instruction_textbox.label.set_fontsize(10)
            self.instruction_textbox.label.set_fontweight('bold')
            self.instruction_textbox.label.set_color('#006400')
            self.instruction_textbox.label.set_horizontalalignment('left')

            self.instruction_textbox.text_disp.set_fontsize(10)
            self.instruction_textbox.text_disp.set_color('#000080')
            self.instruction_textbox.text_disp.set_horizontalalignment('left')

            self.instruction_ax.set_facecolor('#f0fff0')
            self.instruction_ax.set_xticks([])
            self.instruction_ax.set_yticks([])


            for spine in self.instruction_ax.spines.values():
                spine.set_edgecolor('#228b22')
                spine.set_linewidth(2)
        except Exception as e:
            print(f"  Could not style the instruction field: {e}")

        self._current_instruction = default_instruction

        self._textbox_editing = False

        self.instruction_textbox.on_submit(self._on_instruction_submit)
        self.instruction_textbox.on_text_change(self._on_instruction_change)


    def _get_instruction_from_bddl(self) -> str:
        """Read the task instruction from the current BDDL file."""
        try:
            parsed_dict = self.editor.parsed_dict

            language = parsed_dict.get('language', [])
            if language:
                if isinstance(language, list) and len(language) > 0:
                    return ' '.join(str(item) for item in language)
                elif isinstance(language, str):
                    return language

            instructions = parsed_dict.get('language_instruction', [])
            if instructions and len(instructions) > 0:
                return ' '.join(str(item) for item in instructions)

            problem_name = parsed_dict.get('problem_name', '')
            if problem_name:
                return problem_name.replace('_', ' ')

            if self.bddl_file:
                file_stem = Path(self.bddl_file).stem
                return file_stem.replace('_', ' ')

            return "Complete the task"
        except Exception as e:
            return "Complete the task"

    def _on_instruction_submit(self, text):
        """Handle instruction submission with Enter."""
        self._current_instruction = text.strip()

    def _on_instruction_change(self, text):
        """Handle instruction edits."""
        self._current_instruction = text.strip()

    def get_current_instruction(self) -> str:
        """Return the instruction used by the VLA policy."""
        if hasattr(self, 'instruction_textbox') and self.instruction_textbox is not None:
            try:
                return self.instruction_textbox.text.strip()
            except:
                pass
        return self._current_instruction if hasattr(self, '_current_instruction') else "Complete the task"

    def set_instruction(self, instruction: str):
        """Update the task instruction."""
        self._current_instruction = instruction
        if hasattr(self, 'instruction_textbox') and self.instruction_textbox is not None:
            try:
                self.instruction_textbox.set_val(instruction)
            except:
                pass

    def _init_hotkey_panel(self):
        """Create the shortcut panel and AI status display."""
        if self.ui_style == "studio":
            if self.studio is not None:
                self.studio.refresh()
            return
        self.info_ax.clear()
        self.info_ax.axis('off')

        if self.data_collection_mode:
            mode_text = "DATA_COLLECTION"
            mode_color = 'orange'
        elif self.ai_mode:
            mode_text = "AI"
            mode_color = 'red'
        elif self.data_collection_mode:
            mode_text = "HUMAN"
            mode_color = 'cyan'
        elif self.free_mode:
            mode_text = "FREE"
            mode_color = 'blue'
        else:
            mode_text = "PHYSICS"
            mode_color = 'green'

        if self.data_collection_mode:
            # Data collection mode: show collection status and control instructions (using NumPad)
            status_text = self.data_collector.get_status_text() if self.data_collector else "Not Collecting"
            hotkeys = [
                ("=== DATA COLLECT ===", ""),
                (f"Status: {status_text}", ""),
                ("", ""),
                ("=== NumPad Control ===", ""),
                ("2/8", "X-axis +/-"),
                ("4/6", "Y-axis +/-"),
                ("5/0", "Z-axis +/-"),
                ("7/9", "Yaw +/-"),
                ("1/3", "Pitch +/-"),
                ("*//", "Roll +/-"),
                ("", ""),
                ("Enter", "Toggle Gripper"),
                ("-", "Hold Gripper"),
                ("+", "Idle (Wait)"),
                ("", ""),
                ("Space", "Save & Exit"),
                ("ESC", "Cancel"),
            ]
        elif self.ai_mode:
            status = self.ai_controller.get_status_text() if self.ai_controller else "Ready"
            hotkeys = [
                ("=== AI MODE ===", ""),
                ("", ""),
                (f"Status: {status}", ""),
                ("", ""),
                ("Enter", "Start run"),
                ("P", "Pause/Resume"),
                ("R", "Replay"),
                ("Space", "Exit & Reset"),
                ("", ""),
                (f"Current: {mode_text}", ""),
            ]
        else:
            hotkeys = help_text.get_short_help_keys()

            if not self.free_mode and hasattr(self, 'physics_safety_monitor') and self.physics_safety_monitor:
                try:
                    all_events = self.physics_safety_monitor.get_all_events()
                    event_count = len(all_events) if all_events else 0

                    safety_info = [
                        ("=== SAFETY ===", ""),
                        ("Events:", str(event_count)),
                    ]

                    if event_count > 0:
                        recent_events = all_events[-2:] if len(all_events) > 2 else all_events
                        event_types = set()
                        for event in recent_events:
                            event_type = event.get('event_type', 'unknown')
                            event_types.add(event_type)

                        if event_types:
                            types_text = ', '.join(list(event_types)[:2])
                            if len(event_types) > 2:
                                types_text += '...'
                            safety_info.append(("Recent:", types_text))

                    safety_info.append(("", ""))
                    hotkeys = safety_info + hotkeys
                except Exception as e:
                    pass

            for i, (key, desc) in enumerate(hotkeys):
                if key == "Space":
                    hotkeys.insert(i+1, (f"Current: {mode_text}", ""))
                    break

        y_pos = 0.98

        if self.ai_mode:
            if self.ai_controller:
                if self.ai_controller.is_executing:
                    full_mode_text = f"AI MODE\nEXECUTING... ({self.ai_controller._steps} steps)"
                elif self.ai_controller.execution_done:
                    if self.ai_controller.is_playing:
                        progress = f"{self.ai_controller.play_index}/{len(self.ai_controller.trajectory_cache)}"
                        full_mode_text = f"AI MODE\nPLAYING ▶ {progress}"
                    else:
                        full_mode_text = "AI MODE\nPAUSED"
                else:
                    full_mode_text = "AI MODE\nREADY - Enter to start"
            else:
                full_mode_text = "AI MODE"
            mode_color = 'red'
        elif self.data_collection_mode:
            full_mode_text = "HUMAN MODE"
            mode_color = 'cyan'
        elif self.free_mode:
            full_mode_text = "FREE MODE"
            mode_color = 'orange'
        else:
            full_mode_text = "PHYSICS MODE"
            mode_color = 'lime'

        mode_box = self.info_ax.text(
            0.5, y_pos, full_mode_text,
            fontsize=12, weight='bold',
            color=mode_color,
            ha='center', va='top',
            transform=self.info_ax.transAxes,
            bbox=dict(boxstyle='round,pad=0.5', facecolor='black', alpha=0.8, edgecolor=mode_color, linewidth=2)
        )

        line_count = full_mode_text.count('\n') + 1
        y_pos -= 0.06 * line_count
        y_pos -= 0.02

        line_height = 0.025

        for key, desc in hotkeys:
            if "===" in key:
                if "SAFETY" in key:
                    color = 'darkgreen'
                else:
                    color = 'darkblue'
                self.info_ax.text(
                    0.05, y_pos, key,
                    fontsize=9, weight='bold',
                    color=color,
                    transform=self.info_ax.transAxes
                )
                y_pos -= line_height
            elif key == "":
                pass
            elif "Current:" in key:
                self.info_ax.text(
                    0.05, y_pos, key,
                    fontsize=8, weight='bold',
                    color=mode_color,
                    transform=self.info_ax.transAxes
                )
                y_pos -= line_height
            elif key == "Events:":
                try:
                    event_count_int = int(desc) if desc else 0
                except (ValueError, TypeError):
                    event_count_int = 0
                event_color = 'red' if event_count_int > 0 else 'green'
                self.info_ax.text(
                    0.05, y_pos, key,
                    fontsize=8, weight='bold',
                    color='black',
                    transform=self.info_ax.transAxes
                )
                self.info_ax.text(
                    0.35, y_pos, desc,
                    fontsize=8,
                    color=event_color,
                    transform=self.info_ax.transAxes
                )
                y_pos -= line_height
            elif key == "Recent:":
                self.info_ax.text(
                    0.05, y_pos, key,
                    fontsize=8, weight='bold',
                    color='black',
                    transform=self.info_ax.transAxes
                )
                self.info_ax.text(
                    0.35, y_pos, desc,
                    fontsize=7,
                    color='red',
                    transform=self.info_ax.transAxes
                )
                y_pos -= line_height
            else:
                self.info_ax.text(
                    0.05, y_pos, key,
                    fontsize=8, weight='bold',
                    color='black',
                    transform=self.info_ax.transAxes
                )
                if desc:
                    self.info_ax.text(
                        0.35, y_pos, desc,
                        fontsize=7,
                        color='gray',
                        transform=self.info_ax.transAxes
                    )
                y_pos -= line_height

        if self.ai_mode and self.ai_controller:
            self._render_ai_status_panel()

        self.info_ax.add_patch(plt.Rectangle(
            (0, 0), 1, 1,
            fill=False, edgecolor='lightgray', linewidth=2,
            transform=self.info_ax.transAxes
        ))

    def _render_ai_status_panel(self):
        """Render live AI status in the information panel."""
        if not self.ai_controller:
            return

        y_start = 0.70
        line_height = 0.035

        self.info_ax.plot([0.05, 0.95], [y_start + 0.01, y_start + 0.01],
                         'k-', linewidth=1, transform=self.info_ax.transAxes)

        self.info_ax.text(0.5, y_start - 0.01, "=== AI STATUS ===",
                         fontsize=9, weight='bold', color='darkred',
                         ha='center', transform=self.info_ax.transAxes)
        y_start -= line_height

        if self.ai_controller.is_executing:
            phase = "🔄 Executing"
            phase_color = 'orange'
        elif self.ai_controller.execution_done and self.ai_controller.is_playing:
            phase = "▶ Playing"
            phase_color = 'blue'
        elif self.ai_controller.execution_done:
            phase = "⏸ Paused"
            phase_color = 'gray'
        else:
            phase = "Ready - Enter to start"
            phase_color = 'gray'

        status_items = [
            ("Phase:", phase, phase_color),
            ("Steps:", str(self.ai_controller._steps), 'black'),
        ]

        if self.task_success:
            status_items.append(("Task:", "Success", 'green'))
        elif self.ai_controller.execution_done:
            status_items.append(("Task:", "Failed", 'red'))

        violation_count = 0
        if hasattr(self, 'physics_safety_monitor') and self.physics_safety_monitor:
            all_events = self.physics_safety_monitor.get_all_events()
            violation_count = len(all_events) if all_events else 0

        if violation_count > 0:
            cost_text = f"⚠️ {violation_count}"
            status_items.append(("Cost:", cost_text, 'red'))
            status_items.append(("Violations:", str(violation_count), 'red'))
        else:
            status_items.append(("Cost:", "0 ✓", 'green'))

        if self.ai_controller.inference_count > 0 and self.ai_controller.total_inference_time > 0:
            avg_time = self.ai_controller.total_inference_time / (self.ai_controller.inference_count // 8 + 1)
            status_items.append(("Avg Time:", f"{avg_time*1000:.0f}ms", 'black'))

        if self.ai_controller.execution_done and len(self.ai_controller.trajectory_cache) > 0:
            progress = f"{self.ai_controller.play_index}/{len(self.ai_controller.trajectory_cache)}"
            status_items.append(("Progress:", progress, 'blue'))

        for label, value, color in status_items:
            self.info_ax.text(0.05, y_start, label,
                            fontsize=8, weight='bold', color='black',
                            transform=self.info_ax.transAxes)
            self.info_ax.text(0.40, y_start, value,
                            fontsize=8, color=color,
                            transform=self.info_ax.transAxes)
            y_start -= line_height

        box_bottom = max(y_start - 0.03, 0.02)
        box_height = 0.70 - box_bottom
        self.info_ax.add_patch(plt.Rectangle(
            (0.02, box_bottom), 0.96, box_height,
            fill=True, facecolor='lightyellow', alpha=0.3,
            edgecolor='orange', linewidth=1.5,
            transform=self.info_ax.transAxes,
            zorder=0
        ))

    def _get_default_task(self):
        try:
            benchmark_dict = benchmark.get_benchmark_dict()
            task_suite = benchmark_dict["libero_10"]()
            task = task_suite.get_task(0)
            return os.path.join(
                get_libero_path("bddl_files"),
                task.problem_folder,
                task.bddl_file
            )
        except Exception as e:
            print(f"Could not get the default task: {e}")
            return None

    def get_current_task_instruction(self) -> str:
        """Return the current BDDL task instruction."""
        try:
            parsed_dict = self.editor.parsed_dict

            language = parsed_dict.get('language', [])
            if language:
                if isinstance(language, list) and len(language) > 0:
                    # BDDL language fields are parsed as word lists.
                    instruction = ' '.join(str(item) for item in language)
                    return instruction
                elif isinstance(language, str):
                    return language

            instructions = parsed_dict.get('language_instruction', [])
            if instructions:
                if isinstance(instructions, list) and len(instructions) > 0:
                    instruction = ' '.join(str(item) for item in instructions)
                    return instruction
                elif isinstance(instructions, str):
                    return instructions

            problem_name = parsed_dict.get('problem_name', '')
            if problem_name:
                instruction = problem_name.replace('_', ' ')
                return instruction

            if self.bddl_file:
                file_stem = Path(self.bddl_file).stem
                instruction = file_stem.replace('_', ' ')
                return instruction

            return ""
        except Exception as e:
            print(f"Could not read the task instruction: {e}")
            return ""

    def _init_libero_env(self):
        # Policy observations use 256x256; GUI rendering has an independent resolution.
        env_args = {
            "bddl_file_name": str(self.current_bddl),
            "camera_heights": 256,
            "camera_widths": 256,
            "camera_names": "agentview",
            "render_gpu_device_id": 0,
            "has_renderer": False,
            "has_offscreen_renderer": True,
            "use_camera_obs": True,
        }

        self.env = OffScreenRenderEnv(**env_args)
        self.env.seed(0)
        obs = self.env.reset()

        print(f"  - Cameras: {env_args['camera_names']}")
        print(f"  - Camera observation resolution: 256x256 (VLA)")
        print(f"  - GUI resolution: {self.window_width}x{self.window_height}")

        self._auto_save_workspace_state(save_as_initial=True)
        self._workspace_needs_save = False

        if not hasattr(self, 'physics_safety_monitor'):
            self.physics_safety_monitor = None
        self._init_physics_safety_monitor()

        if not hasattr(self, 'data_collector'):
            self.data_collector = None
        self._init_data_collector()

        # Defer panel rendering until the figure and axes exist.

    def _init_physics_safety_monitor(self):
        """Initialize the safety monitor for physics mode."""
        try:
            local_config = self.workspace_dir.parent / "safety_rules.bddl"
            default_config = _SCRIPT_DIR / "gui_modules" / "safety_monitoring_config.bddl"
            config_path = getattr(self, 'safety_config_path', local_config if local_config.exists() else default_config)
            self.safety_config_path = Path(config_path)
            self.physics_safety_monitor = SafetyMonitor(self.env, str(config_path), debug=False)
            self._physics_step_count = 0
            print("  Physics-mode safety monitor initialized")
        except Exception as e:
            print(f"  Could not initialize the safety monitor: {e}")
            self.physics_safety_monitor = None

    def _init_data_collector(self):
        """Initialize the data collection controller."""
        try:
            self.data_collector = DataCollectionController(self)
        except Exception as e:
            print(f"  Could not initialize the data collector: {e}")
            import traceback
            traceback.print_exc()
            self.data_collector = None

    def _auto_save_workspace_state(self, save_as_initial=False):
        """Save workspace state, optionally also replacing the initial reset state."""
        try:
            sim_state = self.env.sim.get_state()
            state_tensor = torch.from_numpy(sim_state.flatten())

            torch.save(state_tensor, str(self.current_state))

            if save_as_initial:
                torch.save(state_tensor, str(self.initial_state))
                shutil.copy2(str(self.current_bddl), str(self.initial_bddl))
                print(f"  Saved initial state: {self.initial_state.name} (press R to restore)")
        except Exception as e:
            print(f"  Could not save workspace state: {e}")

    def _load_objects(self):
        """Load movable objects and fixtures from the scene."""
        self.object_info = {}

        all_objects = self.editor.get_all_objects()

        try:
            all_fixtures = self.editor.get_all_fixtures()
        except Exception as e:
            print(f"Could not load fixtures: {e}")
            print(f"   Continuing with movable objects...")
            all_fixtures = {}

        print(f"\nScene objects:")
        print(f"{'-'*70}")

        for obj_type, obj_list in all_objects.items():
            for obj_name in obj_list:
                self._load_single_object(obj_name, obj_type, is_fixture=False)

        if all_fixtures:
            print(f"\nScene fixtures:")
            for fixture_type, fixture_list in all_fixtures.items():
                for fixture_name in fixture_list:
                    self._load_single_object(fixture_name, fixture_type, is_fixture=True)

        print(f"{'-'*70}")

    def _find_all_related_bodies(self, obj_name: str, main_body_id: int) -> list:
        """Return the main body and all descendant body IDs for an object."""
        related_bodies = [main_body_id]
        model = self.env.sim.model

        for body_id in range(model.nbody):
            try:
                body_name = model.body_id2name(body_id)
                if body_name and body_name.startswith(obj_name):
                    if body_id not in related_bodies:
                        related_bodies.append(body_id)
            except:
                pass

        return related_bodies

    def _load_single_object(self, obj_name: str, obj_type: str, is_fixture: bool = False):
        """Add an object or fixture to the editor's object index."""
        body_names_to_try = [
            obj_name,
            f"{obj_name}_main",
            f"{obj_name}_body",
            f"{obj_name}_base",
            f"{obj_name}_frame",
            f"{obj_name}_collision",
            obj_type,
            f"{obj_type}_1",
        ]

        body_found = False
        for body_name in body_names_to_try:
            try:
                body_id = self.env.sim.model.body_name2id(body_name)
                pos = self.env.sim.data.body_xpos[body_id]

                articulated_joints = self._detect_object_joints(obj_name)

                body_jnt_id = self.env.sim.model.body_jntadr[body_id]
                has_free_joint = False
                if body_jnt_id >= 0:
                    jnt_type = self.env.sim.model.jnt_type[body_jnt_id]
                    has_free_joint = (jnt_type == 0)  # 0 = free joint

                all_body_ids = self._find_all_related_bodies(obj_name, body_id)

                self.object_info[obj_name] = {
                    'type': obj_type,
                    'body_name': body_name,
                    'body_id': body_id,
                    'all_body_ids': all_body_ids,
                    'pos': tuple(pos),
                    'initial_pos': tuple(pos),
                    'joints': articulated_joints,
                    'is_fixture': is_fixture,
                    'has_free_joint': has_free_joint,
                }

                fixture_tag = " [FIXTURE]" if is_fixture else ""
                joint_info = f" [J:{len(articulated_joints)}]" if articulated_joints else ""
                static_tag = " [STATIC]" if not has_free_joint else ""
                print(f"  ✓ {obj_name:20s} ({obj_type:15s}) at ({pos[0]:6.3f}, {pos[1]:6.3f}, {pos[2]:6.3f}){fixture_tag}{joint_info}{static_tag}")

                if is_fixture and not has_free_joint:
                    print(f"     {obj_name} is static; its joints can be adjusted, but it cannot be moved directly")

                body_found = True
                break
            except:
                continue

        if not body_found:
            fixture_tag = " [FIXTURE]" if is_fixture else ""
            print(f"  {obj_name:20s} ({obj_type:15s}){fixture_tag} - not found in the simulator")

    def _detect_object_joints(self, obj_name: str) -> List[Dict]:
        """Find adjustable joints for an object."""
        return joint_control.detect_object_joints(self.env, obj_name)

    def render_frame(self):
        """Render the main camera view."""
        if self.env is None or not hasattr(self.env, 'sim'):
            return np.zeros((self.window_height, self.window_width, 3), dtype=np.uint8)

        try:
            frame = self.env.sim.render(
                width=self.window_width,
                height=self.window_height,
                camera_name="agentview"
            )

            if frame is None:
                return np.zeros((self.window_height, self.window_width, 3), dtype=np.uint8)

            # Flip vertically to convert MuJoCo's OpenGL image origin.
            frame = frame[::-1, :, :]

            # Flip horizontally to match the editor's screen coordinates.
            frame = frame[:, ::-1, :]

            return frame
        except Exception as e:
            return np.zeros((self.window_height, self.window_width, 3), dtype=np.uint8)

    def render_dual_frames(self):
        """Render the main and wrist camera views."""
        if self.env is None or not hasattr(self.env, 'sim'):
            black_frame = np.zeros((self.window_height, self.window_width, 3), dtype=np.uint8)
            return black_frame, black_frame

        try:
            frame_main = self.env.sim.render(
                width=self.window_width,
                height=self.window_height,
                camera_name="agentview"
            )

            frame_wrist = self.env.sim.render(
                width=self.window_width,
                height=self.window_height,
                camera_name="robot0_eye_in_hand"
            )

            if frame_main is not None:
                frame_main = frame_main[::-1, :, :]
                frame_main = frame_main[:, ::-1, :]
            else:
                frame_main = np.zeros((self.window_height, self.window_width, 3), dtype=np.uint8)

            if frame_wrist is not None:
                frame_wrist = frame_wrist[::-1, :, :]
                frame_wrist = frame_wrist[:, ::-1, :]
            else:
                frame_wrist = np.zeros((self.window_height, self.window_width, 3), dtype=np.uint8)

            return frame_main, frame_wrist

        except Exception as e:
            black_frame = np.zeros((self.window_height, self.window_width, 3), dtype=np.uint8)
            return black_frame, black_frame

    def update_frame(self):
        """Update the displayed frame."""
        try:
            # Continue rendering after an environment switch to show new objects immediately.
            env_switched = FrameUpdater.handle_environment_switch(self)
            if env_switched:
                self._force_refresh_frames = max(self._force_refresh_frames, 0)

            FrameUpdater.process_joint_changes(self)

            FrameUpdater.auto_save_workspace(self)

            if self.env is None or not hasattr(self.env, 'sim'):
                black_frame = np.zeros((self.window_height, self.window_width, 3), dtype=np.uint8)
                self.im.set_data(black_frame)
                self.im_wrist.set_data(black_frame)
                return

            frame = None

            if not hasattr(self, '_last_update_state'):
                self._last_update_state = None
            current_state = (self.ai_mode, self.free_mode, self.is_dragging,
                           bool(self.ai_controller and self.ai_controller.is_executing),
                           bool(self.ai_controller and self.ai_controller.execution_done))
            if current_state != self._last_update_state:
                self._last_update_state = current_state

            if self.data_collection_mode:
                frame_main, frame_wrist = self.render_dual_frames()
                frame = frame_main
            elif self.ai_mode:
                if self.ai_controller:
                    self.ai_controller.tick()
                frame = self.render_frame()
            elif not self.free_mode and not self.is_dragging:
                FrameUpdater.run_physics_simulation(self)
                frame = self.render_frame()
            elif self.free_mode:
                FrameUpdater.run_free_mode_forward(self)
                frame = self.render_frame()
            else:
                frame = self.render_frame()

            if frame is None:
                print(f"[WARNING] update_frame: no frame assigned; ai_mode={self.ai_mode}, free_mode={self.free_mode}, is_dragging={self.is_dragging}")
                frame = self.render_frame()

            if hasattr(self, '_force_refresh_frames') and self._force_refresh_frames > 0:
                print(f"[update_frame] Forced refresh {11-self._force_refresh_frames} ({self._force_refresh_frames} frames remaining)")

                self.im.set_array(frame)

                try:
                    self.fig.canvas.draw()
                    self.fig.canvas.flush_events()

                    try:
                        tk_widget = self.fig.canvas.get_tk_widget()
                        tk_widget.update_idletasks()
                        tk_widget.update()
                    except:
                        pass

                except Exception as e:
                    pass

                self._force_refresh_frames -= 1

                if self._force_refresh_frames == 0:
                    sys.stdout.flush()
            else:
                if 'frame_wrist' in locals():
                    self.im.set_data(frame)
                    self.im_wrist.set_data(frame_wrist)
                else:
                    frame_main, frame_wrist = self.render_dual_frames()
                    self.im.set_data(frame_main)
                    self.im_wrist.set_data(frame_wrist)
                    frame = frame_main

                if not hasattr(self, '_normal_render_count'):
                    self._normal_render_count = 0
                self._normal_render_count += 1

            for marker in self.object_markers:
                try:
                    marker.remove()
                except:
                    pass
            self.object_markers = []


            if self.selected_object and self.ui_style == "classic":
                kb_hint = self.ax.text(20, 60,
                                      "NumPad: 8246:XY | 50:Z | 79:Yaw | */:Roll | 13:Pitch",
                                      color='yellow', fontsize=8,
                                      bbox=dict(boxstyle='round,pad=0.3',
                                              facecolor='black', alpha=0.8))
                self.object_markers.append(kb_hint)

            status_text = f"Objects: {len(self.object_info)}"

            if self.ai_mode:
                mode_text = "AI (Auto)"
            elif self.data_collection_mode:
                mode_text = "HUMAN (Data Collection)"
            elif self.free_mode:
                mode_text = "FREE (No Physics)"
            else:
                mode_text = "PHYSICS (Full)"
            status_text += f" | Mode: {mode_text}"

            if self.selected_object:
                info = self.object_info.get(self.selected_object)
                if info:
                    pos = info['pos']
                    status_text += f" | Selected: {self.selected_object} ({pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f})"
                    if self.free_mode and self.keyboard_control_active:
                        status_text += " [KB CTRL]"

            self.ax.set_title('')
            if self.ui_style == 'classic':
                self.ax.set_xlabel(status_text, fontsize=9, family='DejaVu Sans')

            if self.ai_mode and self.ai_controller:
                if not hasattr(self, '_ai_status_update_counter'):
                    self._ai_status_update_counter = 0
                self._ai_status_update_counter += 1

                if self._ai_status_update_counter >= 10:
                    self._init_hotkey_panel()
                    self._ai_status_update_counter = 0

            if not self.ai_mode and not self.free_mode and self.physics_safety_monitor:
                if not hasattr(self, '_physics_status_update_counter'):
                    self._physics_status_update_counter = 0
                self._physics_status_update_counter += 1

                if self._physics_status_update_counter >= 10:
                    self._init_hotkey_panel()
                    self._physics_status_update_counter = 0

            self.fig.canvas.draw_idle()
        except Exception as e:
            print(f"Frame update failed: {e}")

    def world_to_screen(self, world_x: float, world_y: float) -> Tuple[int, int]:
        """Convert world coordinates to screen coordinates."""
        return coordinate_utils.world_to_screen(
            world_x, world_y,
            self.window_width, self.window_height,
            self._calibration_params_x, self._calibration_params_y
        )

    def screen_to_world(self, screen_x: int, screen_y: int) -> Tuple[float, float]:
        """Convert screen coordinates to world coordinates."""
        return coordinate_utils.screen_to_world(
            screen_x, screen_y,
            self.window_width, self.window_height,
            self._calibration_params_x, self._calibration_params_y
        )

    def get_3d_position_from_mouse(self, screen_x: int, screen_y: int, target_height: float) -> Optional[np.ndarray]:
        """Use ray casting to map a mouse position to world coordinates."""
        return coordinate_utils.get_3d_position_from_mouse(
            self.env, screen_x, screen_y, target_height,
            self.window_width, self.window_height
        )

    def get_object_at_position(self, screen_x: int, screen_y: int, select_parent: bool = False) -> Optional[tuple]:
        """Pick the visible body under a pixel in the main camera."""
        if self.env is None or not hasattr(self.env, "sim"):
            return None
        try:
            import mujoco
            sim = self.env.sim
            model, data = sim.model, sim.data
            camera_id = model.camera_name2id("agentview")
            ndc_x = 2.0 * (self.window_width - 1 - screen_x) / self.window_width - 1.0
            ndc_y = 1.0 - 2.0 * screen_y / self.window_height
            half_height = np.tan(np.deg2rad(model.cam_fovy[camera_id]) / 2.0)
            direction = np.array([
                ndc_x * half_height * self.window_width / self.window_height,
                ndc_y * half_height, -1.0,
            ])
            direction = data.cam_xmat[camera_id].reshape(3, 3) @ direction
            direction /= np.linalg.norm(direction)
            context = getattr(sim, "_render_context_offscreen", None)
            groups = context.vopt.geomgroup if context is not None else None
            geom_id = np.array([-1], dtype=np.int32)
            distance = mujoco.mj_ray(
                m=model._model, d=data._data, pnt=data.cam_xpos[camera_id].copy(),
                vec=direction, geomgroup=groups, flg_static=1,
                bodyexclude=-1, geomid=geom_id,
            )
            if distance < 0 or not 0 <= geom_id[0] < model.ngeom:
                return None
            body_id = int(model.geom_bodyid[geom_id[0]])
            for name, info in self.object_info.items():
                if name in ("main_table", "floor"):
                    continue
                if body_id == info["body_id"] or body_id in info.get("all_body_ids", []):
                    return name, info["body_id"] if select_parent else body_id
        except Exception as error:
            print(f"Object picking failed: {error}")
            if select_parent:
                name = self._fallback_get_object_at_position(screen_x, screen_y)
                if name is not None:
                    return name, self.object_info[name]["body_id"]
        return None

    def _fallback_get_object_at_position(self, screen_x: int, screen_y: int) -> Optional[str]:
        """Pick an object by coordinates when segmentation is unavailable."""
        world_x, world_y = self.screen_to_world(screen_x, screen_y)

        min_dist = float('inf')
        closest_obj = None

        for obj_name, info in self.object_info.items():
            pos = info['pos']
            dist = np.sqrt((pos[0] - world_x)**2 + (pos[1] - world_y)**2)
            if dist < min_dist and dist < 0.2:
                min_dist = dist
                closest_obj = obj_name

        if closest_obj:
            print(f"Selected object (fallback): {closest_obj} (distance: {min_dist:.3f})")

        return closest_obj

    def _apply_highlight(self, obj_name: str, specific_body_id: Optional[int] = None):
        """Highlight a specific component body, or every body of the object if omitted."""
        if obj_name not in self.object_info:
            return

        info = self.object_info[obj_name]
        model = self.env.sim.model

        self._original_colors[obj_name] = {}

        if specific_body_id is not None:
            body_ids_to_highlight = [specific_body_id]
            body_name = model.body_id2name(specific_body_id)
            print(f"   Highlighting component: {body_name}")
        else:
            body_ids_to_highlight = [info['body_id']]
            if 'all_body_ids' in info:
                body_ids_to_highlight = info['all_body_ids']
            print(f"   Highlighting whole object ({len(body_ids_to_highlight)} bodies)")

        for geom_id in range(model.ngeom):
            body_id = model.geom_bodyid[geom_id]
            if body_id in body_ids_to_highlight:
                original_rgba = model.geom_rgba[geom_id].copy()
                self._original_colors[obj_name][geom_id] = original_rgba

                model.geom_rgba[geom_id] = np.array([1.0, 0.9, 0.3, 1.0])

    def _remove_highlight(self, obj_name: str):
        """Restore the original object colors."""
        if obj_name not in self._original_colors:
            return

        model = self.env.sim.model

        for geom_id, original_rgba in self._original_colors[obj_name].items():
            if geom_id < model.ngeom:
                model.geom_rgba[geom_id] = original_rgba

        del self._original_colors[obj_name]

    def _euler_to_quaternion(self, roll: float, pitch: float, yaw: float) -> np.ndarray:
        """Convert roll, pitch, and yaw in radians to a [w, x, y, z] quaternion."""
        cy = np.cos(yaw * 0.5)
        sy = np.sin(yaw * 0.5)
        cp = np.cos(pitch * 0.5)
        sp = np.sin(pitch * 0.5)
        cr = np.cos(roll * 0.5)
        sr = np.sin(roll * 0.5)

        # Compose rotations in ZYX order.
        w = cr * cp * cy + sr * sp * sy
        x = sr * cp * cy - cr * sp * sy
        y = cr * sp * cy + sr * cp * sy
        z = cr * cp * sy - sr * sp * cy

        return np.array([w, x, y, z])

    def _quaternion_multiply(self, q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
        """Multiply two [w, x, y, z] quaternions."""
        w1, x1, y1, z1 = q1
        w2, x2, y2, z2 = q2

        w = w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2
        x = w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2
        y = w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2
        z = w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2

        return np.array([w, x, y, z])

    def move_object_6dof(self, obj_name: str, dx: float = 0, dy: float = 0, dz: float = 0,
                        droll: float = 0, dpitch: float = 0, dyaw: float = 0) -> bool:
        """Apply position deltas in meters and Euler-angle deltas in radians; return success."""
        if obj_name not in self.object_info:
            return False

        immovable_fixtures = ['main_table', 'floor']
        if obj_name in immovable_fixtures:
            print(f"{obj_name} is part of the infrastructure and cannot be moved")
            return False

        try:
            info = self.object_info[obj_name]
            body_id = info['body_id']
            has_free_joint = info.get('has_free_joint', True)

            if not has_free_joint:
                print(f"  {obj_name} is static; 6-DOF movement is unavailable")
                print(f"     Press O to adjust its joints, such as drawers or doors")
                return False

            joint_id = self.env.sim.model.body_jntadr[body_id]
            if joint_id >= 0:
                qpos_idx = self.env.sim.model.jnt_qposadr[joint_id]
                qpos = self.env.sim.data.qpos.copy()

                jnt_type = self.env.sim.model.jnt_type[joint_id]

                # A free joint stores three position values and a wxyz quaternion.
                if jnt_type == 0:  # free joint
                    qpos[qpos_idx:qpos_idx+3] += np.array([dx, dy, dz])

                    if droll != 0 or dpitch != 0 or dyaw != 0:
                        current_quat = qpos[qpos_idx+3:qpos_idx+7].copy()

                        delta_quat = self._euler_to_quaternion(droll, dpitch, dyaw)

                        new_quat = self._quaternion_multiply(current_quat, delta_quat)

                        new_quat /= np.linalg.norm(new_quat)

                        qpos[qpos_idx+3:qpos_idx+7] = new_quat
                else:
                    qpos[qpos_idx:qpos_idx+3] += np.array([dx, dy, dz])

                self.env.sim.data.qpos[:] = qpos

                if self.free_mode:
                    self.env.sim.forward()
                else:
                    # Preserve arm and gripper state while applying physics to the object.
                    robot_qpos_size = 9
                    robot_qpos = self.env.sim.data.qpos[:robot_qpos_size].copy()
                    robot_qvel = self.env.sim.data.qvel[:robot_qpos_size].copy()

                    for _ in range(3):
                        self.env.sim.data.qpos[:robot_qpos_size] = robot_qpos
                        self.env.sim.data.qvel[:robot_qpos_size] = robot_qvel
                        self.env.sim.step()

                    self.env.sim.data.qpos[:robot_qpos_size] = robot_qpos
                    self.env.sim.data.qvel[:robot_qpos_size] = robot_qvel
                    self.env.sim.forward()

                actual_pos = self.env.sim.data.body_xpos[body_id].copy()
                self.object_info[obj_name]['pos'] = tuple(actual_pos)

                self._workspace_needs_save = True

                return True
            return False
        except Exception as e:
            print(f"Movement failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def move_object(self, obj_name: str, new_x: float, new_y: float, new_z: Optional[float] = None) -> bool:
        """Move an object with collisions enabled while preserving the robot state."""
        if obj_name not in self.object_info:
            return False

        immovable_fixtures = ['main_table', 'floor']
        if obj_name in immovable_fixtures:
            print(f"{obj_name} is part of the infrastructure and cannot be moved")
            return False

        try:
            info = self.object_info[obj_name]
            body_id = info['body_id']
            current_pos = self.env.sim.data.body_xpos[body_id].copy()
            has_free_joint = info.get('has_free_joint', True)

            if new_z is None:
                new_z = current_pos[2]

            new_pos = np.array([new_x, new_y, new_z])

            if not has_free_joint:
                print(f"  {obj_name} is static; trying mocap movement...")

                try:
                    mocap_id = self.env.sim.model.body_mocapid[body_id]
                    if mocap_id >= 0:
                        self.env.sim.data.mocap_pos[mocap_id] = new_pos
                        self.env.sim.forward()
                        print(f"  Moved using mocap")
                        return True
                except:
                    pass

                print(f"  {obj_name} is a fixed fixture and cannot be moved")
                print(f"     Press O to adjust its joints, such as drawers or doors")
                return False

            joint_id = self.env.sim.model.body_jntadr[body_id]
            if joint_id >= 0:
                qpos_idx = self.env.sim.model.jnt_qposadr[joint_id]

                robot_qpos_size = 9

                robot_qpos = self.env.sim.data.qpos[:robot_qpos_size].copy()
                robot_qvel = self.env.sim.data.qvel[:robot_qpos_size].copy()

                qpos = self.env.sim.data.qpos.copy()
                qpos[qpos_idx:qpos_idx+3] = new_pos
                self.env.sim.data.qpos[:] = qpos

                qvel = self.env.sim.data.qvel.copy()
                qvel[qpos_idx:qpos_idx+3] = 0
                self.env.sim.data.qvel[:] = qvel

                if self.free_mode:
                    self.env.sim.forward()
                else:
                    for _ in range(3):
                        self.env.sim.data.qpos[:robot_qpos_size] = robot_qpos
                        self.env.sim.data.qvel[:robot_qpos_size] = robot_qvel
                        self.env.sim.step()

                    self.env.sim.data.qpos[:robot_qpos_size] = robot_qpos
                    self.env.sim.data.qvel[:robot_qpos_size] = robot_qvel
                    self.env.sim.forward()

                actual_pos = self.env.sim.data.body_xpos[body_id].copy()
                self.object_info[obj_name]['pos'] = tuple(actual_pos)

                self._workspace_needs_save = True

                return True
            return False
        except Exception as e:
            print(f"Movement failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def on_mouse_press(self, event):
        """Handle a mouse press."""
        if hasattr(self, 'instruction_ax') and hasattr(self, '_textbox_editing'):
            if event.inaxes == self.instruction_ax:
                self._textbox_editing = True
            else:
                if self._textbox_editing:
                    self._textbox_editing = False
                    try:
                        if hasattr(self, 'instruction_textbox') and self.instruction_textbox is not None:
                            self.instruction_textbox.stop_typing()
                    except:
                        pass

        MouseHandler.handle_mouse_press(self, event)

    def on_mouse_release(self, event):
        """Handle a mouse release."""
        MouseHandler.handle_mouse_release(self, event)

    def on_mouse_scroll(self, event):
        """Adjust object height with the scroll wheel."""
        MouseHandler.handle_mouse_scroll(self, event)

    def on_mouse_move(self, event):
        """Drag the selected object using ray casting."""
        MouseHandler.handle_mouse_move(self, event)

    def on_key_press(self, event):
        """Handle keyboard shortcuts."""
        if self._object_change_pending:
            return
        # Do not dispatch scene shortcuts while the instruction field has focus.
        if hasattr(self, '_textbox_editing') and self._textbox_editing:
            if event.key == 'escape':
                self._textbox_editing = False
                try:
                    if hasattr(self, 'instruction_textbox') and self.instruction_textbox is not None:
                        self.instruction_textbox.stop_typing()
                except:
                    pass
                self.fig.canvas.draw_idle()
                print("  Exited instruction editing")
            return

        if self.studio is not None and event.key == "h":
            self.studio.show_help()
            return

        if self.calibration_mode:
            return

        if self.ai_mode:
            if event.key == 'enter':
                self.start_ai_run()
                return
            elif event.key == 'p':
                if self.ai_controller:
                    self.ai_controller.toggle_pause()
                    self._init_hotkey_panel()
                return
            elif event.key == 'r':
                if self.ai_controller:
                    self.ai_controller.replay()
                return
            elif event.key == 's' or event.key == 'S':
                if self.ai_controller and self.ai_controller.execution_done:
                    self._save_all_ai_data()
                else:
                    print("  Wait for the AI rollout to finish before saving")
                return
            elif event.key == ' ':
                self.exit_ai_mode()
                return
            else:
                return

        # Handle Human Assist input before global Enter shortcuts.
        if self.data_collection_mode:
            if self.data_collector:
                if event.key == ' ':
                    self.exit_data_collection_mode(save=True)
                    return

                if event.key == 'escape':
                    self.exit_data_collection_mode(save=False)
                    return

                self.data_collector.handle_numpad_input(event.key, event)
            return

        # Check multiple possible key representations for Shift+Enter
        if event.key in ['ctrl+enter', 'ctrl+m', '\r']:
            if not self.free_mode and not self.ai_mode and not self.data_collection_mode:
                self.enter_ai_mode()
                return
            else:
                print("  ⚠️  Can only enter AI mode from PHYSICS mode")
                return

        if KeyboardHandler.handle_6dof_control(self, event.key, event):
            return

        KeyboardHandler.handle_global_keys(self, event.key)

    def enter_ai_mode(self, vla_model_path=None):
        """Prepare AI controls without advancing the scene or connecting a policy."""
        if self.ai_mode:
            return True
        if self.free_mode:
            return False
        if not self.editor.parsed_dict.get("goal_state"):
            message = "Define a task goal before starting AI policy."
            if self.studio:
                self.studio.log(message, error=True)
            else:
                print(message)
            return False
        model_path = vla_model_path or self.vla_model_path
        if self.ai_controller is None:
            self.ai_controller = AIController(self, model_path)
        if not self.ai_controller.enter_ai_mode():
            return False
        self.ai_mode = self.ai_hotkeys_disabled = True
        self.ai_video_frames, self.ai_video_wrist_frames = [], []
        self.ai_video_saved = False
        self._init_hotkey_panel()
        return True

    def start_ai_run(self):
        """Start the prepared policy episode after an explicit user action."""
        if not self.ai_mode or not self.ai_controller:
            return False
        if not self.editor.parsed_dict.get("goal_state"):
            self.ai_controller._log("Define a task goal before starting AI policy.", error=True)
            return False
        if not self.ai_controller.start_run():
            return False
        self.ai_video_frames, self.ai_video_wrist_frames = [], []
        self.ai_video_saved = False
        self.ai_video_dir = Path(__file__).resolve().parent / "datasets" / "video"
        self.ai_video_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.ai_video_path = self.ai_video_dir / f"temp_{timestamp}.mp4"
        self._init_hotkey_panel()
        return True

    def _save_ai_video(self):
        """Save main and wrist camera rollout videos in a shared output directory."""
        if len(self.ai_video_frames) == 0:
            return

        try:
            task_name = self.get_current_instruction().replace(" ", "_").replace("/", "_").replace("\\", "_")[:50]

            success_status = "True" if self.task_success else "False"

            violation_count = 0
            if hasattr(self, 'physics_safety_monitor') and self.physics_safety_monitor:
                all_events = self.physics_safety_monitor.get_all_events()
                violation_count = len(all_events) if all_events else 0

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

            subfolder_name = f"{task_name}_{success_status}_{violation_count}_{timestamp}"
            subfolder_path = self.ai_video_dir / subfolder_name
            subfolder_path.mkdir(parents=True, exist_ok=True)

            final_video_path = subfolder_path / "agentview.mp4"

            video_writer = imageio.get_writer(str(final_video_path), fps=30)
            for frame in self.ai_video_frames:
                if frame.dtype != np.uint8:
                    frame = np.clip(frame, 0, 255).astype(np.uint8)
                video_writer.append_data(frame)
            video_writer.close()

            self.ai_video_path = final_video_path

            if len(self.ai_video_wrist_frames) > 0:
                final_wrist_video_path = subfolder_path / "eye_in_hand.mp4"

                wrist_video_writer = imageio.get_writer(str(final_wrist_video_path), fps=30)
                for frame in self.ai_video_wrist_frames:
                    if frame.dtype != np.uint8:
                        frame = np.clip(frame, 0, 255).astype(np.uint8)
                    wrist_video_writer.append_data(frame)
                wrist_video_writer.close()

                self.ai_video_wrist_path = final_wrist_video_path

            # _save_all_ai_data saves safety events alongside the videos.

        except Exception as e:
            print(f"  Could not save video: {e}")
            import traceback
            traceback.print_exc()

    def _save_safety_events(self):
        """Save safety events as JSON alongside the rollout videos."""
        try:
            if not hasattr(self, 'physics_safety_monitor') or not self.physics_safety_monitor:
                print("  ⚠️  Global Safety Monitor not initialized, cannot save safety events")
                return

            safety_monitor = self.physics_safety_monitor
            all_events = safety_monitor.get_all_events()
            summary = safety_monitor.get_events_summary()

            if self.ai_video_path is None:
                return

            safety_json_path = self.ai_video_path.parent / "safety_events.json"

            import json
            safety_data = {
                "video_path": str(self.ai_video_path),
                "total_events": len(all_events),
                "summary": summary,
                "events": all_events,
                "config_path": safety_monitor.config_path,
                "rules": safety_monitor.config_rules,
                "rule_results": safety_monitor.rule_results,
                "monitor_status": safety_monitor.get_status(),
            }

            with open(safety_json_path, 'w', encoding='utf-8') as f:
                json.dump(safety_data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            print(f"  Could not save safety events: {e}")
            import traceback
            traceback.print_exc()

    def _save_all_ai_data(self):
        """Save completed rollout videos, safety events, RLDS data, and dataset metadata."""
        if not self.ai_controller or not self.ai_controller.execution_done:
            print("  The AI rollout has not finished; data cannot be saved yet")
            return

        if self.ai_video_saved:
            print("  Data has already been saved")
            return

        print(f"\n{'='*70}")
        print(f"Saving AI rollout data...")
        print(f"{'='*70}")

        try:
            if len(self.ai_video_frames) > 0:
                print(f"  Saving videos...")
                self._save_ai_video()
                print(f"  Videos saved")
            else:
                print(f"  No video frames to save")

            print(f"  Saving safety events...")
            self._save_safety_events()
            print(f"  Safety events saved")

            if self.ai_controller.rlds_exporter and self.ai_controller.rlds_collector and len(self.ai_controller.rlds_exporter.episode_data) > 0:
                print(f"  Saving RLDS data...")
                try:
                    task_name = self.get_current_instruction().replace(" ", "_").replace("/", "_").replace("\\", "_")[:50]

                    violation_count = 0
                    if hasattr(self, 'physics_safety_monitor') and self.physics_safety_monitor:
                        all_events = self.physics_safety_monitor.get_all_events()
                        violation_count = len(all_events) if all_events else 0

                    rlds_path = self.ai_controller.rlds_exporter.save_to_hdf5(
                        task_name=task_name,
                        success=self.task_success,
                        violation_count=violation_count
                    )
                    print(f"  RLDS data saved: {rlds_path}")

                    safety_events_path = None
                    video_path = None

                    if hasattr(self, 'ai_video_path') and self.ai_video_path:
                        video_path_obj = Path(self.ai_video_path)
                        video_path = str(video_path_obj)
                        safety_events_path = str(video_path_obj.parent / "safety_events.json")

                    try:
                        info_path = self.ai_controller.rlds_exporter.save_dataset_info(
                            rlds_path=rlds_path,
                            safety_events_path=safety_events_path,
                            video_path=video_path
                        )
                        print(f"  Dataset description saved: {info_path}")
                    except Exception as e:
                        print(f"  Could not save dataset description: {e}")
                        import traceback
                        traceback.print_exc()
                except Exception as e:
                    print(f"  Could not save RLDS data: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"  RLDS collector is not initialized or contains no data")

            self.ai_video_saved = True

            print(f"{'='*70}")
            print(f"All rollout data saved")
            print(f"{'='*70}\n")

        except Exception as e:
            print(f"  Could not save rollout data: {e}")
            import traceback
            traceback.print_exc()

    def exit_ai_mode(self):
        """Leave AI mode and restore editor state."""
        if not self.ai_mode:
            return

        print(f"\n{'='*70}")
        print(f"Exiting AI mode (editor)")
        print(f"{'='*70}\n")
        print(f"  Current state: ai_mode={self.ai_mode}, ai_controller={self.ai_controller is not None}")

        if not self.ai_video_saved and len(self.ai_video_frames) > 0:
            print(f"\nUnsaved rollout data: press S to save videos, safety events, and RLDS data")

        self.ai_video_frames = []
        self.ai_video_wrist_frames = []
        self.ai_video_saved = False

        # Restore the environment before clearing editor mode flags.
        if self.ai_controller:
            try:
                self.ai_controller.exit_ai_mode(reset_robot=True)
                print(f"  AI controller stopped and scene state restored")
            except Exception as e:
                print(f"  Could not stop the AI controller: {e}")
                import traceback
                traceback.print_exc()

        # Reset editor flags even if controller cleanup fails.
        print(f"\n  Resetting editor state...")
        self.ai_mode = False
        self.ai_hotkeys_disabled = False
        self.free_mode = False
        self.is_dragging = False
        self.selected_object = None

        self._init_hotkey_panel()

        self._force_refresh_frames = 0

        self.ai_mode = False

        try:
            frame_main, frame_wrist = self.render_dual_frames()
            self.im.set_data(frame_main)
            self.im_wrist.set_data(frame_wrist)
            self.fig.canvas.draw_idle()
        except Exception as e:
            print(f"  GUI refresh failed: {e}")
            import traceback
            traceback.print_exc()


    def show_all_joints_info(self):
        """Print joint diagnostics for all objects."""
        print(f"\n{'='*70}")
        print(f"Object joint information")
        print(f"{'='*70}\n")

        has_joints = False
        for obj_name, info in sorted(self.object_info.items()):
            joints = info.get('joints', [])
            is_fixture = info.get('is_fixture', False)
            has_free_joint = info.get('has_free_joint', True)

            if joints or not has_free_joint:
                has_joints = True
                fixture_tag = " [FIXTURE]" if is_fixture else ""
                static_tag = " [STATIC]" if not has_free_joint else ""
                print(f"📦 {obj_name}{fixture_tag}{static_tag}")

                if not has_free_joint:
                    print(f"   Static object: position is fixed, but joints may be adjustable")

                if joints:
                    print(f"   Adjustable joints ({len(joints)}):")
                    for j in joints:
                        jtype = j['type']
                        jrange = j.get('range', None)
                        current = j.get('current_pos', 0)
                        range_str = f"[{jrange[0]:.3f} ~ {jrange[1]:.3f}]" if jrange else "[unlimited]"
                        print(f"      • {j['name']}")
                        print(f"        Type: {jtype}  Range: {range_str}  Current: {current:.3f}")
                else:
                    print(f"   No adjustable joints")
                print()

        if not has_joints:
            print("  No adjustable joints found in the scene")
            print("     Drawers, doors, and microwaves require articulated MuJoCo models")

        print(f"{'='*70}")
        print(f"Tips:")
        print(f"   - Press O to adjust the selected object's joints")
        print(f"   - [STATIC] objects have fixed positions but may have adjustable joints")
        print(f"   - [FIXTURE] marks scene fixtures such as cabinets and stoves")
        print(f"{'='*70}\n")

    def save_bddl(self, output_path: Optional[str] = None, auto_create_regions: bool = True) -> str:
        """Save object positions to BDDL, optionally creating missing regions."""
        success_count = 0
        failed_objects = []
        created_regions = []

        for obj_name, info in self.object_info.items():
            try:
                pos = info['pos']
                self.editor.move_object(obj_name, new_position=(pos[0], pos[1]))
                print(f"Updated {obj_name} position: ({pos[0]:.4f}, {pos[1]:.4f}, {pos[2]:.4f})")
                success_count += 1

            except ValueError as e:
                if auto_create_regions and "No region found" in str(e) and "for object " in str(e):
                    try:
                        # Create only the missing region, without duplicating the object definition.
                        print(f"Creating a region for {obj_name}...")

                        region_name = f"main_table_{obj_name}_region"
                        x, y = pos[0], pos[1]
                        half_len = 0.02  # Region half-size in meters.

                        region_data = {
                            "target": "main_table",
                            "ranges": [[
                                x - half_len,
                                y - half_len,
                                x + half_len,
                                y + half_len
                            ]],
                            "extra": [],
                            "yaw_rotation": [0, 0],
                            "rgba": [0, 0, 1, 0]
                        }

                        self.editor.parsed_dict["regions"][region_name] = region_data

                        on_top_condition = f"onTop({obj_name}, {region_name})"
                        if on_top_condition not in self.editor.parsed_dict.get("initial_state", []):
                            if "initial_state" not in self.editor.parsed_dict:
                                self.editor.parsed_dict["initial_state"] = []
                            self.editor.parsed_dict["initial_state"].append(on_top_condition)

                        print(f"Created region for {obj_name}: {region_name}")
                        print(f"Updated {obj_name} position: ({pos[0]:.4f}, {pos[1]:.4f}, {pos[2]:.4f})")
                        success_count += 1
                        created_regions.append(obj_name)

                    except Exception as create_error:
                        failed_objects.append((obj_name, f"Could not create region: {create_error}"))
                        print(f"Could not create a region for {obj_name}: {create_error}")
                else:
                    failed_objects.append((obj_name, str(e)))
                    print(f"Skipped {obj_name}: {e}")

            except Exception as e:
                failed_objects.append((obj_name, str(e)))
                print(f"Could not update {obj_name}: {e}")

        if output_path is None:
            base_name = Path(self.bddl_file).stem

            if hasattr(self, 'custom_save_dir') and self.custom_save_dir:
                output_path = Path(self.custom_save_dir) / f"{base_name}_edited.bddl"
            else:
                output_path = Path(self.bddl_file).parent / f"{base_name}_edited.bddl"

        self.editor.save(str(output_path))

        print(f"\n{'='*70}")
        print(f"BDDL save results")
        print(f"{'='*70}")
        print(f"Updated objects: {success_count}")

        if created_regions:
            print(f"Created regions: {len(created_regions)}")
            for obj_name in created_regions:
                print(f"  • {obj_name}")

        if failed_objects:
            print(f"\nSkipped objects: {len(failed_objects)}")
            for obj_name, reason in failed_objects:
                print(f"  • {obj_name}: {reason}")
            print(f"\nPossible reasons for skipped objects:")
            print(f"  1. Fixtures do not require position updates")
            print(f"  2. The object type could not be inferred")
            print(f"  3. Simulator position changes for these objects were not written to BDDL")

        print(f"\nFile saved: {output_path}")
        print(f"{'='*70}\n")

        return str(output_path)

    def export_bddl_from_sim(self, output_path: Optional[str] = None) -> str:
        """Build a fresh BDDL file from simulator state to avoid duplicate definitions."""
        print(f"\n{'='*70}")
        print(f"Exporting a new BDDL file from the simulator")
        print(f"{'='*70}\n")

        from bddl_editor import BDDLEditor
        new_editor = BDDLEditor(None)

        new_editor.parsed_dict["problem_name"] = self.editor.parsed_dict.get("problem_name", "exported_scene")
        new_editor.parsed_dict["fixtures"] = self.editor.parsed_dict.get("fixtures", {}).copy()
        new_editor.parsed_dict["scene_properties"] = self.editor.parsed_dict.get("scene_properties", {}).copy()
        new_editor.parsed_dict["goal_state"] = self.editor.parsed_dict.get("goal_state", []).copy()
        new_editor.parsed_dict["language_instruction"] = self.editor.parsed_dict.get("language_instruction", []).copy()

        new_editor.parsed_dict["objects"] = {}
        new_editor.parsed_dict["regions"] = {}
        new_editor.parsed_dict["initial_state"] = []

        success_count = 0

        for obj_name, info in self.object_info.items():
            try:
                obj_type = info['type']
                pos = info['pos']

                if obj_type not in new_editor.parsed_dict["objects"]:
                    new_editor.parsed_dict["objects"][obj_type] = []
                if obj_name not in new_editor.parsed_dict["objects"][obj_type]:
                    new_editor.parsed_dict["objects"][obj_type].append(obj_name)

                region_name = f"main_table_{obj_name}_region"
                x, y = pos[0], pos[1]
                half_len = 0.02  # Region half-size in meters.

                region_data = {
                    "target": "main_table",
                    "ranges": [[
                        x - half_len,
                        y - half_len,
                        x + half_len,
                        y + half_len
                    ]],
                    "extra": [],
                    "yaw_rotation": [0, 0],
                    "rgba": [0, 0, 1, 0]
                }

                new_editor.parsed_dict["regions"][region_name] = region_data

                on_top_condition = f"onTop({obj_name}, {region_name})"
                new_editor.parsed_dict["initial_state"].append(on_top_condition)

                print(f"Exported {obj_name} ({obj_type}) at ({pos[0]:.4f}, {pos[1]:.4f}, {pos[2]:.4f})")
                success_count += 1

            except Exception as e:
                print(f"Skipped {obj_name}: {e}")

        if output_path is None:
            base_name = Path(self.bddl_file).stem
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

            if hasattr(self, 'custom_save_dir') and self.custom_save_dir:
                output_path = Path(self.custom_save_dir) / f"{base_name}_exported_{timestamp}.bddl"
            else:
                output_path = Path(self.bddl_file).parent / f"{base_name}_exported_{timestamp}.bddl"

        new_editor.save(str(output_path))

        print(f"\n{'='*70}")
        print(f"BDDL export results")
        print(f"{'='*70}")
        print(f"Exported objects: {success_count}")
        print(f"Created a new BDDL file that can be loaded directly")
        print(f"Object definitions and samplers were rebuilt to avoid duplicates")
        print(f"\nFile saved: {output_path}")
        print(f"{'='*70}\n")

        return str(output_path)

    def import_bddl(self):
        """Select a BDDL file using the file dialog."""
        import tkinter as tk
        from tkinter import filedialog

        print(f"\n{'='*70}")
        print(f"Import BDDL file")
        print(f"{'='*70}\n")

        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)

        if hasattr(self, 'bddl_file') and self.bddl_file:
            initial_dir = str(Path(self.bddl_file).parent)
        else:
            initial_dir = str(Path.cwd())

        file_path = filedialog.askopenfilename(
            title="Select BDDL File to Import",
            initialdir=initial_dir,
            filetypes=[
                ("BDDL files", "*.bddl"),
                ("All files", "*.*")
            ]
        )

        root.destroy()

        if not file_path:
            print("Import canceled")
            return

        print(f"Selected file: {file_path}")

        if not Path(file_path).exists():
            print(f"File not found: {file_path}")
            return

        import threading
        thread = threading.Thread(
            target=lambda: self._do_import_bddl(file_path),
            daemon=True
        )
        thread.start()

    def _do_import_bddl(self, bddl_file_path: str):
        """Prepare a BDDL import in the worker thread."""
        print(f"\n[Worker] Importing BDDL file...")
        print(f"[Worker] File: {bddl_file_path}\n")

        try:
            print(f"[Worker] Step 1/7: Saving workspace state...")
            if hasattr(self, 'env') and self.env is not None:
                self._auto_save_workspace_state()

            print(f"[Worker] Step 2/7: Loading BDDL...")
            new_editor = BDDLEditor(bddl_file_path)

            print(f"[Worker] Step 3/7: Creating environment...")
            # Keep policy observations at 256x256 independently of GUI rendering.
            new_env = OffScreenRenderEnv(
                bddl_file_name=bddl_file_path,
                camera_heights=256,
                camera_widths=256,
                has_renderer=False,
                has_offscreen_renderer=True,
                render_camera="agentview",
                use_camera_obs=True,
                control_freq=20,
            )

            print(f"[Worker] Step 4/7: Resetting environment...")
            new_env.reset()

            print(f"[Worker] Step 5/7: Initializing renderer...")
            for _ in range(5):
                _ = new_env.sim.render(
                    height=self.window_height,
                    width=self.window_width,
                    camera_name="agentview"
                )
                new_env.sim.forward()

            print(f"[Worker] Step 6/7: Preparing environment switch...")
            switch_data = {
                'new_env': new_env,
                'new_editor': new_editor,
                'new_bddl_file': bddl_file_path,
                'operation': 'import_bddl'
            }

            print(f"[Worker] Step 7/7: Notifying the main thread...")
            with self._env_switch_lock:
                self._new_env_ready = switch_data

            print(f"\n[Worker] BDDL import prepared")
            print(f"[Worker] Waiting for the main thread to switch environments...")

        except Exception as e:
            print(f"\n[Worker] Import failed: {e}")
            import traceback
            traceback.print_exc()

    def save_init_state(self, output_path: Optional[str] = None) -> str:
        """Save a scene bundle and return its pruned_init path.

        BDDL stores scene structure, pruned_init stores simulator state, and
        optional YAML metadata describes objects and the save timestamp.
        """
        print(f"\n{'='*70}")
        print(f"Saving scene bundle (BDDL + pruned_init)")
        print(f"{'='*70}\n")

        try:
            if self._workspace_needs_save or not self.current_state.exists():
                self._auto_save_workspace_state()
                self._workspace_needs_save = False
            else:
                print(f"  Workspace state is up to date")

            if output_path is None:
                base_name = Path(self.bddl_file).stem
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

                if hasattr(self, 'custom_save_dir') and self.custom_save_dir:
                    output_path = Path(self.custom_save_dir) / f"{base_name}_init_{timestamp}.pruned_init"
                else:
                    output_path = Path(self.bddl_file).parent / f"{base_name}_init_{timestamp}.pruned_init"

            shutil.copy2(str(self.current_state), str(output_path))

            bddl_output = Path(output_path).with_suffix('.bddl')
            shutil.copy2(str(self.current_bddl), str(bddl_output))

            meta_output = Path(output_path).with_suffix('.meta.yaml')
            metadata = {
                'version': '2.0',
                'timestamp': datetime.now().isoformat(),
                'bddl_file': str(self.bddl_file),
                'scene_name': Path(self.bddl_file).stem,
                'state_dimensions': {
                    'qpos': int(len(self.env.sim.data.qpos)),
                    'qvel': int(len(self.env.sim.data.qvel))
                },
                'objects': {},
                'fixtures': {},
                'robot': {
                    'qpos': self.env.sim.data.qpos[:9].tolist(),
                    'qvel': self.env.sim.data.qvel[:9].tolist()
                }
            }

            for obj_name, info in self.object_info.items():
                try:
                    body_id = info['body_id']
                    pos = self.env.sim.data.body_xpos[body_id].copy()
                    quat = self.env.sim.data.body_xquat[body_id].copy()

                    obj_data = {
                        'type': info['type'],
                        'body_id': int(body_id),
                        'position': {
                            'x': float(pos[0]),
                            'y': float(pos[1]),
                            'z': float(pos[2])
                        },
                        'quaternion': {
                            'w': float(quat[0]),
                            'x': float(quat[1]),
                            'y': float(quat[2]),
                            'z': float(quat[3])
                        }
                    }

                    if 'joints' in info and info['joints']:
                        obj_data['joints'] = {}
                        joints_data = info['joints']
                        if isinstance(joints_data, dict):
                            for joint_name, joint_info in joints_data.items():
                                qpos_addr = joint_info['qpos_addr']
                                obj_data['joints'][joint_name] = {
                                    'type': joint_info['type'],
                                    'range': joint_info['range'],
                                    'current_value': float(self.env.sim.data.qpos[qpos_addr]),
                                    'qpos_addr': int(qpos_addr)
                                }

                    if info.get('is_fixture', False):
                        metadata['fixtures'][obj_name] = obj_data
                    else:
                        metadata['objects'][obj_name] = obj_data

                except Exception as e:
                    print(f"  Could not save metadata for {obj_name}: {e}")

            with open(meta_output, 'w', encoding='utf-8') as f:
                yaml.dump(metadata, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

            state_tensor = torch.load(str(self.current_state))
            sim_state = self.env.sim.get_state()

            print(f"Scene bundle saved (BDDL + pruned_init)")
            print(f"State information:")
            print(f"  - State shape: {state_tensor.shape}")
            print(f"  - qpos size: {len(sim_state.qpos)}")
            print(f"  - qvel size: {len(sim_state.qvel)}")
            print(f"  - Objects: {len(metadata['objects'])}")
            print(f"  - Fixtures: {len(metadata['fixtures'])}")
            print(f"  - Data type: {state_tensor.dtype}")
            print(f"\nScene bundle files:")
            print(f"  .bddl          - Scene definition (objects, relations, goals)")
            print(f"  .pruned_init   - Simulator state")
            print(f"  .meta.yaml     - Human-readable metadata")
            print(f"\nTo load this scene:")
            print(f"  1. Press I to load the BDDL and pruned_init files together")
            print(f"  2. The environment will be created and its saved state restored")
            print(f"  3. BDDL and state files must remain paired ✅")
            print(f"\nState file: {output_path}")
            print(f"BDDL file: {bddl_output}")
            print(f"Metadata file: {meta_output}")
            print(f"Workspace backup: {self.workspace_dir / 'current.*'}")
            print(f"{'='*70}\n")

            return str(output_path)

        except Exception as e:
            print(f"Save failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def save_scene_to_folder(self) -> Optional[str]:
        """Save scene.bddl, scene.pruned_init, and scene.meta.yaml in a timestamped folder."""
        print(f"\n{'='*70}")
        print(f"Saving scene to the Scene directory")
        print(f"{'='*70}\n")

        try:
            scene_root = Path("Scene")
            scene_root.mkdir(exist_ok=True)

            base_name = Path(self.bddl_file).stem
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            scene_folder = scene_root / f"{base_name}_{timestamp}"
            scene_folder.mkdir(exist_ok=True)

            print(f"  Scene directory: {scene_folder}")

            # Always capture live simulator state; the workspace cache may be stale after dragging.
            print(f"  Saving simulator state...")
            self._auto_save_workspace_state()
            self._workspace_needs_save = False

            bddl_path = scene_folder / "scene.bddl"
            shutil.copy2(str(self.current_bddl), str(bddl_path))

            pruned_init_path = scene_folder / "scene.pruned_init"
            shutil.copy2(str(self.current_state), str(pruned_init_path))

            meta_path = scene_folder / "scene.meta.yaml"
            metadata = {
                'version': '3.0',
                'timestamp': datetime.now().isoformat(),
                'scene_name': base_name,
                'original_bddl': str(self.bddl_file),
                'state_dimensions': {
                    'qpos': int(len(self.env.sim.data.qpos)),
                    'qvel': int(len(self.env.sim.data.qvel))
                },
                'objects': {},
                'fixtures': {},
                'robot': {
                    'qpos': self.env.sim.data.qpos[:9].tolist(),
                    'qvel': self.env.sim.data.qvel[:9].tolist()
                }
            }

            for obj_name, info in self.object_info.items():
                try:
                    body_id = info['body_id']
                    pos = self.env.sim.data.body_xpos[body_id].copy()
                    quat = self.env.sim.data.body_xquat[body_id].copy()

                    obj_data = {
                        'type': info['type'],
                        'body_id': int(body_id),
                        'position': {
                            'x': float(pos[0]),
                            'y': float(pos[1]),
                            'z': float(pos[2])
                        },
                        'quaternion': {
                            'w': float(quat[0]),
                            'x': float(quat[1]),
                            'y': float(quat[2]),
                            'z': float(quat[3])
                        }
                    }

                    if 'joints' in info and info['joints']:
                        obj_data['joints'] = {}
                        joints_data = info['joints']
                        if isinstance(joints_data, dict):
                            for joint_name, joint_info in joints_data.items():
                                qpos_addr = joint_info['qpos_addr']
                                obj_data['joints'][joint_name] = {
                                    'type': joint_info['type'],
                                    'range': joint_info['range'],
                                    'current_value': float(self.env.sim.data.qpos[qpos_addr]),
                                    'qpos_addr': int(qpos_addr)
                                }

                    if info.get('is_fixture', False):
                        metadata['fixtures'][obj_name] = obj_data
                    else:
                        metadata['objects'][obj_name] = obj_data

                except Exception as e:
                    print(f"  Could not save metadata for {obj_name}: {e}")

            with open(meta_path, 'w', encoding='utf-8') as f:
                yaml.dump(metadata, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

            print(f"\nScene saved")
            print(f"Location: {scene_folder}")
            print(f"Contents:")
            print(f"  - Objects: {len(metadata['objects'])}")
            print(f"  - Fixtures: {len(metadata['fixtures'])}")
            print(f"  - State size: qpos={len(self.env.sim.data.qpos)}, qvel={len(self.env.sim.data.qvel)}")
            print(f"\nPress I to load this scene from the Scene directory")
            print(f"{'='*70}\n")

            return str(scene_folder)

        except Exception as e:
            print(f"Save failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def load_scene_from_folder(self):
        """Select a scene bundle directory with the file dialog."""
        import tkinter as tk
        from tkinter import filedialog

        print(f"\n{'='*70}")
        print(f"Load scene from the Scene directory")
        print(f"{'='*70}\n")

        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)

        scene_root = Path("Scene")
        if not scene_root.exists():
            scene_root.mkdir(exist_ok=True)

        folder_path = filedialog.askdirectory(
            title="Select a scene folder containing scene.bddl and scene.pruned_init",
            initialdir=str(scene_root)
        )

        root.destroy()

        if not folder_path:
            print("Load canceled")
            return

        import threading
        thread = threading.Thread(
            target=lambda: self._do_load_scene_from_folder(folder_path),
            daemon=True
        )
        thread.start()

    def _do_load_scene_from_folder(self, folder_path: str):
        """Load a scene bundle in the worker thread."""
        print(f"\n[Worker] Loading scene...")
        print(f"[Worker] Directory: {folder_path}\n")

        try:
            folder = Path(folder_path)

            bddl_path = folder / "scene.bddl"
            pruned_init_path = folder / "scene.pruned_init"
            meta_path = folder / "scene.meta.yaml"

            if not bddl_path.exists():
                print(f"Missing scene.bddl file")
                return

            print(f"[Worker] Step 1/5: Checking files...")
            print(f"  Found scene.bddl")

            has_pruned_init = pruned_init_path.exists()
            if has_pruned_init:
                print(f"  Found scene.pruned_init")
            else:
                print(f"  No scene.pruned_init found; the scene will be sampled from BDDL")

            if meta_path.exists():
                print(f"  Found scene.meta.yaml")

            print(f"\n[Worker] Step 2/5: Updating working BDDL...")
            shutil.copy2(str(bddl_path), str(self.current_bddl))
            print(f"  BDDL updated")

            print(f"\n[Worker] Step 3/5: Creating environment...")
            new_env = OffScreenRenderEnv(
                bddl_file_name=str(bddl_path),
                camera_heights=256,
                camera_widths=256,
                has_renderer=False,
                has_offscreen_renderer=True,
                render_camera="agentview",
                use_camera_obs=True,
                control_freq=20,
            )
            new_env.seed(0)
            new_env.reset()
            print(f"  Environment created")

            if has_pruned_init:
                print(f"\n[Worker] Step 4/5: Restoring saved state...")
                try:
                    state_tensor = torch.load(str(pruned_init_path))
                    sim_state = state_tensor.numpy()
                    new_env.sim.set_state_from_flattened(sim_state)
                    new_env.sim.forward()
                    print(f"  Scene state restored")
                except Exception as e:
                    print(f"  State restoration failed; using BDDL sampling: {e}")
            else:
                print(f"\n[Worker] Step 4/5: Sampling from BDDL...")
                print(f"  Scene sampled from BDDL")

            print(f"\n[Worker] Step 5/5: Initializing renderer...")
            for _ in range(5):
                _ = new_env.sim.render(
                    height=self.window_height,
                    width=self.window_width,
                    camera_name="agentview"
                )
                new_env.sim.forward()
            print(f"  Renderer initialized")

            print(f"\n[Worker] Preparing environment switch...")
            from bddl_editor import BDDLEditor
            new_editor = BDDLEditor(str(bddl_path))

            switch_data = {
                'new_env': new_env,
                'new_editor': new_editor,
                'new_bddl_file': str(bddl_path),
                'operation': 'load_scene_folder',
                'has_pruned_init': has_pruned_init
            }

            with self._env_switch_lock:
                self._new_env_ready = switch_data

            print(f"\n[Worker] Scene loaded")
            print(f"[Worker] Waiting for the main thread to switch environments...")

        except Exception as e:
            print(f"\n[Worker] Load failed: {e}")
            import traceback
            traceback.print_exc()

    def load_init_state(self, init_state_file: Optional[str] = None):
        """Restore simulator state from a pruned_init file, prompting for a path if omitted."""
        print(f"\n{'='*70}")
        print(f"Load initial state (.pruned_init)")
        print(f"{'='*70}\n")

        if init_state_file is None:
            import threading
            def get_input():
                try:
                    print("Enter the .pruned_init file path:")
                    print("  Example: ./scene_init_20251126_123456.pruned_init")
                    print("  Press Enter to cancel")

                    user_input = input("Path: ").strip()

                    if not user_input:
                        print("Load canceled")
                        return

                    self._do_load_init_state(user_input)

                except Exception as e:
                    print(f"Load failed: {e}")

            thread = threading.Thread(target=get_input, daemon=True)
            thread.start()
        else:
            self._do_load_init_state(init_state_file)

    def _do_load_init_state(self, init_state_file: str):
        """Perform the initial-state load."""
        from gui_modules.init_state_io import load_init_state_with_verification
        load_init_state_with_verification(self, init_state_file)

    def start_calibration(self):
        """Start interactive coordinate calibration."""
        self.calibration_mode = True
        self.calibration_points = []

        print(f"\n{'='*70}")
        print("Calibration started")
        print(f"{'='*70}")
        print("\nFollow these steps:")
        print("1. Find the green circles marking object positions")
        print("2. Click a point on an object precisely")
        print("3. Enter its reference in the terminal:")
        print("   - Object center: basket_1")
        print("   - Object corner: basket_1 top_left")
        print("   - World coordinates: 0.123 -0.456")
        print("4. Repeat steps 2-3 for at least 5 points")
        print("5. Press Enter to finish calibration")
        print("\nTips:")
        print("  - Use several corners of the same object, such as all four basket corners")
        print("  - Supported offsets include left, right, top, bottom, top_left, and top_right")
        print("  - Points may come from different objects")
        print("  - More reference points can improve accuracy; 10 or more are recommended")
        print("  - Press Esc to cancel calibration")
        print(f"{'='*70}\n")

        print("Available objects:")
        for i, obj_name in enumerate(self.object_info.keys(), 1):
            print(f"  {i}. {obj_name}")
        print()

    def handle_calibration_click(self, screen_x: int, screen_y: int):
        """Record a reference point for coordinate calibration."""
        print(f"\nClicked position: ({screen_x}, {screen_y})")
        print("Enter one of the following:")
        print("  1. Object name, such as basket_1")
        print("  2. Object name and offset, such as basket_1 left or basket_1 top_left")
        print("  3. World coordinates, such as 0.123 -0.456")
        print("  4. Press Enter to finish calibration or Esc to cancel")

        # Read terminal input in a worker to keep the GUI responsive.
        import threading
        def get_input():
            try:
                user_input = input("Input: ").strip()

                if not user_input:
                    import matplotlib.pyplot as plt
                    plt.pause(0.1)
                    self.finish_calibration()
                    return
                elif user_input.lower() == 'esc':
                    self.cancel_calibration()
                else:
                    parts = user_input.split()

                    if len(parts) >= 2 and self._is_float(parts[0]) and self._is_float(parts[1]):
                        world_x = float(parts[0])
                        world_y = float(parts[1])
                        self.calibration_points.append((screen_x, screen_y, world_x, world_y))
                        print(f"Recorded: screen ({screen_x}, {screen_y}) = world ({world_x:.3f}, {world_y:.3f})")
                        print(f"   Calibration points: {len(self.calibration_points)}")

                    elif parts[0] in self.object_info:
                        obj_name = parts[0]
                        info = self.object_info[obj_name]
                        center_x, center_y = info['pos'][0], info['pos'][1]

                        if len(parts) > 1:
                            offset = parts[1].lower()
                            obj_size = 0.05  # Approximate object radius as 5 cm for corner calibration.

                            offset_x, offset_y = 0, 0
                            if 'left' in offset:
                                offset_y = -obj_size
                            elif 'right' in offset:
                                offset_y = obj_size

                            if 'top' in offset or 'front' in offset:
                                offset_x = obj_size
                            elif 'bottom' in offset or 'back' in offset:
                                offset_x = -obj_size

                            world_x = center_x + offset_x
                            world_y = center_y + offset_y
                            print(f"Recorded: {obj_name} ({offset}) at screen ({screen_x}, {screen_y}) = world ({world_x:.3f}, {world_y:.3f})")
                        else:
                            world_x, world_y = center_x, center_y
                            print(f"Recorded: {obj_name} (center) at screen ({screen_x}, {screen_y}) = world ({world_x:.3f}, {world_y:.3f})")

                        self.calibration_points.append((screen_x, screen_y, world_x, world_y))
                        print(f"   Calibration points: {len(self.calibration_points)}")
                    else:
                        print(f"Object not found: {parts[0]}")
                        print("See the list of available objects above")
            except EOFError:
                self.finish_calibration()
            except Exception as e:
                print(f"Could not parse input: {e}")

        thread = threading.Thread(target=get_input, daemon=True)
        thread.start()

    def _is_float(self, s: str) -> bool:
        """Return whether the string represents a floating-point number."""
        try:
            float(s)
            return True
        except ValueError:
            return False

    def load_calibration_from_file(self):
        """Load calibration parameters from YAML."""
        try:
            if not self.calibration_file.exists():
                print(f"Calibration file not found: {self.calibration_file}")
                print("   Using defaults; a file will be created when calibration is saved")
                return

            with open(self.calibration_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            current_version = data.get('current_version', 'default')
            calibrations = data.get('calibrations', {})

            if current_version in calibrations:
                cal = calibrations[current_version]
                self._calibration_params_x = np.array(cal['params_x'])
                self._calibration_params_y = np.array(cal['params_y'])

                print(f"Loaded calibration: {current_version}")
                print(f"  Created: {cal.get('created_at', 'Unknown')}")
                print(f"  Reference points: {cal.get('num_points', 'Unknown')}")
                print(f"  Mean error: {cal.get('avg_error', 0):.4f}m")
            else:
                print(f"Calibration '{current_version}' not found; using defaults")

        except Exception as e:
            print(f"Could not load calibration: {e}")
            print("   Using default parameters")

    def save_calibration_to_file(self, version_name: str, description: str,
                                 params_x: np.ndarray, params_y: np.ndarray,
                                 num_points: int, avg_error: float, max_error: float):
        """Save calibration parameters as YAML."""
        try:
            if self.calibration_file.exists():
                with open(self.calibration_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
            else:
                data = {'current_version': 'default', 'calibrations': {}}

            data['calibrations'][version_name] = {
                'description': description,
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'num_points': num_points,
                'avg_error': float(avg_error),
                'max_error': float(max_error),
                'params_x': [float(x) for x in params_x],
                'params_y': [float(y) for y in params_y]
            }

            data['current_version'] = version_name

            with open(self.calibration_file, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

            print(f"Calibration saved: {self.calibration_file}")
            print(f"  Version: {version_name}")

        except Exception as e:
            print(f"Could not save calibration: {e}")

    def list_calibrations(self):
        """List saved calibrations."""
        try:
            if not self.calibration_file.exists():
                print("Calibration file not found")
                return

            with open(self.calibration_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            current = data.get('current_version', 'default')
            calibrations = data.get('calibrations', {})

            print(f"\n{'='*70}")
            print("Available calibrations:")
            print(f"{'='*70}")

            for i, (name, cal) in enumerate(calibrations.items(), 1):
                marker = "★" if name == current else " "
                print(f"{marker} {i}. {name}")
                print(f"     Description: {cal.get('description', 'N/A')}")
                print(f"     Created: {cal.get('created_at', 'N/A')}")
                print(f"     Points: {cal.get('num_points', 'N/A')}, "
                      f"error: {cal.get('avg_error', 0):.4f}m")

            print(f"{'='*70}\n")

        except Exception as e:
            print(f"Could not read calibration list: {e}")

    def finish_calibration(self):
        """Compute and apply the current calibration without saving it yet."""
        if len(self.calibration_points) < 3:
            print("\nAt least 3 calibration points are required; add more points or enter 'cancel'")
            return

        print(f"\n{'='*70}")
        print(f"Computing coordinate transform...")
        print(f"{'='*70}\n")

        import numpy as np

        screen_points = np.array([[p[0], p[1]] for p in self.calibration_points])
        world_points = np.array([[p[2], p[3]] for p in self.calibration_points])

        screen_norm = screen_points.copy()
        screen_norm[:, 0] = screen_norm[:, 0] / self.window_width - 0.5
        screen_norm[:, 1] = screen_norm[:, 1] / self.window_height - 0.5

        # Fit [world_x, world_y] = A * [screen_x, screen_y] + b by least squares.
        X = np.column_stack([screen_norm, np.ones(len(screen_norm))])
        params_x = np.linalg.lstsq(X, world_points[:, 0], rcond=None)[0]
        params_y = np.linalg.lstsq(X, world_points[:, 1], rcond=None)[0]

        print("Computed transform parameters:")
        print(f"  world_x = {params_x[0]:.6f} * norm_x + {params_x[1]:.6f} * norm_y + {params_x[2]:.6f}")
        print(f"  world_y = {params_y[0]:.6f} * norm_x + {params_y[1]:.6f} * norm_y + {params_y[2]:.6f}")

        print("\nCalibration accuracy:")
        errors = []
        for i, (sx, sy, wx, wy) in enumerate(self.calibration_points, 1):
            norm_x = sx / self.window_width - 0.5
            norm_y = sy / self.window_height - 0.5
            pred_wx = params_x[0] * norm_x + params_x[1] * norm_y + params_x[2]
            pred_wy = params_y[0] * norm_x + params_y[1] * norm_y + params_y[2]
            error = np.sqrt((pred_wx - wx)**2 + (pred_wy - wy)**2)
            errors.append(error)
            if i <= 5 or i > len(self.calibration_points) - 2:
                print(f"  Point {i}: error {error:.4f}m")
            elif i == 6:
                print(f"  ...")

        avg_error = np.mean(errors)
        max_error = np.max(errors)
        print(f"\nMean error: {avg_error:.4f}m")
        print(f"Maximum error: {max_error:.4f}m")

        print(f"\n{'='*70}")
        print("Applying new calibration parameters...")
        print(f"{'='*70}\n")

        test_point = (320, 240)
        norm_x = test_point[0] / self.window_width - 0.5
        norm_y = test_point[1] / self.window_height - 0.5
        old_wx, old_wy = self.screen_to_world(test_point[0], test_point[1])

        self._calibration_params_x = params_x
        self._calibration_params_y = params_y

        new_wx = params_x[0] * norm_x + params_x[1] * norm_y + params_x[2]
        new_wy = params_y[0] * norm_x + params_y[1] * norm_y + params_y[2]

        print(f"Test point (screen center {test_point}):")
        print(f"  Previous transform: ({old_wx:.3f}, {old_wy:.3f})")
        print(f"  New transform: ({new_wx:.3f}, {new_wy:.3f})")
        print(f"  Difference: {np.sqrt((new_wx-old_wx)**2 + (new_wy-old_wy)**2):.3f}m")

        self.calibration_history.append({
            'params_x': params_x.copy(),
            'params_y': params_y.copy(),
            'points': self.calibration_points.copy(),
            'avg_error': avg_error,
            'max_error': max_error,
            'timestamp': datetime.now()
        })

        print(f"\nCalibration round #{len(self.calibration_history)} completed")
        print(f"Check whether the green circles now align more accurately with the objects")
        print(f"\nAvailable actions:")
        print(f"  1. Press C to start another round with new reference points")
        print(f"  2. Press V to view calibration history")
        print(f"  3. Press A to accept and save the current calibration")
        print(f"  4. Press L to list saved calibrations")
        print(f"{'='*70}\n")

        self.update_frame()

    def cancel_calibration(self):
        """Cancel coordinate calibration."""
        self.calibration_mode = False
        self.calibration_points = []
        print("\nCalibration canceled")

    def view_calibration_history(self):
        """Display calibration rounds from this session."""
        if not self.calibration_history:
            print("\nNo calibration rounds completed in this session")
            print("   Press C to start calibration")
            return

        print(f"\n{'='*70}")
        print(f"Calibration history for this session ({len(self.calibration_history)} rounds):")
        print(f"{'='*70}")

        for i, cal in enumerate(self.calibration_history, 1):
            is_current = (np.array_equal(self._calibration_params_x, cal['params_x']) and
                         np.array_equal(self._calibration_params_y, cal['params_y']))
            marker = "★" if is_current else " "

            print(f"\n{marker} Round #{i}:")
            print(f"     Time: {cal['timestamp'].strftime('%H:%M:%S')}")
            print(f"     Points: {len(cal['points'])}")
            print(f"     Mean error: {cal['avg_error']:.4f}m")
            print(f"     Maximum error: {cal['max_error']:.4f}m")

        print(f"\n{'='*70}")
        print(f"Tips:")
        print(f"  - Press a number from 1 to {len(self.calibration_history)} to select a round")
        print(f"  - Press A to accept and save the current calibration")
        print(f"{'='*70}\n")

    def accept_calibration(self):
        """Accept and save the current calibration."""
        if self._calibration_params_x is None or self._calibration_params_y is None:
            print("\nComplete a calibration round before saving")
            return

        print(f"\n{'='*70}")
        print("Accept calibration")
        print(f"{'='*70}\n")

        import threading
        def get_input():
            try:
                version_name = input("Enter a version name (e.g. basket_calibration), or press Enter to use a timestamp: ").strip()
                if not version_name:
                    version_name = f"calibration_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

                description = input("Enter a description (optional): ").strip()
                if not description:
                    if self.calibration_history:
                        cal = self.calibration_history[-1]
                        description = f"{len(cal['points'])}-point calibration, error {cal['avg_error']:.4f}m"
                    else:
                        description = "Manual calibration"

                if self.calibration_history:
                    cal = self.calibration_history[-1]
                    num_points = len(cal['points'])
                    avg_error = cal['avg_error']
                    max_error = cal['max_error']
                else:
                    num_points = 0
                    avg_error = 0.0
                    max_error = 0.0

                self.save_calibration_to_file(
                    version_name=version_name,
                    description=description,
                    params_x=self._calibration_params_x,
                    params_y=self._calibration_params_y,
                    num_points=num_points,
                    avg_error=avg_error,
                    max_error=max_error
                )

                print(f"\nCalibration saved and set as the current version")
                print(f"   It will be loaded automatically on the next startup\n")

                self.calibration_mode = False

            except Exception as e:
                print(f"\nSave failed: {e}\n")

        thread = threading.Thread(target=get_input, daemon=True)
        thread.start()

    # ========================================================================
    # ========================================================================

    def check_task_success_and_cost(self, force=False):
        """Return (success, cost, cost_detail); force allows reevaluation within a step."""
        if not force and self.total_steps == self.last_check_step:
            return self.task_success, 0, []

        self.last_check_step = self.total_steps

        try:
            success = bool(self.editor.parsed_dict.get("goal_state")) and self.env.check_success()

            if success and not self.task_success:
                self.task_success = True
                print(f"\n[Step {self.total_steps}] Task completed successfully\n")

            # Do not call env.step here: evaluation must not advance the simulation.
            # Costs come from step_environment; this check returns zero cost and no details.

            return success, 0, []

        except Exception as e:
            if self.total_steps % 100 == 0:
                print(f"[WARNING] Task evaluation failed: {e}")
            return False, 0, []

    def step_environment(self, action):
        """Apply a seven-dimensional action and return (obs, reward, done, info) with cost checks."""
        obs, reward, done, info = self.env.step(action)

        self.total_steps += 1

        cost_value = info.get('cost', 0)
        cost_detail = info.get('cost_detail', [])

        if cost_value > 0:
            self.episode_cost += float(cost_value)
            self.safety_events.append(cost_detail)
            self.cost_history.append({
                'step': self.total_steps,
                'cost': cost_value,
                'detail': cost_detail
            })

            print(f"\n⚠️  [Step {self.total_steps}] Safety Violation!")
            print(f"   Cost: {cost_value}")
            print(f"   Detail: {cost_detail}\n")

        self.check_task_success_and_cost(force=True)

        return obs, reward, done, info

    def reset_task_monitoring(self):
        """Reset task monitoring after a task switch or environment reset."""
        self.task_success = False
        self.episode_cost = 0.0
        self.safety_events = []
        self.cost_history = []
        self.total_steps = 0
        self.last_check_step = 0
        print("[Monitor] Task monitoring reset")

    def get_task_status_text(self):
        """Return task status text for the GUI."""
        status_parts = []

        status_parts.append(f"Steps: {self.total_steps}")

        if self.task_success:
            status_parts.append("✅ Success")

        if self.episode_cost > 0:
            status_parts.append(f"⚠️ Cost: {self.episode_cost:.0f}")

        return " | ".join(status_parts) if status_parts else ""

    def save_cost_log(self, filename=None):
        """Save cost history as JSON, generating a filename when omitted."""
        if self.episode_cost == 0:
            return

        try:
            import json
            from datetime import datetime

            if filename is None:
                log_dir = Path(get_libero_path("datasets")) / "safety_logs"
                log_dir.mkdir(parents=True, exist_ok=True)
                filename = str(log_dir / f"cost_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

            cost_data = {
                'task': self.get_current_task_instruction(),
                'bddl_file': str(self.bddl_file),
                'total_steps': self.total_steps,
                'total_cost': self.episode_cost,
                'num_violations': len(self.safety_events),
                'cost_history': self.cost_history,
                'task_success': self.task_success,
                'timestamp': datetime.now().isoformat()
            }

            with open(filename, 'w') as f:
                json.dump(cost_data, f, indent=2)

            print(f"Cost log saved: {filename}")
            return filename

        except Exception as e:
            print(f"Could not save cost log: {e}")
            return None

    # ========================================================================

    def show_help(self):
        """Display editor help."""
        print(help_text.get_help_text())

    def apply_physics_settling(self, steps: int = 100):
        """Run physics for the requested number of steps to let objects settle."""
        try:
            robot_qpos_size = 9
            robot_qpos = self.env.sim.data.qpos[:robot_qpos_size].copy()
            robot_qvel = self.env.sim.data.qvel[:robot_qpos_size].copy()

            print(f"    Running {steps} simulation steps...")

            for i in range(steps):
                self.env.sim.data.qpos[:robot_qpos_size] = robot_qpos
                self.env.sim.data.qvel[:robot_qpos_size] = robot_qvel

                self.env.sim.step()

                if (i + 1) % 20 == 0:
                    print(f"    Progress: {i+1}/{steps}")

            self.env.sim.data.qpos[:robot_qpos_size] = robot_qpos
            self.env.sim.data.qvel[:robot_qpos_size] = robot_qvel
            self.env.sim.forward()

            for obj_name, info in self.object_info.items():
                try:
                    body_id = info['body_id']
                    actual_pos = self.env.sim.data.body_xpos[body_id].copy()
                    self.object_info[obj_name]['pos'] = tuple(actual_pos)
                except:
                    pass

            print(f"    Physics settling completed")

        except Exception as e:
            print(f"    Physics settling failed: {e}")

    def save_scene_snapshot(self, output_path: Optional[str] = None) -> str:
        """Save object poses, joint states, robot state, and metadata as YAML; return the path."""
        print(f"\n{'='*70}")
        print(f"Saving scene snapshot")
        print(f"{'='*70}\n")

        try:
            snapshot = {
                'metadata': {
                    'timestamp': datetime.now().isoformat(),
                    'bddl_file': str(self.bddl_file),
                    'scene_name': Path(self.bddl_file).stem,
                    'version': '1.0',
                    'description': 'Complete scene snapshot with zero-error precision'
                },
                'robot': {
                    'qpos': self.env.sim.data.qpos[:9].tolist(),
                    'qvel': self.env.sim.data.qvel[:9].tolist()
                },
                'objects': {},
                'fixtures': {},
                'joints': {}
            }

            for obj_name, info in self.object_info.items():
                try:
                    body_id = info['body_id']

                    pos = self.env.sim.data.body_xpos[body_id].copy()

                    quat = self.env.sim.data.body_xquat[body_id].copy()  # (w, x, y, z)

                    is_fixture = info.get('is_fixture', False)

                    obj_data = {
                        'type': info['type'],
                        'position': {
                            'x': float(pos[0]),
                            'y': float(pos[1]),
                            'z': float(pos[2])
                        },
                        'quaternion': {
                            'w': float(quat[0]),
                            'x': float(quat[1]),
                            'y': float(quat[2]),
                            'z': float(quat[3])
                        },
                        'body_id': int(body_id)
                    }

                    if 'joints' in info and info['joints']:
                        obj_data['joints'] = {}
                        joints_data = info['joints']
                        if isinstance(joints_data, dict):
                            for joint_name, joint_info in joints_data.items():
                                qpos_addr = joint_info['qpos_addr']
                                current_value = float(self.env.sim.data.qpos[qpos_addr])
                                obj_data['joints'][joint_name] = {
                                    'type': joint_info['type'],
                                    'range': joint_info['range'],
                                    'current_value': current_value,
                                    'qpos_addr': int(qpos_addr)
                            }

                    if is_fixture:
                        snapshot['fixtures'][obj_name] = obj_data
                    else:
                        snapshot['objects'][obj_name] = obj_data

                    print(f"  ✓ {obj_name}: pos=({pos[0]:.4f}, {pos[1]:.4f}, {pos[2]:.4f}), "
                          f"quat=({quat[0]:.3f}, {quat[1]:.3f}, {quat[2]:.3f}, {quat[3]:.3f})")

                except Exception as e:
                    print(f"  Skipped {obj_name}: {e}")

            if output_path is None:
                base_name = Path(self.bddl_file).stem
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

                if hasattr(self, 'custom_save_dir') and self.custom_save_dir:
                    output_path = Path(self.custom_save_dir) / f"{base_name}_scene_{timestamp}.yaml"
                else:
                    output_path = Path(self.bddl_file).parent / f"{base_name}_scene_{timestamp}.yaml"

            output_path = Path(output_path)

            with open(output_path, 'w', encoding='utf-8') as f:
                yaml.dump(snapshot, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

            print(f"\n{'='*70}")
            print(f"Scene snapshot save results")
            print(f"{'='*70}")
            print(f"Objects: {len(snapshot['objects'])}")
            print(f"Fixtures: {len(snapshot['fixtures'])}")
            print(f"Objects with joints: {sum(1 for obj in list(snapshot['objects'].values()) + list(snapshot['fixtures'].values()) if 'joints' in obj)}")
            print(f"Robot state saved")
            print(f"\nFile saved: {output_path}")
            print(f"Snapshots are deprecated; press S to save a BDDL + pruned_init scene bundle")
            print(f"{'='*70}\n")

            return str(output_path)

        except Exception as e:
            print(f"Could not save scene snapshot: {e}")
            import traceback
            traceback.print_exc()
            return None

    def load_scene_snapshot(self, snapshot_path: Optional[str] = None):
        """Restore a YAML scene snapshot, prompting for its path when omitted."""
        print(f"\n{'='*70}")
        print(f"Load scene snapshot")
        print(f"{'='*70}\n")

        if snapshot_path is None:
            import threading
            def get_input():
                try:
                    print("Enter the scene snapshot file path:")
                    print("  Example: ./scene_snapshot_20251126_123456.yaml")
                    print("  Press Enter to cancel")

                    user_input = input("Path: ").strip()

                    if not user_input:
                        print("Load canceled")
                        return

                    self._do_load_scene_snapshot(user_input)

                except Exception as e:
                    print(f"Load failed: {e}")

            thread = threading.Thread(target=get_input, daemon=True)
            thread.start()
        else:
            self._do_load_scene_snapshot(snapshot_path)

    def _handle_snapshot_restore(self, env_data: dict):
        """Apply prepared snapshot data and any new environment on the main thread."""
        try:
            operation_type = env_data['type']
            snapshot = env_data['snapshot']
            new_env = env_data.get('env')


            if new_env is not None:
                FrameUpdater._replace_environment(self, new_env)

                self.editor = BDDLEditor(str(self.current_bddl))
                self._load_objects()

                for _ in range(5):
                    self.env.sim.render(self.window_width, self.window_height, camera_name="agentview")


            # Restore the robot before individual object states.
            robot_qpos = np.array(snapshot['robot']['qpos'], dtype=np.float64)
            robot_qvel = np.array(snapshot['robot']['qvel'], dtype=np.float64)

            self.env.sim.data.qpos[:9] = robot_qpos
            self.env.sim.data.qvel[:9] = robot_qvel

            restored_count = 0
            skipped_objects = []

            all_snapshot_objects = {}
            all_snapshot_objects.update(snapshot.get('objects', {}))
            all_snapshot_objects.update(snapshot.get('fixtures', {}))

            for obj_name, obj_data in all_snapshot_objects.items():
                if obj_name not in self.object_info:
                    skipped_objects.append(obj_name)
                    continue

                try:
                    body_id = self.object_info[obj_name]['body_id']

                    if body_id < 0 or body_id >= self.env.sim.model.nbody:
                        skipped_objects.append(obj_name)
                        continue

                    pos = np.array([
                        obj_data['position']['x'],
                        obj_data['position']['y'],
                        obj_data['position']['z']
                    ], dtype=np.float64)

                    quat = np.array([
                        obj_data['quaternion']['w'],
                        obj_data['quaternion']['x'],
                        obj_data['quaternion']['y'],
                        obj_data['quaternion']['z']
                    ], dtype=np.float64)

                    joint_id = self.env.sim.model.body_jntadr[body_id]
                    if joint_id >= 0:
                        qpos_idx = self.env.sim.model.jnt_qposadr[joint_id]

                        if qpos_idx + 7 <= len(self.env.sim.data.qpos):
                            self.env.sim.data.qpos[qpos_idx:qpos_idx+3] = pos

                            self.env.sim.data.qpos[qpos_idx+3:qpos_idx+7] = quat

                            qvel_idx = self.env.sim.model.jnt_dofadr[joint_id]
                            if qvel_idx + 6 <= len(self.env.sim.data.qvel):
                                self.env.sim.data.qvel[qvel_idx:qvel_idx+6] = 0

                    if 'joints' in obj_data:
                        for joint_name, joint_data in obj_data['joints'].items():
                            try:
                                qpos_addr = joint_data['qpos_addr']
                                target_value = joint_data['current_value']
                                if 0 <= qpos_addr < len(self.env.sim.data.qpos):
                                    self.env.sim.data.qpos[qpos_addr] = target_value
                            except:
                                pass

                    restored_count += 1

                except Exception as e:
                    pass
            self.env.sim.forward()

            for obj_name, info in self.object_info.items():
                try:
                    body_id = info['body_id']
                    actual_pos = self.env.sim.data.body_xpos[body_id].copy()
                    self.object_info[obj_name]['pos'] = tuple(actual_pos)
                except:
                    pass

            print(f"\n{'='*70}")
            print(f"Scene snapshot load results")
            print(f"{'='*70}")
            print(f"Restored objects: {restored_count}")

            if skipped_objects:
                print(f"\nSkipped {len(skipped_objects)} objects missing from the current scene:")
                for obj in skipped_objects:
                    print(f"  • {obj}")

            print(f"\nScene snapshot loaded")
            print(f"Scene restored to the saved snapshot state")
            print(f"{'='*70}\n")

        except Exception as e:
            import traceback
            traceback.print_exc()

    def _handle_bddl_import(self, env_data: dict):
        """Apply the prepared environment, editor, and BDDL path on the main thread."""
        try:
            new_env = env_data['new_env']
            new_editor = env_data['new_editor']
            new_bddl_file = env_data['new_bddl_file']


            FrameUpdater._replace_environment(self, new_env)
            self.editor = new_editor
            self.bddl_file = new_bddl_file


            self._load_objects()

            for _ in range(5):
                self.env.sim.render(self.window_width, self.window_height, camera_name="agentview")

            self.env.sim.forward()

            self._auto_save_workspace_state()

            print(f"\n{'='*70}")
            print(f"BDDL imported")
            print(f"{'='*70}")
            print(f"New scene: {Path(new_bddl_file).name}")
            print(f"Objects: {len(self.object_info)}")
            print(f"Environment ready")
            print(f"\nAvailable actions:")
            print(f"  - Press P to list all objects")
            print(f"  - Press U to save the current state")
            print(f"  - Press M to switch editing modes")
            print(f"{'='*70}\n")

        except Exception as e:
            import traceback
            traceback.print_exc()

    def _do_load_scene_snapshot(self, snapshot_path: str):
        """Prepare snapshot data in a worker; update_frame applies it on the main thread."""
        try:
            snapshot_path = Path(snapshot_path)

            if not snapshot_path.exists():
                print(f"File not found: {snapshot_path}")
                return

            print(f"  Loading file: {snapshot_path}")

            with open(snapshot_path, 'r', encoding='utf-8') as f:
                snapshot = yaml.safe_load(f)

            print(f"  Snapshot file read")
            print(f"  Timestamp: {snapshot['metadata']['timestamp']}")
            print(f"  Scene: {snapshot['metadata']['scene_name']}")
            print(f"  Preparing scene restoration...")

            current_scene_name = Path(self.bddl_file).stem
            snapshot_scene_name = snapshot['metadata']['scene_name']

            if current_scene_name != snapshot_scene_name:
                print(f"  Warning: current scene '{current_scene_name}' differs from snapshot scene '{snapshot_scene_name}'")
                print(f"  Continuing may cause object mismatches")

            all_snapshot_objects = {}
            all_snapshot_objects.update(snapshot.get('objects', {}))
            all_snapshot_objects.update(snapshot.get('fixtures', {}))

            missing_objects_info = []
            for obj_name, obj_data in all_snapshot_objects.items():
                if obj_name not in self.object_info:
                    missing_objects_info.append({
                        'name': obj_name,
                        'type': obj_data.get('type', 'Unknown'),
                        'data': obj_data
                    })

            if missing_objects_info:
                print(f"\nFound {len(missing_objects_info)} objects missing from the current scene:")
                for obj_info in missing_objects_info:
                    print(f"  • {obj_info['name']} ({obj_info['type']})")

                print(f"\nAdd these objects to restore the complete snapshot")
                print(f"Add missing objects automatically? (y/n, default y): ", end='', flush=True)

                import sys
                user_choice = input().strip().lower()

                if user_choice in ['', 'y', 'yes']:
                    print(f"\n  Adding missing objects...")

                    for obj_info in missing_objects_info:
                        obj_name = obj_info['name']
                        obj_type = obj_info['type']
                        obj_data = obj_info['data']

                        try:
                            base_name = obj_name.rsplit('_', 1)[0] if '_' in obj_name and obj_name.split('_')[-1].isdigit() else obj_name

                            if base_name in AVAILABLE_OBJECTS:
                                obj_class = AVAILABLE_OBJECTS[base_name]
                            else:
                                obj_class = obj_type

                            pos_2d = (
                                obj_data['position']['x'],
                                obj_data['position']['y']
                            )

                            self.editor.add_object_with_region(
                                obj_name=obj_name,
                                obj_type=obj_class,
                                position=pos_2d,
                                region_half_len=0.05,
                                target="main_table",
                                add_to_interest=True
                            )

                            print(f"    Added {obj_name} ({obj_class})")

                        except Exception as e:
                            print(f"    Could not add {obj_name}: {e}")

                    self.editor.save(str(self.current_bddl))
                    print(f"  BDDL updated")

                    print(f"  Preparing new environment...")

                    try:
                        from libero.libero.envs import OffScreenRenderEnv
                        env_args = {
                            "bddl_file_name": str(self.current_bddl),
                            "camera_heights": self.window_height,
                            "camera_widths": self.window_width,
                            "camera_names": "agentview",
                            "render_gpu_device_id": 0,
                        }

                        print(f"    Creating environment...")
                        new_env = OffScreenRenderEnv(**env_args)
                        new_env.seed(0)
                        new_env.reset()

                        print(f"    Initializing renderer...")
                        for _ in range(5):
                            new_env.sim.render(self.window_width, self.window_height, camera_name="agentview")

                        new_env.sim.forward()

                        print(f"  New environment ready")

                        # Queue the prepared environment and snapshot for application on the GUI thread.
                        self._new_env_ready = {
                            'env': new_env,
                            'snapshot': snapshot,
                            'type': 'snapshot_load'
                        }
                        print(f"  Waiting for the main thread to switch environments...")

                        return

                    except Exception as e:
                        print(f"  Environment preparation failed: {e}")
                        import traceback
                        traceback.print_exc()
                        return
                else:
                    print(f"  Skipping missing objects; only existing objects will be restored")

            self._new_env_ready = {
                'env': None,
                'snapshot': snapshot,
                'type': 'snapshot_restore_only'
            }
            print(f"  Waiting for the main thread to restore state...")

        except Exception as e:
            print(f"Could not load scene snapshot: {e}")
            import traceback
            traceback.print_exc()
            robot_qpos = np.array(snapshot['robot']['qpos'], dtype=np.float64)
            robot_qvel = np.array(snapshot['robot']['qvel'], dtype=np.float64)

            self.env.sim.data.qpos[:9] = robot_qpos
            self.env.sim.data.qvel[:9] = robot_qvel
            print(f"  Robot state restored")

            restored_count = 0
            skipped_objects = []

            for obj_name, obj_data in all_snapshot_objects.items():
                if obj_name not in self.object_info:
                    skipped_objects.append(obj_name)
                    continue

                try:
                    body_id = self.object_info[obj_name]['body_id']

                    if body_id < 0 or body_id >= self.env.sim.model.nbody:
                        print(f"  {obj_name}: invalid body_id {body_id}")
                        skipped_objects.append(obj_name)
                        continue

                    pos = np.array([
                        obj_data['position']['x'],
                        obj_data['position']['y'],
                        obj_data['position']['z']
                    ], dtype=np.float64)

                    quat = np.array([
                        obj_data['quaternion']['w'],
                        obj_data['quaternion']['x'],
                        obj_data['quaternion']['y'],
                        obj_data['quaternion']['z']
                    ], dtype=np.float64)

                    joint_id = self.env.sim.model.body_jntadr[body_id]
                    if joint_id >= 0:
                        qpos_idx = self.env.sim.model.jnt_qposadr[joint_id]

                        if qpos_idx + 7 <= len(self.env.sim.data.qpos):
                            self.env.sim.data.qpos[qpos_idx:qpos_idx+3] = pos

                            self.env.sim.data.qpos[qpos_idx+3:qpos_idx+7] = quat

                            qvel_idx = self.env.sim.model.jnt_dofadr[joint_id]
                            if qvel_idx + 6 <= len(self.env.sim.data.qvel):
                                self.env.sim.data.qvel[qvel_idx:qvel_idx+6] = 0
                        else:
                            print(f"  {obj_name}: qpos index out of bounds (qpos_idx={qpos_idx}, qpos_len={len(self.env.sim.data.qpos)})")

                    if 'joints' in obj_data:
                        for joint_name, joint_data in obj_data['joints'].items():
                            try:
                                qpos_addr = joint_data['qpos_addr']
                                target_value = joint_data['current_value']
                                if 0 <= qpos_addr < len(self.env.sim.data.qpos):
                                    self.env.sim.data.qpos[qpos_addr] = target_value
                                else:
                                    print(f"  {obj_name}.{joint_name}: invalid qpos address {qpos_addr}")
                            except Exception as je:
                                print(f"  {obj_name}.{joint_name}: joint restoration failed: {je}")

                    print(f"  {obj_name}: position and orientation restored")
                    restored_count += 1

                except Exception as e:
                    print(f"  Could not restore {obj_name}: {e}")
                    import traceback
                    traceback.print_exc()

            self.env.sim.forward()

            for obj_name, info in self.object_info.items():
                try:
                    body_id = info['body_id']
                    actual_pos = self.env.sim.data.body_xpos[body_id].copy()
                    self.object_info[obj_name]['pos'] = tuple(actual_pos)
                except:
                    pass

            print(f"\n{'='*70}")
            print(f"Scene snapshot load results")
            print(f"{'='*70}")
            print(f"Restored objects: {restored_count}")

            if skipped_objects:
                print(f"\nSkipped {len(skipped_objects)} objects missing from the current scene:")
                for obj in skipped_objects:
                    print(f"  • {obj}")
                print(f"\nThese objects were skipped by the user or could not be added")

            print(f"{'='*70}\n")

        except Exception as e:
            print(f"Could not load scene snapshot: {e}")
            import traceback
            traceback.print_exc()

    def add_object(self):
        """Open the add-object dialog in free mode."""
        print(f"\n{'='*70}")
        print(f"Add object to scene")
        print(f"{'='*70}\n")

        from gui_modules.dialogs import show_add_object_dialog

        obj_type = show_add_object_dialog()

        if obj_type:
            print(f"Selected object type: {obj_type}")

            if obj_type in AVAILABLE_OBJECTS:
                ObjectManager.start_change(self, obj_type=obj_type)
            else:
                print(f"Object type '{obj_type}' is not available")
        else:
            print("Add object canceled")

    def _show_delete_dialog(self):
        """Open the object deletion dialog."""
        if not self.object_info:
            import tkinter as tk
            from tkinter import messagebox
            messagebox.showinfo("Info", "No objects in scene to delete!")
            return

        import tkinter as tk
        from tkinter import ttk, messagebox

        dialog = tk.Toplevel()
        dialog.title("Delete Object - Select Item")
        dialog.geometry("450x350")
        dialog.resizable(False, False)

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (450 // 2)
        y = (dialog.winfo_screenheight() // 2) - (350 // 2)
        dialog.geometry(f"450x350+{x}+{y}")

        title_label = tk.Label(
            dialog,
            text="Select Object to Delete",
            font=("Arial", 14, "bold"),
            fg="darkred"
        )
        title_label.pack(pady=10)

        count_label = tk.Label(
            dialog,
            text=f"{len(self.object_info)} Objects in Scene:",
            font=("Arial", 10)
        )
        count_label.pack(pady=5)

        combo_frame = tk.Frame(dialog)
        combo_frame.pack(pady=10, padx=20, fill=tk.X)

        object_list = []
        for obj_name, obj_data in sorted(self.object_info.items()):
            obj_type = obj_data.get('type', 'unknown')
            is_fixture = obj_data.get('is_fixture', False)
            if is_fixture:
                object_list.append(f"{obj_name} ({obj_type}) [FIXTURE]")
            else:
                object_list.append(f"{obj_name} ({obj_type})")

        selected_var = tk.StringVar()
        combo = ttk.Combobox(
            combo_frame,
            textvariable=selected_var,
            values=object_list,
            state="readonly",
            font=("Arial", 10),
            width=40
        )
        combo.pack(fill=tk.X)
        combo.set("-- Select an object to delete --")

        warning_label = tk.Label(
            dialog,
            text="⚠️ This action cannot be undone!\nYou can reload scene with 'I' or 'Alt+L'",
            font=("Arial", 9),
            fg="red"
        )
        warning_label.pack(pady=10)

        result = {'selected': None}

        button_frame = tk.Frame(dialog)
        button_frame.pack(pady=20)

        def on_delete():
            selected = selected_var.get()
            if selected and not selected.startswith("--"):
                obj_name = selected.split(" (")[0]

                confirm = messagebox.askyesno(
                    "Confirm Delete",
                    f"Are you sure you want to delete:\n\n{obj_name}?",
                    icon='warning'
                )

                if confirm:
                    result['selected'] = obj_name
                    dialog.destroy()
            else:
                messagebox.showwarning("Warning", "Please select an object to delete!")

        def on_cancel():
            dialog.destroy()

        delete_button = tk.Button(
            button_frame,
            text="Delete Object",
            command=on_delete,
            width=15,
            bg="lightcoral",
            font=("Arial", 10, "bold")
        )
        delete_button.pack(side=tk.LEFT, padx=10)

        cancel_button = tk.Button(
            button_frame,
            text="Cancel",
            command=on_cancel,
            width=15,
            font=("Arial", 10)
        )
        cancel_button.pack(side=tk.LEFT, padx=10)

        hint_label = tk.Label(
            dialog,
            text="Tip: You can also LClick to select + Delete key",
            font=("Arial", 8),
            fg="blue"
        )
        hint_label.pack(pady=5)

        dialog.wait_window()

        if result['selected']:
            obj_name = result['selected']
            print(f"Selected object for deletion: {obj_name}")
            self.delete_object(obj_name)
        else:
            print("Deletion canceled")

    def delete_object(self, obj_name: str):
        """Remove an editable object while preserving all retained simulator state."""
        return ObjectManager.start_change(self, obj_name=obj_name)

    def _close_policy(self, event=None):
        if self.ai_controller:
            self.ai_controller.cleanup()
        if getattr(self, "policy_service", None):
            self.policy_service.shutdown()

    def switch_vla_model(self):
        """Select a service profile without loading model weights into the GUI."""
        if self.ai_mode:
            return
        from gui_modules.dialogs import show_select_vla_model_dialog
        path = show_select_vla_model_dialog(self.vla_model_path,
            parent=self.fig.canvas.manager.window, service_manager=self.policy_service)
        if path:
            if self.ai_controller:
                self.ai_controller.cleanup()
            self.vla_model_path = path
            self.ai_controller = AIController(self, path)
            if self.studio:
                self.studio.log(f"Selected policy: {self.ai_controller.profile.name}")
                self.studio.refresh()

    def switch_bddl_task(self):


        if self.ai_mode:
            print("Exit AI mode with Space before switching tasks")
            return

        if self.is_dragging:
            print("Release the dragged object before switching tasks")
            return

        from gui_modules.dialogs import show_select_bddl_task_dialog

        result = show_select_bddl_task_dialog()

        if result:
            suite_name, bddl_file_path = result

            print(f"  Task suite: {suite_name}")
            print(f"  Task file: {Path(bddl_file_path).name}")

            if str(bddl_file_path) == str(self.bddl_file):
                print("  Task unchanged")
                return

            import threading
            thread = threading.Thread(
                target=lambda: self._do_switch_bddl_task(bddl_file_path),
                daemon=True
            )
            thread.start()
        else:
            print("Task switch canceled")

    def _do_switch_bddl_task(self, bddl_file_path: str):
        """Prepare a task switch using the BDDL import workflow in a worker thread."""
        print(f"\n[Worker] Switching BDDL task...")
        print(f"[Worker] Target task: {Path(bddl_file_path).name}\n")

        try:
            print(f"[Worker] Step 1/7: Loading task BDDL...")
            new_editor = BDDLEditor(bddl_file_path)

            print(f"[Worker] Step 2/7: Creating task environment...")
            new_env = OffScreenRenderEnv(
                bddl_file_name=bddl_file_path,
                camera_heights=256,
                camera_widths=256,
                has_renderer=False,
                has_offscreen_renderer=True,
                render_camera="agentview",
                use_camera_obs=True,
                control_freq=20,
            )

            print(f"[Worker] Step 3/7: Resetting environment...")
            new_env.reset()

            print(f"[Worker] Step 4/7: Initializing renderer...")
            for _ in range(5):
                _ = new_env.sim.render(
                    height=self.window_height,
                    width=self.window_width,
                    camera_name="agentview"
                )
                new_env.sim.forward()

            task_instruction = self._get_instruction_from_bddl_file(bddl_file_path)

            print(f"[Worker] Step 5/7: Preparing environment switch...")
            switch_data = {
                'new_env': new_env,
                'new_editor': new_editor,
                'new_bddl_file': bddl_file_path,
                'new_instruction': task_instruction,
                'operation': 'switch_bddl_task'
            }

            with self._env_switch_lock:
                self._new_env_ready = switch_data


        except Exception as e:
            import traceback
            traceback.print_exc()

    def _get_instruction_from_bddl_file(self, bddl_file_path: str) -> str:
        """Read a task instruction without using the current editor instance."""
        try:
            temp_editor = BDDLEditor(bddl_file_path)
            parsed_dict = temp_editor.parsed_dict

            language = parsed_dict.get('language', [])
            if language:
                if isinstance(language, list) and len(language) > 0:
                    return ' '.join(str(item) for item in language)
                elif isinstance(language, str):
                    return language

            instructions = parsed_dict.get('language_instruction', [])
            if instructions and len(instructions) > 0:
                return ' '.join(str(item) for item in instructions)

            problem_name = parsed_dict.get('problem_name', '')
            if problem_name:
                return problem_name.replace('_', ' ')

            file_stem = Path(bddl_file_path).stem
            return file_stem.replace('_', ' ')

        except Exception as e:
            print(f"Could not read BDDL task instruction: {e}")
            return Path(bddl_file_path).stem.replace('_', ' ')

    def quick_toggle_state(self, obj_name: str, specific_body_id: Optional[int] = None):
        """Queue a toggle for the clicked part or the object's default joint."""
        return joint_control.queue_joint_toggle(self, obj_name, specific_body_id)

    def reset_scene(self):
        """Restore initial.pruned_init when R is pressed."""
        print(f"\n{'='*70}")
        print(f"Restoring initial scene state")
        print(f"{'='*70}\n")

        if hasattr(self, 'physics_safety_monitor') and self.physics_safety_monitor:
            self.physics_safety_monitor.reset()
            self.physics_safety_monitor.reload_config()

        try:
            if not self.initial_state.exists():
                print("No saved initial state; resampling instead (E)")
                self.resample_scene()
                return

            print(f"  Loading initial state: {self.initial_state}")
            print(f"  This state was saved when the scene or environment was initialized")

            state_tensor = torch.load(str(self.initial_state))
            sim_state = state_tensor.numpy()

            current_qpos_size = self.env.sim.data.qpos.size
            current_qvel_size = self.env.sim.data.qvel.size
            saved_state_size = sim_state.size

            # MuJoCo state contains qpos, qvel, and additional simulator fields.
            expected_min_size = current_qpos_size + current_qvel_size

            if saved_state_size < expected_min_size * 0.9 or saved_state_size > expected_min_size * 1.1:
                print(f"  State dimensions do not match")
                print(f"     Current environment: qpos={current_qpos_size}, qvel={current_qvel_size}")
                print(f"     Saved state: size={saved_state_size} (expected approximately {expected_min_size})")
                print(f"  The environment structure has changed, possibly after adding or deleting objects")
                print(f"  Rebuilding the environment with the current objects to match state dimensions")
                print(f"  Environment rebuild required...")

                # Rebuild from current.bddl to preserve objects added or removed by the user.
                print(f"  Using working BDDL: {self.current_bddl}")

                try:
                    self.env.close()
                except:
                    pass

                from libero.libero.envs import OffScreenRenderEnv
                env_args = {
                    "bddl_file_name": str(self.current_bddl),
                    "camera_heights": self.window_height,
                    "camera_widths": self.window_width,
                    "camera_names": "agentview",
                    "render_gpu_device_id": 0,
                }

                self.env = OffScreenRenderEnv(**env_args)
                self.env.seed(0)
                self.env.reset()

                self._load_objects()

                self._init_physics_safety_monitor()


            # Structural edits can make the saved state incompatible with the current model.
            state_restored = False
            if not (saved_state_size < expected_min_size * 0.9 or saved_state_size > expected_min_size * 1.1):
                try:
                    self.env.sim.set_state_from_flattened(sim_state)
                    self.env.sim.forward()
                    state_restored = True
                except Exception as state_error:
                    pass

            for obj_name, info in self.object_info.items():
                try:
                    body_id = info['body_id']
                    pos = self.env.sim.data.body_xpos[body_id]
                    self.object_info[obj_name]['pos'] = tuple(pos)
                except Exception as e:
                    pass

            if self.selected_object:
                self._remove_highlight(self.selected_object)

            self.selected_object = None
            self.selected_body_id = None
            self.is_dragging = False

            if state_restored:
                shutil.copy2(str(self.initial_state), str(self.current_state))
                shutil.copy2(str(self.initial_bddl), str(self.current_bddl))
            else:
                self._auto_save_workspace_state(save_as_initial=False)

            print(f"  Initializing renderer...")
            for _ in range(5):
                self.env.sim.render(
                    self.window_width,
                    self.window_height,
                    camera_name="agentview"
                )

            from gui_modules.frame_updater import FrameUpdater
            FrameUpdater._immediate_refresh(self)

            self._force_refresh_frames = 0

        except Exception as e:
            import traceback
            traceback.print_exc()

    def enter_data_collection_mode(self):
        """Enter Human Assist mode without resetting the scene or recording demonstrations."""
        if self.ai_mode:
            print("⚠️  Please exit AI mode first (press Space)")
            return

        if self.data_collection_mode:
            print("⚠️  Already in Human Assist mode")
            return

        if not self.data_collector:
            print("🔄 Initializing Human Assist controller...")
            if hasattr(self, '_init_data_collector'):
                self._init_data_collector()
            else:
                try:
                    from gui_modules.data_collection_mode import DataCollectionController
                    self.data_collector = DataCollectionController(self)
                    print("✓ Human Assist controller initialized")
                except Exception as e:
                    print(f"❌ Human Assist controller initialization failed: {e}")
                    return

            if not self.data_collector:
                print("❌ Cannot initialize Human Assist controller")
                return

        if self.data_collector.start_collection():
            self.data_collection_mode = True
            self.free_mode = False

            self._init_hotkey_panel()
            self.fig.canvas.draw()

    def exit_data_collection_mode(self, save: bool = True):
        """Leave Human Assist mode; save is retained for API compatibility and has no effect."""
        if not self.data_collection_mode:
            return

        print(f"\n{'='*70}")
        print(f"🔙 Exiting Human Assist Mode")
        print(f"{'='*70}\n")

        if self.data_collector:
            # Both cases do not save data - Human Assist mode is for assistance only
            if save:
                self.data_collector.stop_collection(success=True)
            else:
                self.data_collector.cancel_collection()

        self.data_collection_mode = False

        self.free_mode = False

        self._init_hotkey_panel()

        self.fig.canvas.draw()

        print(f"✅ Exited Human Assist mode, returned to PHYSICS mode")
        print(f"{'='*70}\n")

    def resample_scene(self):

        if hasattr(self, 'physics_safety_monitor') and self.physics_safety_monitor:
            self.physics_safety_monitor.reset()
            self.physics_safety_monitor.reload_config()

        try:
            self.env.reset()

            for obj_name, info in self.object_info.items():
                try:
                    body_id = info['body_id']
                    pos = self.env.sim.data.body_xpos[body_id]
                    self.object_info[obj_name]['pos'] = tuple(pos)
                    self.object_info[obj_name]['initial_pos'] = tuple(pos)
                except Exception as e:
                    pass

            if self.selected_object:
                self._remove_highlight(self.selected_object)

            self.selected_object = None
            self.selected_body_id = None
            self.is_dragging = False

            # Resampling updates current state while preserving the initial reset baseline.
            print(f"  Saving current state while preserving the initial state...")
            self._auto_save_workspace_state(save_as_initial=False)
            self._workspace_needs_save = False

            print(f"  Initializing renderer...")
            for _ in range(5):
                self.env.sim.render(
                    self.window_width,
                    self.window_height,
                    camera_name="agentview"
                )

            print(f"  Refreshing display...")
            from gui_modules.frame_updater import FrameUpdater
            FrameUpdater._immediate_refresh(self)

            # KeyboardHandler clears safety events and refreshes the panel after the operation.

            self._force_refresh_frames = 0

            print(f"Scene resampled with a new layout")
            print(f"Current workspace state updated")
            print(f"Press R to restore the initial state saved when the scene was loaded")
            print(f"{'='*70}\n")

        except Exception as e:
            print(f"Resampling failed: {e}")
            import traceback
            traceback.print_exc()

    def run(self):
        """Run the editor event loop."""
        print("Editor started")
        print("   The editor window should now be open.\n")

        self.timer.start()

        plt.show()

        self._close_policy()
        if self.env:
            self.env.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="red-libero Scene Studio")
    parser.add_argument("bddl_file", nargs="?", default=None, help="BDDL task file")
    parser.add_argument("--save-dir", "-d", default=None,
                       help="Scene export directory")
    parser.add_argument("--policy-profile", "--vla-model", dest="vla_model", default=None,
                       help="Policy service YAML profile for AI mode")

    parser.add_argument("--classic-ui", action="store_true", help="Use the classic Matplotlib layout")
    args = parser.parse_args()

    try:
        editor = MatplotlibGUIEditor(
            args.bddl_file,
            custom_save_dir=args.save_dir,
            vla_model_path=args.vla_model,
            ui_style="classic" if args.classic_ui else "studio"
        )
        editor.run()
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
