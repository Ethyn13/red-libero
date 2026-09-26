"""Inspect and toggle articulated object joints."""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


def detect_object_joints(env, obj_name: str) -> List[Dict]:
    joints = []
    try:
        for joint_id in range(env.sim.model.njnt):
            joint_name = env.sim.model.joint_id2name(joint_id)
            if obj_name in joint_name and joint_name != obj_name:
                joint_type = env.sim.model.jnt_type[joint_id]
                if joint_type in [2, 3]:
                    qpos_addr = env.sim.model.jnt_qposadr[joint_id]
                    jnt_range = env.sim.model.jnt_range[joint_id]
                    has_limits = bool(env.sim.model.jnt_limited[joint_id])
                    joint_body_id = env.sim.model.jnt_bodyid[joint_id]
                    joint_body_name = env.sim.model.body_id2name(joint_body_id)
                    joints.append(
                        {
                            "name": joint_name,
                            "id": joint_id,
                            "type": "slide" if joint_type == 2 else "hinge",
                            "qpos_addr": qpos_addr,
                            "dof_addr": env.sim.model.jnt_dofadr[joint_id],
                            "range": tuple(jnt_range) if has_limits else None,
                            "current_pos": env.sim.data.qpos[qpos_addr],
                            "body_id": joint_body_id,
                            "body_name": joint_body_name,
                        }
                    )
    except Exception as e:
        logger.warning(f"Detect object joints failed: e={e}")
    return joints


def resolve_joint(model, joints, body_id=None):
    """Resolve a clicked body to its nearest joint-bearing ancestor."""
    if body_id is None:
        return next(iter(joints), None)
    visited = set()
    while 0 < body_id < model.nbody and body_id not in visited:
        visited.add(body_id)
        for joint in joints:
            if joint["body_id"] == body_id:
                return joint
        body_id = int(model.body_parentid[body_id])
    return None


def queue_joint_toggle(editor, obj_name, body_id=None):
    joints = editor.object_info.get(obj_name, {}).get("joints", [])
    joint = resolve_joint(editor.env.sim.model, joints, body_id)
    if joint is None or joint.get("range") is None:
        if getattr(editor, "studio", None):
            editor.studio.log("Selected part has no movable joint with limits.")
        return False
    current = editor.env.sim.data.qpos[joint["qpos_addr"]]
    for change in editor._pending_joint_changes:
        if change["qpos_addr"] == joint["qpos_addr"]:
            current = change["target_pos"]
    lower, upper = joint["range"]
    target = upper if abs(current - lower) < (upper - lower) * 0.3 else lower
    editor._pending_joint_changes.append({
        "qpos_addr": joint["qpos_addr"],
        "target_pos": target,
        "joint_name": joint["name"],
    })
    if getattr(editor, "studio", None):
        editor.studio.log(f"Joint: {joint['name']} ({current:.3f} → {target:.3f}).")
    return True
