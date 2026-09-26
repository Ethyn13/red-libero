"""Contact- and motion-based grasp detection strategies."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import numpy as np


class GraspDetectionStrategy(ABC):
    """Return is_grasping, confidence, and strategy-specific details."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def detect(self, env: Any, obj_name: str, **kwargs) -> Dict[str, Any]:
        pass

    def get_info(self) -> Dict[str, Any]:
        return {"name": self.name}

    def _no_grasp_result(self, reason: str) -> Dict[str, Any]:
        return {"is_grasping": False, "confidence": 0.0, "details": {"reason": reason}}


class _FingerContactStrategy(GraspDetectionStrategy):
    """Share object lookup and finger sampling for contact-only strategies."""

    require_both = False
    method = "simple_contact"

    def detect(self, env: Any, obj_name: str, **kwargs) -> Dict[str, Any]:
        try:
            obj = env.get_object(obj_name)
            if obj is None:
                return self._no_grasp_result("Object not found")
            robot = env.robots[0]
            gripper = robot.gripper[robot.arms[0]]
            contacts = [
                env._check_contact(
                    env.sim, gripper._important_geoms[side], obj.contact_geoms
                )
                for side in ("left_fingerpad", "right_fingerpad")
            ]
            (left, right) = contacts
            grasping = left and right if self.require_both else left or right
            return {
                "is_grasping": grasping,
                "confidence": 1.0 if grasping else 0.0,
                "details": {
                    "left_contact": left,
                    "right_contact": right,
                    "method": self.method,
                },
            }
        except Exception as exc:
            return self._no_grasp_result(f"Error: {exc}")


class SimpleContactStrategy(_FingerContactStrategy):
    def __init__(self):
        super().__init__("SimpleContact")


class DualFingerStrategy(_FingerContactStrategy):
    require_both = True
    method = "dual_finger"

    def __init__(self):
        super().__init__("DualFinger")


