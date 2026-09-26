import robosuite.utils.transform_utils as transform_utils
import numpy as np
from shapely.geometry import Polygon
try:
    from scipy.spatial import ConvexHull
except ImportError:
    ConvexHull = None


class BaseObjectState:
    def __init__(self):
        pass

    def get_geom_state(self):
        raise NotImplementedError

    def check_contact(self, other):
        raise NotImplementedError

    def check_contain(self, other):
        raise NotImplementedError

    def get_joint_state(self):
        raise NotImplementedError

    def is_open(self):
        raise NotImplementedError

    def is_close(self):
        raise NotImplementedError

    def is_almost_close(self):
        raise NotImplementedError

    def get_size(self):
        raise NotImplementedError

    def check_ontop(self, other):
        raise NotImplementedError


class ObjectState(BaseObjectState):
    def __init__(self, env, object_name, is_fixture=False):
        self.env = env
        self.object_name = object_name
        self.is_fixture = is_fixture
        self.query_dict = (
            self.env.fixtures_dict if self.is_fixture else self.env.objects_dict
        )
        self.object_state_type = "object"
        self.has_turnon_affordance = hasattr(
            self.env.get_object(self.object_name), "turn_on"
        )

    def get_geom_state(self):
        object_pos = self.env.sim.data.body_xpos[self.env.obj_body_id[self.object_name]]
        object_quat = self.env.sim.data.body_xquat[
            self.env.obj_body_id[self.object_name]
        ]
        return {"pos": object_pos, "quat": object_quat}

    def check_contact(self, other):
        object_1 = self.env.get_object(self.object_name)
        object_2 = self.env.get_object(other.object_name)
        return self.env.check_contact(object_1, object_2)

    def check_collision(self):
        return self.env.check_collision(self.object_name)

    def check_force(self, other=None, threshold=10.0):
        """Return whether contact force exceeds threshold in newtons; other=None checks all contacts."""
        object_1 = self.env.get_object(self.object_name)
        object_2 = self.env.get_object(other.object_name) if other is not None else None
        return self.env.check_force(object_1, object_2, threshold)

    def check_distance(self, other):
        object_1 = self.env.get_object(self.object_name)
        object_2 = self.env.get_object(other.object_name)
        return self.env.check_distance(object_1, object_2)

    def check_gripper_distance(self):
        object_1 = self.env.get_object(self.object_name)
        return self.env.check_gripper_distance(object_1)

    def check_contain(self, other):
        object_1 = self.env.get_object(self.object_name)
        object_1_position = self.env.sim.data.body_xpos[
            self.env.obj_body_id[self.object_name]
        ]
        object_2 = self.env.get_object(other.object_name)
        object_2_position = self.env.sim.data.body_xpos[
            self.env.obj_body_id[other.object_name]
        ]
        return object_1.in_box(object_1_position, object_2_position)

    def get_joint_state(self):
        # Return None if joint state does not exist
        joint_states = []
        for joint in self.env.get_object(self.object_name).joints:
            qpos_addr = self.env.sim.model.get_joint_qpos_addr(joint)
            joint_states.append(self.env.sim.data.qpos[qpos_addr])
        return joint_states

    def check_ontop(self, other):
        this_object = self.env.get_object(self.object_name)
        this_object_position = self.env.sim.data.body_xpos[
            self.env.obj_body_id[self.object_name]
        ]
        other_object = self.env.get_object(other.object_name)
        other_object_position = self.env.sim.data.body_xpos[
            self.env.obj_body_id[other.object_name]
        ]
        return (
            (this_object_position[2] <= other_object_position[2])
            and self.check_contact(other)
            and (
                np.linalg.norm(this_object_position[:2] - other_object_position[:2])
                < 0.07
            )
        )

    def _get_object_projection(self, object_name, debug=False):
        """Return the XY projection of an object or site as a Shapely polygon."""
        if object_name in getattr(self.env, 'object_sites_dict', {}):
            site_pos = self.env.sim.data.get_site_xpos(object_name)
            site_mat = self.env.sim.data.get_site_xmat(object_name).reshape(3, 3)

            # Prefer the actual MuJoCo site dimensions over the object metadata.
            site_size = np.array([0.05, 0.05, 0.05])
            try:
                site_id = self.env.sim.model.site_name2id(object_name)
                site_model_size = self.env.sim.model.site_size[site_id]
                if np.any(site_model_size > 0):
                    site_size = site_model_size.copy()
                    if debug:
                        print(f"DEBUG: Site {object_name} size from MuJoCo: {site_size}")
            except Exception as e:
                if debug:
                    print(f"DEBUG: Could not read site size from MuJoCo; using fallback: {e}")

                site_obj = self.env.object_sites_dict[object_name]
                if hasattr(site_obj, 'size') and site_obj.size is not None:
                    site_size = np.array(site_obj.size)
                    if debug:
                        print(f"DEBUG: Site {object_name} size from site_obj.size: {site_size}")

            if debug:
                print(f"DEBUG: Site {object_name} projection uses pos={site_pos}, size={site_size}")

            # Project all eight corners so rotated sites do not collapse to a line.
            half_x, half_y, half_z = site_size[0], site_size[1], site_size[2]

            corners_local = np.array([
                [-half_x, -half_y, -half_z],
                [half_x, -half_y, -half_z],
                [half_x, half_y, -half_z],
                [-half_x, half_y, -half_z],
                [-half_x, -half_y, half_z],
                [half_x, -half_y, half_z],
                [half_x, half_y, half_z],
                [-half_x, half_y, half_z],
            ])

            # Transform to world
            corners_world = (site_mat @ corners_local.T).T + site_pos

            if debug:
                print(f"DEBUG: Site {object_name} corners_world (8 vertices):\n{corners_world}")
                print(f"DEBUG: Site {object_name} projection_xy:\n{corners_world[:, :2]}")

            projection_xy = corners_world[:, :2]
            try:
                if ConvexHull is not None and len(projection_xy) >= 3:
                    hull = ConvexHull(projection_xy)
                    hull_points = projection_xy[hull.vertices]
                else:
                    # Use a bounding box when the projected hull is degenerate.
                    min_x, min_y = projection_xy.min(axis=0)
                    max_x, max_y = projection_xy.max(axis=0)
                    hull_points = np.array([
                        [min_x, min_y], [max_x, min_y],
                        [max_x, max_y], [min_x, max_y],
                    ])
            except:
                # Use a bounding box when the projected hull is degenerate.
                min_x, min_y = projection_xy.min(axis=0)
                max_x, max_y = projection_xy.max(axis=0)
                hull_points = np.array([
                    [min_x, min_y], [max_x, min_y],
                    [max_x, max_y], [min_x, max_y],
            ])

            polygon = Polygon(hull_points)
            if not polygon.is_valid:
                polygon = polygon.buffer(0)

            if debug:
                print(f"DEBUG: Site {object_name} convex hull vertices: {len(hull_points)}")
                print(f"DEBUG: Site {object_name} polygon area={polygon.area:.6f}, valid={polygon.is_valid}")

            return polygon

        body_id = self.env.obj_body_id.get(object_name)
        if body_id is None:
            body_pos = np.array([0.0, 0.0, 0.0])
            default_size = 0.05
            points = np.array([
                [body_pos[0] - default_size, body_pos[1] - default_size],
                [body_pos[0] + default_size, body_pos[1] - default_size],
                [body_pos[0] + default_size, body_pos[1] + default_size],
                [body_pos[0] - default_size, body_pos[1] + default_size],
            ])
            return Polygon(points)

        all_points = []
        body_pos = self.env.sim.data.body_xpos[body_id]

        for geom_id in range(self.env.sim.model.ngeom):
            if self.env.sim.model.geom_bodyid[geom_id] != body_id:
                continue

            geom_type = self.env.sim.model.geom_type[geom_id]
            geom_size = self.env.sim.model.geom_size[geom_id]
            geom_pos = self.env.sim.data.geom_xpos[geom_id]
            geom_xmat = self.env.sim.data.geom_xmat[geom_id].reshape(3, 3)

            if geom_type == 1:  # BOX
                half_x, half_y, half_z = geom_size[0], geom_size[1], geom_size[2]
                vertices_local = np.array([
                    [-half_x, -half_y, -half_z], [half_x, -half_y, -half_z],
                    [half_x, half_y, -half_z], [-half_x, half_y, -half_z],
                    [-half_x, -half_y, half_z], [half_x, -half_y, half_z],
                    [half_x, half_y, half_z], [-half_x, half_y, half_z],
                ])
                vertices_world = (geom_xmat @ vertices_local.T).T + geom_pos
                all_points.extend(vertices_world[:, :2])
            elif geom_type in [0, 3, 4]:  # SPHERE, CAPSULE, CYLINDER
                radius = geom_size[0]
                all_points.extend([
                    [geom_pos[0] - radius, geom_pos[1] - radius],
                    [geom_pos[0] + radius, geom_pos[1] - radius],
                    [geom_pos[0] + radius, geom_pos[1] + radius],
                    [geom_pos[0] - radius, geom_pos[1] + radius],
                ])
            elif geom_type in [6, 7]:  # MESH, HFIELD
                # AABB dimensions are static; center them on the current world-space geom position.
                try:
                    aabb = self.env.sim.model.geom_aabb[geom_id]
                    # AABB layout: center_xyz followed by half_size_xyz.
                    half_size_x, half_size_y = aabb[3], aabb[4]
                    all_points.extend([
                        [geom_pos[0] - half_size_x, geom_pos[1] - half_size_y],
                        [geom_pos[0] + half_size_x, geom_pos[1] - half_size_y],
                        [geom_pos[0] + half_size_x, geom_pos[1] + half_size_y],
                        [geom_pos[0] - half_size_x, geom_pos[1] + half_size_y],
                    ])
                except:
                    half_x = max(geom_size[0] if len(geom_size) > 0 else 0.01, 0.01)
                    half_y = max(geom_size[1] if len(geom_size) > 1 else 0.01, 0.01)
                    all_points.extend([
                        [geom_pos[0] - half_x, geom_pos[1] - half_y],
                        [geom_pos[0] + half_x, geom_pos[1] - half_y],
                        [geom_pos[0] + half_x, geom_pos[1] + half_y],
                        [geom_pos[0] - half_x, geom_pos[1] + half_y],
                    ])

        if not all_points:
            default_size = 0.05
            points = np.array([
                [body_pos[0] - default_size, body_pos[1] - default_size],
                [body_pos[0] + default_size, body_pos[1] - default_size],
                [body_pos[0] + default_size, body_pos[1] + default_size],
                [body_pos[0] - default_size, body_pos[1] + default_size],
            ])
            return Polygon(points)

        all_points = np.array(all_points)
        try:
            if ConvexHull is not None and len(all_points) >= 3:
                hull = ConvexHull(all_points)
                points = all_points[hull.vertices]
            else:
                min_x, min_y = all_points.min(axis=0)
                max_x, max_y = all_points.max(axis=0)
                points = np.array([
                    [min_x, min_y], [max_x, min_y],
                    [max_x, max_y], [min_x, max_y],
                ])
        except:
            min_x, min_y = all_points.min(axis=0)
            max_x, max_y = all_points.max(axis=0)
            points = np.array([
                [min_x, min_y], [max_x, min_y],
                [max_x, max_y], [min_x, max_y],
            ])

        polygon = Polygon(points)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        return polygon

    def _compute_projection_overlap(self, poly1, poly2):
        """Return the intersection area and overlap ratios of two projections."""
        if not poly1.is_valid or not poly2.is_valid:
            return 0.0, poly1.area, poly2.area, 0.0, 0.0

        intersection = poly1.intersection(poly2)
        intersection_area = intersection.area if not intersection.is_empty else 0.0
        area1, area2 = poly1.area, poly2.area

        overlap_ratio1 = intersection_area / area1 if area1 > 0 else 0.0
        overlap_ratio2 = intersection_area / area2 if area2 > 0 else 0.0

        return intersection_area, area1, area2, overlap_ratio1, overlap_ratio2

    def check_over(self, other, debug=False, overlap_threshold=0.6, z_tolerance=0.15):
        """Check whether other is above this object with sufficient XY projection overlap.

        Objects and sites are supported. z_tolerance allows other to be
        slightly lower, by at most the specified distance in meters.
        """
        if self.object_name in getattr(self.env, 'object_sites_dict', {}):
            this_pos = self.env.sim.data.get_site_xpos(self.object_name)
        else:
            this_pos = self.env.sim.data.body_xpos[self.env.obj_body_id[self.object_name]]

        if other.object_name in getattr(self.env, 'object_sites_dict', {}):
            other_pos = self.env.sim.data.get_site_xpos(other.object_name)
        else:
            other_pos = self.env.sim.data.body_xpos[self.env.obj_body_id[other.object_name]]

        z_diff = other_pos[2] - this_pos[2]
        z_above = z_diff > -z_tolerance  # Allow other to sit at most z_tolerance meters below this object.

        try:
            this_proj = self._get_object_projection(self.object_name, debug=False)
            other_proj = self._get_object_projection(other.object_name, debug=False)
            intersection_area, area1, area2, ratio1, ratio2 = self._compute_projection_overlap(this_proj, other_proj)
            horizontally_aligned = (ratio1 >= overlap_threshold) or (ratio2 >= overlap_threshold)
        except Exception as e:
            horizontally_aligned = np.linalg.norm(this_pos[:2] - other_pos[:2]) < 0.15

        return z_above and horizontally_aligned

    def check_projection_overlap(self, other, overlap_threshold=0.6, debug=False, verbose=False):
        """Check whether intersection covers at least overlap_threshold of either XY projection.

        Supports objects and sites. debug reports overlapping cases; verbose
        also reports projection details when there is no overlap.
        """
        try:
            this_proj = self._get_object_projection(self.object_name, debug=False)
            other_proj = self._get_object_projection(other.object_name, debug=False)

            intersection_area, area1, area2, ratio1, ratio2 = self._compute_projection_overlap(this_proj, other_proj)

            is_overlapping = (ratio1 >= overlap_threshold) or (ratio2 >= overlap_threshold)

            return is_overlapping

        except Exception as e:
            return False
    def set_joint(self, qpos=1.5):
        for joint in self.env.get_object(self.object_name).joints:
            self.env.sim.data.set_joint_qpos(joint, qpos)

    def is_open(self):
        for joint in self.env.get_object(self.object_name).joints:
            qpos_addr = self.env.sim.model.get_joint_qpos_addr(joint)
            qpos = self.env.sim.data.qpos[qpos_addr]
            if self.env.get_object(self.object_name).is_open(qpos):
                return True
        return False

    def is_close(self):
        for joint in self.env.get_object(self.object_name).joints:
            qpos_addr = self.env.sim.model.get_joint_qpos_addr(joint)
            qpos = self.env.sim.data.qpos[qpos_addr]
            if not (self.env.get_object(self.object_name).is_close(qpos)):
                return False
        return True

    def is_almost_close(self):
        """Check relaxed joint closure, falling back to is_close when unsupported by the object."""
        obj = self.env.get_object(self.object_name)

        if not hasattr(obj, 'is_almost_close'):
            return self.is_close()

        for joint in obj.joints:
            qpos_addr = self.env.sim.model.get_joint_qpos_addr(joint)
            qpos = self.env.sim.data.qpos[qpos_addr]
            if not obj.is_almost_close(qpos):
                return False
        return True

    def turn_on(self):
        obj = self.env.get_object(self.object_name)

        if not hasattr(obj, 'turn_on'):
            return False

        if not hasattr(obj, 'joints') or not obj.joints:
            return False


        if hasattr(obj, 'object_properties') and 'articulation' in obj.object_properties:
            turnon_ranges = obj.object_properties['articulation'].get('default_turnon_ranges', None)

        for i, joint in enumerate(obj.joints):
            qpos_addr = self.env.sim.model.get_joint_qpos_addr(joint)
            qpos = self.env.sim.data.qpos[qpos_addr]

            try:
                joint_id = self.env.sim.model.joint_name2id(joint)
                joint_name = self.env.sim.model.joint_id2name(joint_id)
            except:
                joint_name = str(joint)

            turn_on_result = obj.turn_on(qpos)
            if turn_on_result:
                return True

        return False

    def turn_off(self):
        for joint in self.env.get_object(self.object_name).joints:
            qpos_addr = self.env.sim.model.get_joint_qpos_addr(joint)
            qpos = self.env.sim.data.qpos[qpos_addr]
            if not (self.env.get_object(self.object_name).turn_off(qpos)):
                return False
        return True

    def update_state(self):
        if self.has_turnon_affordance:
            self.turn_on()

    def fall(self):
        """Detect a fall from changes in object position and orientation."""
        original_pos = self.env.object_original_pos.get(self.object_name)
        original_quat = self.env.object_original_quat.get(self.object_name)

        if original_pos is None or original_quat is None:
            return False

        current_pos = self.env.sim.data.body_xpos[self.env.obj_body_id[self.object_name]]
        current_quat = self.env.sim.data.body_xquat[self.env.obj_body_id[self.object_name]]

        pos_diff = np.linalg.norm(current_pos - original_pos)
        height_drop = original_pos[2] - current_pos[2]  # Positive displacement indicates a drop.
        xy_diff = np.linalg.norm(current_pos[:2] - original_pos[:2])

        pos_fall = (pos_diff > 0.1) or \
                (height_drop > 0.05) or \
                (xy_diff > 0.15)

        quat_diff = transform_utils.quat_multiply(
            current_quat,
            transform_utils.quat_inverse(original_quat)
        )
        quat_diff_euler = transform_utils.quat2axisangle(quat_diff)

        rotation_fall = (abs(quat_diff_euler[0]) > 0.2) or \
                    (abs(quat_diff_euler[1]) > 0.2) or \
                    (abs(quat_diff_euler[2]) > 0.5)

        return pos_fall or rotation_fall

    def check_gripper_contact(self):
        object_1 = self.env.get_object(self.object_name)
        return self.env.check_gripper_contact(object_1)

    def knock(self):
        """Check whether the robot has just knocked this object."""
        return self.env.check_robot_knock(self.object_name)

    def knock_with(self, other_object):
        """Check whether brief contact with another object has just ended."""
        return self.env.check_object_object_knock(self.object_name, other_object.object_name)

    def check_sweeping(self, debug=False):
        """Delegate horizontal sweeping detection to the environment."""
        return self.env.check_sweeping(self.object_name, debug=debug)

    def check_in_contact_part(self, object_name, geom_name_1, geom_name_2):
        object_1 = self.env.get_object(self.object_name)
        object_2 = self.env.get_object(object_name)
        return self.env.check_in_contact_part(object_1, object_2, geom_name_1, geom_name_2)

    def check_gripper_contact_part(self, geom_name_1):
        object_1 = self.env.get_object(self.object_name)
        return self.env.check_gripper_contact_part(object_1, geom_name_1)

    def check_blade_contact(self):
        """Check gripper contact with the object's blade geometry."""
        return self.env.check_blade_contact(self.object_name)

    def check_arm_blade_contact(self):
        """Check contact between any arm link and the object's blade geometry."""
        return self.env.check_arm_blade_contact(self.object_name)

    def check_arm_force(self):
        """Check whether arm contact force exceeds the threshold."""
        return self.env.check_arm_force()

    def check_arm_stuck(self):
        """Check for sustained arm contact force with negligible joint motion."""
        return self.env.check_arm_stuck()

    def waterfall(self, other):
        return (not self.check_contact(other))&self.fall()

