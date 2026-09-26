"""Convert camera coordinates to simulator positions."""

import logging
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


def world_to_screen(
    world_x: float,
    world_y: float,
    window_width: int,
    window_height: int,
    calibration_params_x: Optional[np.ndarray] = None,
    calibration_params_y: Optional[np.ndarray] = None,
) -> Tuple[int, int]:
    if calibration_params_x is not None and calibration_params_y is not None:
        params_x = calibration_params_x
        params_y = calibration_params_y
    else:
        params_x = np.array([-0.021842, 0.619758, 0.031169])
        params_y = np.array([0.664909, 0.017735, 0.001459])
    world_x_centered = world_x - params_x[2]
    world_y_centered = world_y - params_y[2]
    det = params_x[0] * params_y[1] - params_x[1] * params_y[0]
    if abs(det) < 1e-10:
        norm_x = world_y_centered / params_y[0] if abs(params_y[0]) > 1e-10 else 0
        norm_y = world_x_centered / params_x[1] if abs(params_x[1]) > 1e-10 else 0
    else:
        norm_x = (params_y[1] * world_x_centered - params_x[1] * world_y_centered) / det
        norm_y = (
            -params_y[0] * world_x_centered + params_x[0] * world_y_centered
        ) / det
    screen_x = int((norm_x + 0.5) * window_width)
    screen_y = int((norm_y + 0.5) * window_height)
    screen_x = max(0, min(window_width - 1, screen_x))
    screen_y = max(0, min(window_height - 1, screen_y))
    screen_x = window_width - 1 - screen_x
    return (screen_x, screen_y)


def screen_to_world(
    screen_x: int,
    screen_y: int,
    window_width: int,
    window_height: int,
    calibration_params_x: Optional[np.ndarray] = None,
    calibration_params_y: Optional[np.ndarray] = None,
) -> Tuple[float, float]:
    norm_x = screen_x / window_width - 0.5
    norm_y = screen_y / window_height - 0.5
    if calibration_params_x is not None and calibration_params_y is not None:
        world_x = (
            calibration_params_x[0] * norm_x
            + calibration_params_x[1] * norm_y
            + calibration_params_x[2]
        )
        world_y = (
            calibration_params_y[0] * norm_x
            + calibration_params_y[1] * norm_y
            + calibration_params_y[2]
        )
    else:
        world_x = -0.021842 * norm_x + 0.619758 * norm_y + 0.031169
        world_y = 0.664909 * norm_x + 0.017735 * norm_y + 0.001459
    return (world_x, world_y)


def get_3d_position_from_mouse(
    env,
    screen_x: int,
    screen_y: int,
    target_height: float,
    window_width: int,
    window_height: int,
) -> Optional[np.ndarray]:
    try:
        model = env.sim.model
        data = env.sim.data
        camera_id = model.camera_name2id("agentview")
        cam_pos = data.cam_xpos[camera_id].copy()
        cam_mat = data.cam_xmat[camera_id].reshape(3, 3).copy()
        screen_x = window_width - 1 - screen_x
        ndc_x = 2.0 * screen_x / window_width - 1.0
        ndc_y = 1.0 - 2.0 * screen_y / window_height
        fovy = model.cam_fovy[camera_id]
        aspect = window_width / window_height
        tan_fovy = np.tan(np.radians(fovy) / 2.0)
        tan_fovx = tan_fovy * aspect
        ray_dir_cam = np.array([ndc_x * tan_fovx, ndc_y * tan_fovy, -1.0])
        ray_dir_cam = ray_dir_cam / np.linalg.norm(ray_dir_cam)
        ray_dir_world = cam_mat @ ray_dir_cam
        ray_dir_world = ray_dir_world / np.linalg.norm(ray_dir_world)
        if abs(ray_dir_world[2]) < 1e-06:
            return None
        t = (target_height - cam_pos[2]) / ray_dir_world[2]
        if t < 0:
            return None
        intersection = cam_pos + t * ray_dir_world
        return intersection
    except Exception as e:
        logger.warning(f"Get 3d position from mouse failed: e={e}")
        return None