class AdvancedGraspStrategy(GraspDetectionStrategy):
    """Combine lift, contact, and gripper-distance evidence after settling."""

    def __init__(
        self,
        lifted_height_threshold: float = 0.06,
        grasp_distance_threshold: float = 0.06,
        grasp_div_threshold: float = 0.03,
        wait_steps: int = 10,
    ):
        super().__init__("AdvancedGrasp")
        self.lifted_height_threshold = lifted_height_threshold
        self.grasp_distance_threshold = grasp_distance_threshold
        self.grasp_div_threshold = grasp_div_threshold
        self.wait_steps = wait_steps
        self.object_initial_heights = {}

    def detect(self, env: Any, obj_name: str, **kwargs) -> Dict[str, Any]:
        try:
            object_to_check = env.get_object(obj_name)
            if object_to_check is None:
                return self._no_grasp_result("Object not found")
            if not (hasattr(env, "obj_body_id") and obj_name in env.obj_body_id):
                return self._no_grasp_result("Object body ID not found")
            step_count = kwargs.get("step_count", 0)
            gripper_pos = kwargs.get("gripper_pos")
            if gripper_pos is None and hasattr(env, "robots"):
                arm_name = env.robots[0].arms[0]
                eef_site_id = env.robots[0].eef_site_id
                if isinstance(eef_site_id, dict):
                    eef_site_id = eef_site_id[arm_name]
                gripper_pos = env.sim.data.site_xpos[eef_site_id]
            obj_pos = env.sim.data.body_xpos[env.obj_body_id[obj_name]]
            distance = self._calculate_gripper_object_distance(
                env, obj_name, gripper_pos
            )
            if distance is None:
                distance = (
                    np.linalg.norm(gripper_pos - obj_pos)
                    if gripper_pos is not None
                    else float("inf")
                )
            if obj_name not in self.object_initial_heights:
                if step_count >= self.wait_steps:
                    self.object_initial_heights[obj_name] = obj_pos[2]
            height_diff = 0.0
            if obj_name in self.object_initial_heights:
                current_height = obj_pos[2]
                initial_height = self.object_initial_heights[obj_name]
                height_diff = current_height - initial_height
            arm_name = env.robots[0].arms[0]
            gripper = env.robots[0].gripper[arm_name]
            if not hasattr(gripper, "_important_geoms"):
                return self._no_grasp_result(
                    "Gripper missing _important_geoms attribute"
                )
            if gripper._important_geoms is None:
                return self._no_grasp_result("Gripper _important_geoms is None")
            try:
                has_left = "left_fingerpad" in gripper._important_geoms
                has_right = "right_fingerpad" in gripper._important_geoms
                if not has_left or not has_right:
                    return self._no_grasp_result(
                        f"Gripper missing fingerpad geoms (left={has_left}, right={has_right})"
                    )
            except TypeError:
                return self._no_grasp_result(
                    f"Gripper _important_geoms not iterable: {type(gripper._important_geoms)}"
                )
            try:
                left_contact = env._check_contact(
                    env.sim,
                    gripper._important_geoms["left_fingerpad"],
                    object_to_check.contact_geoms,
                )
            except Exception:
                left_contact = False
            try:
                right_contact = env._check_contact(
                    env.sim,
                    gripper._important_geoms["right_fingerpad"],
                    object_to_check.contact_geoms,
                )
            except Exception:
                right_contact = False
            robot_contact = self._check_robot_contact(env, obj_name)
            is_lifted = height_diff > self.lifted_height_threshold
            (dist_to_left, dist_to_right) = self._get_gripper_object_distances(
                env, obj_name, gripper
            )
            both_fingers_contact = left_contact and right_contact
            between_grippers = (
                dist_to_left is not None
                and dist_to_right is not None
                and (dist_to_left < self.grasp_distance_threshold)
                and (dist_to_right < self.grasp_distance_threshold)
                and (abs(dist_to_left - dist_to_right) < self.grasp_div_threshold)
            )
            between_and_lifted = between_grippers and is_lifted
            is_grasping = both_fingers_contact or between_and_lifted
            grasp_reasons = []
            if is_grasping:
                if both_fingers_contact:
                    grasp_reasons.append("dual_finger_contact")
                if between_and_lifted:
                    grasp_reasons.append("between_grippers_and_lifted")
            return {
                "is_grasping": is_grasping,
                "details": {
                    "left_contact": left_contact,
                    "right_contact": right_contact,
                    "robot_contact": robot_contact,
                    "height_diff": height_diff,
                    "distance": distance,
                    "is_lifted": is_lifted,
                    "dist_to_left_gripper": dist_to_left,
                    "dist_to_right_gripper": dist_to_right,
                    "between_grippers": between_grippers,
                    "grasp_reasons": grasp_reasons,
                    "method": "advanced_multi_criteria",
                },
            }
        except Exception as e:
            return self._no_grasp_result(f"Error: {e}")

    def _calculate_gripper_object_distance(
        self, env: Any, obj_name: str, gripper_pos: np.ndarray
    ) -> Optional[float]:
        try:
            object_to_check = env.get_object(obj_name)
            if object_to_check is None or gripper_pos is None:
                return None
            obj_geoms = object_to_check.contact_geoms
            min_distance = float("inf")
            for obj_geom_name in obj_geoms:
                obj_geom_id = None
                for geom_id in range(env.sim.model.ngeom):
                    if env.sim.model.geom_id2name(geom_id) == obj_geom_name:
                        obj_geom_id = geom_id
                        break
                if obj_geom_id is None:
                    continue
                obj_geom_pos = env.sim.data.geom_xpos[obj_geom_id]
                obj_size = env.sim.model.geom_size[obj_geom_id]
                center_distance = np.linalg.norm(gripper_pos - obj_geom_pos)
                obj_radius = (
                    np.max(obj_size)
                    if obj_size is not None and len(obj_size) > 0
                    else 0.0
                )
                surface_distance = max(0, center_distance - obj_radius)
                min_distance = min(min_distance, surface_distance)
            return min_distance if min_distance != float("inf") else None
        except Exception:
            return None

    def _get_gripper_object_distances(
        self, env: Any, obj_name: str, gripper: Any
    ) -> tuple:
        try:
            if not (hasattr(env, "obj_body_id") and obj_name in env.obj_body_id):
                return (None, None)
            obj_pos = env.sim.data.body_xpos[env.obj_body_id[obj_name]]
            if (
                not hasattr(gripper, "_important_geoms")
                or gripper._important_geoms is None
            ):
                return (None, None)
            left_fingerpad_geom = gripper._important_geoms.get("left_fingerpad")
            right_fingerpad_geom = gripper._important_geoms.get("right_fingerpad")
            if left_fingerpad_geom is None or right_fingerpad_geom is None:
                return (None, None)
            left_geom_id = None
            right_geom_id = None
            left_targets = (
                left_fingerpad_geom
                if isinstance(left_fingerpad_geom, (list, tuple, set))
                else [left_fingerpad_geom]
            )
            right_targets = (
                right_fingerpad_geom
                if isinstance(right_fingerpad_geom, (list, tuple, set))
                else [right_fingerpad_geom]
            )
            for geom_id in range(env.sim.model.ngeom):
                geom_name = env.sim.model.geom_id2name(geom_id)
                if geom_name is None:
                    continue
                if left_geom_id is None:
                    for target in left_targets:
                        if target is None:
                            continue
                        try:
                            if geom_name == target or (
                                target and geom_name and (target in geom_name)
                            ):
                                left_geom_id = geom_id
                                break
                        except TypeError:
                            continue
                if right_geom_id is None:
                    for target in right_targets:
                        if target is None:
                            continue
                        try:
                            if geom_name == target or (
                                target and geom_name and (target in geom_name)
                            ):
                                right_geom_id = geom_id
                                break
                        except TypeError:
                            continue
            if left_geom_id is None or right_geom_id is None:
                return (None, None)
            left_pos = env.sim.data.geom_xpos[left_geom_id]
            right_pos = env.sim.data.geom_xpos[right_geom_id]
            dist_to_left = np.linalg.norm(obj_pos - left_pos)
            dist_to_right = np.linalg.norm(obj_pos - right_pos)
            return (dist_to_left, dist_to_right)
        except Exception:
            return (None, None)

    def _check_robot_contact(self, env: Any, obj_name: str) -> bool:
        try:
            sim = env.sim
            obj = env.get_object(obj_name)
            if obj is None:
                return False
            robot_keywords = [
                "robot",
                "gripper",
                "finger",
                "wrist",
                "forearm",
                "link",
                "hand",
                "arm",
            ]
            for i in range(sim.data.ncon):
                contact = sim.data.contact[i]
                geom1 = sim.model.geom_id2name(contact.geom1)
                geom2 = sim.model.geom_id2name(contact.geom2)
                if geom1 is None or geom2 is None:
                    continue
                is_robot_geom1 = any(
                    (keyword in geom1.lower() for keyword in robot_keywords)
                )
                is_robot_geom2 = any(
                    (keyword in geom2.lower() for keyword in robot_keywords)
                )
                is_robot_contact = is_robot_geom1 or is_robot_geom2
                is_object_contact = obj.name in geom1 or obj.name in geom2
                if is_robot_contact and is_object_contact:
                    return True
            return False
        except Exception:
            return False

    def reset_history(self):
        self.object_initial_heights.clear()

    def get_info(self) -> Dict[str, Any]:
        info = super().get_info()
        info.update(
            {
                "lifted_height_threshold": self.lifted_height_threshold,
                "grasp_distance_threshold": self.grasp_distance_threshold,
                "wait_steps": self.wait_steps,
                "tracked_objects": len(self.object_initial_heights),
            }
        )
        return info