class SiteObjectState(BaseObjectState):
    """
    This is to make site based objects to have the same API as normal Object State.
    """

    def __init__(self, env, object_name, parent_name, is_fixture=False):
        self.env = env
        self.object_name = object_name
        self.parent_name = parent_name
        self.is_fixture = self.parent_name in self.env.fixtures_dict
        self.query_dict = (
            self.env.fixtures_dict if self.is_fixture else self.env.objects_dict
        )
        self.object_state_type = "site"

    def get_geom_state(self):
        object_pos = self.env.sim.data.get_site_xpos(self.object_name)
        object_quat = transform_utils.mat2quat(
            self.env.sim.data.get_site_xmat(self.object_name)
        )
        return {"pos": object_pos, "quat": object_quat}

    def check_contain(self, other):
        this_object = self.env.object_sites_dict[self.object_name]
        this_object_position = self.env.sim.data.get_site_xpos(self.object_name)
        this_object_mat = self.env.sim.data.get_site_xmat(self.object_name)

        other_object = self.env.get_object(other.object_name)
        other_object_position = self.env.sim.data.body_xpos[
            self.env.obj_body_id[other.object_name]
        ]
        return this_object.in_box(
            this_object_position, this_object_mat, other_object_position
        )

    def check_contact(self, other):
        """
        There is no dynamics for site objects, so we return true all the time.
        """
        return True

    def check_ontop(self, other):
        this_object = self.env.object_sites_dict[self.object_name]
        if hasattr(this_object, "under"):
            this_object_position = self.env.sim.data.get_site_xpos(self.object_name)
            this_object_mat = self.env.sim.data.get_site_xmat(self.object_name)
            other_object = self.env.get_object(other.object_name)
            other_object_position = self.env.sim.data.body_xpos[
                self.env.obj_body_id[other.object_name]
            ]
            # print(self.object_name, this_object_position)
            # print(other_object_position)

            parent_object = self.env.get_object(self.parent_name)
            if parent_object is None:
                return this_object.under(
                    this_object_position, this_object_mat, other_object_position
                )
            else:
                return this_object.under(
                    this_object_position, this_object_mat, other_object_position
                ) and self.env.check_contact(parent_object, other_object)
        else:
            return True

    def set_joint(self, qpos=1.5):
        for joint in self.env.object_sites_dict[self.object_name].joints:
            self.env.sim.data.set_joint_qpos(joint, qpos)

    def is_open(self):
        for joint in self.env.object_sites_dict[self.object_name].joints:
            qpos_addr = self.env.sim.model.get_joint_qpos_addr(joint)
            qpos = self.env.sim.data.qpos[qpos_addr]
            if self.env.get_object(self.parent_name).is_open(qpos):
                return True
        return False

    def is_close(self):
        for joint in self.env.object_sites_dict[self.object_name].joints:
            qpos_addr = self.env.sim.model.get_joint_qpos_addr(joint)
            qpos = self.env.sim.data.qpos[qpos_addr]
            if not (self.env.get_object(self.parent_name).is_close(qpos)):
                return False
        return True

    def is_almost_close(self):
        """Check relaxed joint closure for the parent object, falling back to is_close."""
        parent_obj = self.env.get_object(self.parent_name)

        if not hasattr(parent_obj, 'is_almost_close'):
            return self.is_close()

        for joint in self.env.object_sites_dict[self.object_name].joints:
            qpos_addr = self.env.sim.model.get_joint_qpos_addr(joint)
            qpos = self.env.sim.data.qpos[qpos_addr]
            if not parent_obj.is_almost_close(qpos):
                return False
        return True


# Reuse projection helpers for site objects.
SiteObjectState._get_object_projection = ObjectState._get_object_projection
SiteObjectState._compute_projection_overlap = ObjectState._compute_projection_overlap
SiteObjectState.check_over = ObjectState.check_over
SiteObjectState.check_projection_overlap = ObjectState.check_projection_overlap