class GraspStrategyManager:
    def __init__(self, default_strategy: str = "advanced"):
        self.strategies = {
            "simple": SimpleContactStrategy(),
            "dual": DualFingerStrategy(),
            "advanced": AdvancedGraspStrategy(),
        }
        self.current_strategy_name = default_strategy

    def set_strategy(self, strategy_name: str):
        if strategy_name not in self.strategies:
            available = list(self.strategies.keys())
            raise ValueError(
                f"Unknown strategy '{strategy_name}'. Available: {available}"
            )
        self.current_strategy_name = strategy_name

    def get_strategy(self) -> GraspDetectionStrategy:
        return self.strategies[self.current_strategy_name]

    def register_strategy(self, name: str, strategy: GraspDetectionStrategy):
        self.strategies[name] = strategy

    def detect(self, env: Any, obj_name: str, **kwargs) -> Dict[str, Any]:
        strategy = self.get_strategy()
        return strategy.detect(env, obj_name, **kwargs)

    def reset_history(self):
        for strategy in self.strategies.values():
            if hasattr(strategy, "reset_history"):
                strategy.reset_history()

    def get_info(self) -> Dict[str, Any]:
        return {
            "current_strategy": self.current_strategy_name,
            "available_strategies": list(self.strategies.keys()),
            "strategy_info": self.get_strategy().get_info(),
        }


def check_grasping(object_state):
    env = object_state.env
    object_name = object_state.object_name
    return env.check_grasping(object_name)
