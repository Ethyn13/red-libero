import collections
import numpy as np
import os
import re
import robosuite
import xml.etree.ElementTree as ET
import time

from copy import copy
from robosuite.utils.mjcf_utils import find_elements, xml_path_completion
from robosuite.utils.placement_samplers import ObjectPositionSampler

class RandomizationError(Exception):
    """Custom exception raised when randomization fails (e.g., object placement)."""
    pass

class MultiRegionRandomSampler(ObjectPositionSampler):
    """
    Places all objects within the table uniformly random.
    Args:
        name (str): Name of this sampler.
        mujoco_objects (None or MujocoObject or list of MujocoObject): single model or list of MJCF object models
        x_range (2-array of float): Specify the (min, max) relative x_range used to uniformly place objects
        y_range (2-array of float): Specify the (min, max) relative y_range used to uniformly place objects
        rotation (None or float or Iterable):
            :`None`: Add uniform random random rotation
            :`Iterable (a,b)`: Uniformly randomize rotation angle between a and b (in radians)
            :`value`: Add fixed angle rotation
        rotation_axis (str): Can be 'x', 'y', or 'z'. Axis about which to apply the requested rotation
        ensure_object_boundary_in_range (bool):
            :`True`: The center of object is at position:
                 [uniform(min x_range + radius, max x_range - radius)], [uniform(min x_range + radius, max x_range - radius)]
            :`False`:
                [uniform(min x_range, max x_range)], [uniform(min x_range, max x_range)]
        ensure_valid_placement (bool): If True, will check for correct (valid) object placements
        reference_pos (3-array): global (x,y,z) position relative to which sampling will occur
        z_offset (float): Add a small z-offset to placements. This is useful for fixed objects
            that do not move (i.e. no free joint) to place them above the table.
    """

    def __init__(
        self,
        name,
        mujoco_objects=None,
        x_ranges=[(0, 0)],
        y_ranges=[(0, 0)],
        rotation=None,
        rotation_axis="z",
        ensure_object_boundary_in_range=True,
        ensure_valid_placement=True,
        reference_pos=(0, 0, 0),
        z_offset=0.0,
    ):
        self.x_ranges = x_ranges
        self.y_ranges = y_ranges
        assert len(self.x_ranges) == len(self.y_ranges)
        self.num_ranges = len(self.x_ranges)
        self.idx = 0
        self.rotation = rotation
        self.rotation_axis = rotation_axis
        self.idx = 0

        super().__init__(
            name=name,
            mujoco_objects=mujoco_objects,
            ensure_object_boundary_in_range=ensure_object_boundary_in_range,
            ensure_valid_placement=ensure_valid_placement,
            reference_pos=reference_pos,
            z_offset=z_offset,
        )

    def _sample_x(self, object_horizontal_radius):
        """
        Samples the x location for a given object
        Args:
            object_horizontal_radius (float): Radius of the object currently being sampled for
        Returns:
            float: sampled x position
        """
        minimum, maximum = self.x_ranges[self.idx]
        if self.ensure_object_boundary_in_range:
            minimum += object_horizontal_radius
            maximum -= object_horizontal_radius
        return np.random.uniform(high=maximum, low=minimum)

    def _sample_y(self, object_horizontal_radius):
        """
        Samples the y location for a given object
        Args:
            object_horizontal_radius (float): Radius of the object currently being sampled for
        Returns:
            float: sampled y position
        """
        minimum, maximum = self.y_ranges[self.idx]
        if self.ensure_object_boundary_in_range:
            minimum += object_horizontal_radius
            maximum -= object_horizontal_radius
        return np.random.uniform(high=maximum, low=minimum)

    def _sample_quat(self):
        """
        Samples the orientation for a given object
        Returns:
            np.array: sampled (r,p,y) euler angle orientation
        Raises:
            ValueError: [Invalid rotation axis]
        """
        if self.rotation is None:
            rot_angle = np.random.uniform(high=2 * np.pi, low=0)
        elif isinstance(self.rotation, collections.Iterable):
            rot_angle = np.random.uniform(
                high=max(self.rotation), low=min(self.rotation)
            )
        else:
            rot_angle = self.rotation

        # Return angle based on axis requested
        if self.rotation_axis == "x":
            return np.array([np.cos(rot_angle / 2), np.sin(rot_angle / 2), 0, 0])
        elif self.rotation_axis == "y":
            return np.array([np.cos(rot_angle / 2), 0, np.sin(rot_angle / 2), 0])
        elif self.rotation_axis == "z":
            return np.array([np.cos(rot_angle / 2), 0, 0, np.sin(rot_angle / 2)])
        else:
            # Invalid axis specified, raise error
            raise ValueError(
                "Invalid rotation axis specified. Must be 'x', 'y', or 'z'. Got: {}".format(
                    self.rotation_axis
                )
            )

    def sample(self, fixtures=None, reference=None, on_top=True):
        """
        Uniformly sample relative to this sampler's reference_pos or @reference (if specified).
        Args:
            fixtures (dict): dictionary of current object placements in the scene as well as any other relevant
                obstacles that should not be in contact with newly sampled objects. Used to make sure newly
                generated placements are valid. Should be object names mapped to (pos, quat, MujocoObject)
            reference (str or 3-tuple or None): if provided, sample relative placement. Can either be a string, which
                corresponds to an existing object found in @fixtures, or a direct (x,y,z) value. If None, will sample
                relative to this sampler's `'reference_pos'` value.
            on_top (bool): if True, sample placement on top of the reference object. This corresponds to a sampled
                z-offset of the current sampled object's bottom_offset + the reference object's top_offset
                (if specified)
        Return:
            dict: dictionary of all object placements, mapping object_names to (pos, quat, obj), including the
                placements specified in @fixtures. Note quat is in (w,x,y,z) form
        Raises:
            RandomizationError: [Cannot place all objects]
            AssertionError: [Reference object name does not exist, invalid inputs]
        """
        # Standardize inputs
        placed_objects = {} if fixtures is None else copy(fixtures)
        if reference is None:
            base_offset = self.reference_pos
        elif type(reference) is str:
            assert (
                reference in placed_objects
            ), "Invalid reference received. Current options are: {}, requested: {}".format(
                placed_objects.keys(), reference
            )
            ref_pos, _, ref_obj = placed_objects[reference]
            base_offset = np.array(ref_pos)
            if on_top:
                base_offset += np.array((0, 0, ref_obj.top_offset[-1]))
        else:
            base_offset = np.array(reference)
            assert (
                base_offset.shape[0] == 3
            ), "Invalid reference received. Should be (x,y,z) 3-tuple, but got: {}".format(
                base_offset
            )

        # Sample pos and quat for all objects assigned to this sampler
        for obj in self.mujoco_objects:
            # First make sure the currently sampled object hasn't already been sampled
            assert (
                obj.name not in placed_objects
            ), "Object '{}' has already been sampled!".format(obj.name)

            horizontal_radius = obj.horizontal_radius
            bottom_offset = obj.bottom_offset
            success = False
            for i in range(5000):  # 5000 retries
                self.idx = np.random.randint(self.num_ranges)
                object_x = self._sample_x(horizontal_radius) + base_offset[0]
                object_y = self._sample_y(horizontal_radius) + base_offset[1]
                object_z = self.z_offset + base_offset[2]
                if on_top:
                    object_z -= bottom_offset[-1]

                # objects cannot overlap
                location_valid = True
                if self.ensure_valid_placement:
                    for (x, y, z), _, other_obj in placed_objects.values():
                        if (
                            np.linalg.norm((object_x - x, object_y - y))
                            <= other_obj.horizontal_radius + horizontal_radius
                        ) and (
                            object_z - z <= other_obj.top_offset[-1] - bottom_offset[-1]
                        ):
                            location_valid = False
                            break

                if location_valid:
                    # random rotation
                    quat = self._sample_quat()

                    # multiply this quat by the object's initial rotation if it has the attribute specified
                    if hasattr(obj, "init_quat"):
                        quat = quat_multiply(quat, obj.init_quat)

                    # location is valid, put the object down
                    pos = (object_x, object_y, object_z)

                    placed_objects[obj.name] = (pos, quat, obj)
                    success = True
                    break

            if not success:
                raise RandomizationError("Cannot place all objects ):")
        # print(placed_objects)
        return placed_objects

def quat_multiply(q1, q2):
    """
    Multiply two quaternions q1 and q2.
    Quaternion format: [x, y, z, w]

    Returns:
        result quaternion: [x, y, z, w]
    """
    x1, y1, z1, w1 = q1
    x2, y2, z2, w2 = q2

    x = w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2
    y = w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2
    z = w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2
    w = w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2

    return np.array([x, y, z, w])

def postprocess_model_xml(xml_str, cameras_dict={}, demo_generation=False):
    """
    This function postprocesses the model.xml collected from a MuJoCo demonstration
    in order to make sure that the STL files can be found.

    Args:
        xml_str (str): Mujoco sim demonstration XML file as string

    Returns:
        str: Post-processed xml file as string
    """

    path = os.path.split(robosuite.__file__)[0]
    path_split = path.split("/")

    # replace mesh and texture file paths
    tree = ET.fromstring(xml_str)
    root = tree
    asset = root.find("asset")
    meshes = asset.findall("mesh")
    textures = asset.findall("texture")
    all_elements = meshes + textures

    # also replace paths for libero
    libero_path = os.getcwd() + "/libero"
    libero_path_split = libero_path.split("/")

    # replace paths for vla_arena
    vla_arena_path = os.getcwd() + "/vla_arena"
    vla_arena_path_split = vla_arena_path.split("/")

    for elem in all_elements:
        old_path = elem.get("file")
        if old_path is None:
            continue
        old_path_split = old_path.split("/")
        if "robosuite" in old_path_split:
            ind = max(
                loc for loc, val in enumerate(old_path_split) if val == "robosuite"
            )  # last occurrence index
            new_path_split = path_split + old_path_split[ind + 1 :]
            new_path = "/".join(new_path_split)
            elem.set("file", new_path)
        elif "libero" in old_path_split and demo_generation:
            ind = max(
                loc for loc, val in enumerate(old_path_split) if val == "libero"
            )  # last occurrence index
            new_path_split = libero_path_split + old_path_split[ind + 1 :]
            new_path = "/".join(new_path_split)
            elem.set("file", new_path)
        elif "vla_arena" in old_path_split and demo_generation:
            ind = max(
                loc for loc, val in enumerate(old_path_split) if val == "vla_arena"
            )   # last occurrence index
            new_path_split = vla_arena_path_split + old_path_split[ind + 1 :]
            new_path = "/".join(new_path_split)
            elem.set("file", new_path)
        else:
            continue

    # cameras = root.find("worldbody").findall("camera")
    cameras = find_elements(root=tree, tags="camera", return_first=False)
    for camera in cameras:
        camera_name = camera.get("name")
        if camera_name in cameras_dict:
            camera.set("name", camera_name)
            camera.set("pos", cameras_dict[camera_name]["pos"])
            camera.set("quat", cameras_dict[camera_name]["quat"])
            camera.set("mode", "fixed")

    return ET.tostring(root, encoding="utf8").decode("utf8")


def rectangle2xyrange(rect_ranges):
    x_ranges = []
    y_ranges = []
    for rect_range in rect_ranges:
        x_ranges.append([rect_range[0], rect_range[2]])
        y_ranges.append([rect_range[1], rect_range[3]])
    return x_ranges, y_ranges


class LinearMotionGenerator:
    def __init__(self, start_pos, start_quat, direction, cycle_time, travel_dist, dt=1):
        """Initialize a back-and-forth linear trajectory.

        start_pos and travel_dist are in meters; start_quat is xyzw.
        direction need not be normalized. cycle_time is the full round-trip
        duration in seconds, and dt is the step duration in seconds.
        """
        self.start_pos = np.asarray(start_pos, dtype=float)
        self.start_quat = np.asarray(start_quat, dtype=float)
        self.direction = np.asarray(direction, dtype=float)
        self.direction /= np.linalg.norm(self.direction)
        self.cycle_time = float(cycle_time)
        self.travel_dist = float(travel_dist)
        self.dt = float(dt)

        self.steps_per_cycle = float(round(self.cycle_time / self.dt))
        self.half_steps = self.steps_per_cycle // 2

        self.step_disp = self.direction * (self.travel_dist / self.half_steps)

        self.pos = self.start_pos.copy()
        self.quat = self.start_quat.copy()

        # Travel direction: 1 forward, -1 backward.
        self.forward = True
        self.step_count = 0

    def __iter__(self):
        return self

    def __next__(self):
        """Advance one step and return (position, quaternion)."""
        self.step_count += 1

        if self.step_count > self.half_steps:
            self.step_count = 1
            self.forward = not self.forward

        if self.forward:
            self.pos += self.step_disp
        else:
            self.pos -= self.step_disp

        return self.pos.copy(), self.quat.copy()

    def reset(self):
        """Reset the trajectory to its starting point."""
        self.pos = self.start_pos.copy()
        self.quat = self.start_quat.copy()
        self.forward = True
        self.step_count = 0


class CircularMotionGenerator:
    def __init__(self, start_pos, center_pos, start_quat, period, dt=1, normal=None):
        """Initialize a circular trajectory from start_pos around center_pos.

        start_quat is xyzw; period and dt are in seconds. normal defines
        the circle's plane and defaults to the Z axis.
        """
        self.center = np.asarray(center_pos, dtype=float)
        self.start_pos = np.asarray(start_pos, dtype=float)
        self.start_quat = np.asarray(start_quat, dtype=float)
        self.period = float(period)
        self.dt = float(dt)

        radius_vec = self.start_pos - self.center
        self.radius = np.linalg.norm(radius_vec)
        if self.radius < 1e-8:
            raise ValueError("start_pos must differ from center_pos")
        self.axis_x = radius_vec / self.radius

        self.omega = 2 * np.pi / self.period

        self.angle_step = self.omega * self.dt

        if normal is None:
            normal = np.array([0, 0, 1.0])
        self.normal = normal / np.linalg.norm(normal)

        self.axis_y = np.cross(self.normal, self.axis_x)
        self.axis_y /= np.linalg.norm(self.axis_y)

        self.angle = 0.0

    def __iter__(self):
        return self

    def __next__(self):
        """Advance by dt and return (position, quaternion)."""
        self.angle += self.angle_step

        pos = (self.center
               + self.radius * np.cos(self.angle) * self.axis_x
               + self.radius * np.sin(self.angle) * self.axis_y)

        return pos.copy(), self.start_quat.copy()

    def reset(self):
        self.angle = 0.0

def direction_to_quaternion(target_dir):
    """Convert a direction vector to a wxyz quaternion using the stored reference orientation."""
    target = np.array(target_dir, dtype=np.float64)
    target_norm = np.linalg.norm(target)

    if target_norm < 1e-6:
        raise ValueError("target_dir must be a nonzero vector")

    target = target / target_norm

    # Preserve the reference quaternion's norm of two for compatibility.
    base_quat = np.array([1.0, 1.0, 1.0, 1.0])
    base_dir = np.array([0.0, 1.0, 0.0])
    ref_dir = np.array([0.0, 0.1])

    axis = np.cross(base_dir, target)
    axis_norm = np.linalg.norm(axis)

    if axis_norm < 1e-6:
        dot = np.dot(base_dir, target)
        if dot > 0:
            return tuple(base_quat)
        else:
            return (-base_quat[0], -base_quat[1], -base_quat[2], -base_quat[3])

    axis = axis / axis_norm

    dot_product = np.dot(base_dir, target)
    angle = np.arccos(np.clip(dot_product, -1.0, 1.0))

    half_angle = angle / 2.0
    delta_quat = np.array([
        np.cos(half_angle),
        axis[0] * np.sin(half_angle),
        axis[1] * np.sin(half_angle),
        axis[2] * np.sin(half_angle)
    ])

    base_unit = base_quat / np.linalg.norm(base_quat)
    composite = quaternion_multiply(delta_quat, base_unit)

    result = composite * 2.0

    return tuple(result)

def quaternion_multiply(q1, q2):
    """Return the quaternion product q1 * q2."""
    w1, x1, y1, z1 = q1
    w2, x2, y2, z2 = q2

    return np.array([
        w1*w2 - x1*x2 - y1*y2 - z1*z2,
        w1*x2 + x1*w2 + y1*z2 - z1*y2,
        w1*y2 - x1*z2 + y1*w2 + z1*x2,
        w1*z2 + x1*y2 - y1*x2 + z1*w2
    ])

class SmoothWaypointMotionGenerator:
    def __init__(self, waypoints, start_quat, segment_time=10, dt=0.01, loop=False):
        """Interpolate position and orientation between (position, direction) waypoints.

        segment_time and dt are in seconds; loop controls repeated traversal.
        """
        if len(waypoints) < 2:
            raise ValueError("waypoints must contain at least two points")

        self.waypoints = waypoints
        self.positions = [list(map(float,wp[0])) for wp in waypoints]
        self.quaternions = [direction_to_quaternion(list(map(float,wp[1]))) for wp in waypoints]

        self.n_segments = len(waypoints) - 1

        self.segment_time = float(segment_time)
        self.dt = float(dt)
        self.steps_per_segment = max(1, int(self.segment_time / self.dt))
        self.loop = bool(loop)

        self.direction=1
        self.seg_idx = 0
        self.step_idx = 0
        self.current_quat = start_quat.copy()

    def __iter__(self):
        return self

    def __next__(self):
        if not self.loop and self.seg_idx == 0 and self.direction == -1 and self.step_idx >= self.steps_per_segment:
            raise StopIteration

        p0 = np.array(self.positions[self.seg_idx])
        p1 = np.array(self.positions[(self.seg_idx + self.direction) % len(self.positions)])

        alpha = self.step_idx / self.steps_per_segment

        current_pos = p0 + alpha * (p1 - p0)

        q0 = self.quaternions[self.seg_idx]
        q1 = self.quaternions[(self.seg_idx + self.direction) % len(self.quaternions)]
        norm0 = np.linalg.norm(q0)
        norm1 = np.linalg.norm(q1)
        q0 = q0 / norm0 if norm0 != 0 else [1.0, 0.0, 0.0, 0.0]
        q1 = q1 / norm1 if norm1 != 0 else [1.0, 0.0, 0.0, 0.0]

        dot_product = q0[0]*q1[0] + q0[1]*q1[1] + q0[2]*q1[2] + q0[3]*q1[3]

        # Negate the endpoint when needed to interpolate along the shorter quaternion arc.
        if dot_product < 0.0:
            q1 = [-x for x in q1]
            dot_product = -dot_product

        # Use normalized linear interpolation for nearly identical orientations.
        if dot_product > 0.9995:
            interpolated = [
                q0[0] + alpha * (q1[0] - q0[0]),
                q0[1] + alpha * (q1[1] - q0[1]),
                q0[2] + alpha * (q1[2] - q0[2]),
                q0[3] + alpha * (q1[3] - q0[3])
            ]
            norm = np.linalg.norm(interpolated)
            self.current_quat = interpolated / norm if norm != 0 else [1.0, 0.0, 0.0, 0.0]
        else:
            theta_0 = np.arccos(dot_product)
            theta = theta_0 * alpha
            sin_theta = np.sin(theta)
            sin_theta_0 = np.sin(theta_0)

            s0 = np.cos(theta) - dot_product * sin_theta / sin_theta_0
            s1 = sin_theta / sin_theta_0

            self.current_quat = [
                s0 * q0[0] + s1 * q1[0],
                s0 * q0[1] + s1 * q1[1],
                s0 * q0[2] + s1 * q1[2],
                s0 * q0[3] + s1 * q1[3]
            ]

        self.step_idx += 1

        if self.step_idx >= self.steps_per_segment:
            self.step_idx = 0
            self.seg_idx += self.direction

            # Reverse direction at the endpoints for back-and-forth traversal.
            if self.seg_idx >= self.n_segments:
                self.direction = -1
                self.seg_idx = self.n_segments
            elif self.seg_idx <= 0:
                if self.loop:
                    self.direction = 1
                    self.seg_idx = 0
                else:
                    self.seg_idx = 0

        return current_pos.tolist(), self.current_quat.copy()

    def reset(self):
        """Reset the trajectory to its starting point."""
        self.seg_idx = 0
        self.step_idx = 0

class ParabolicMotionGenerator:
    def __init__(self, start_pos, start_quat, initial_speed, direction, dt=0.01, gravity=None):
        """Initialize a ballistic trajectory with position in meters and an xyzw quaternion.

        initial_speed is in m/s, dt in seconds, and gravity in m/s^2.
        direction need not be normalized and should not align with gravity.
        """
        self.start_pos = np.array(start_pos, dtype=float)
        self.start_quat = np.array(start_quat, dtype=float)
        dir_vec = np.array(direction, dtype=float)
        norm = np.linalg.norm(dir_vec)
        if norm < 1e-8:
            raise ValueError("direction must be a nonzero vector")
        self.initial_velocity = dir_vec / norm * float(initial_speed)
        if gravity is None:
            gravity = np.array([0, 0, -9.81], dtype=float)
        else:
            gravity = np.array(gravity, dtype=float)
        self.gravity = gravity
        self.dt = float(dt)

        self.pos = self.start_pos.copy()
        self.quat = self.start_quat.copy()
        self.t = 0.0

    def __iter__(self):
        return self

    def __next__(self):
        # pos(t) = p0 + v0 * t + 0.5 * g * t^2
        self.t += self.dt
        self.pos = self.start_pos + self.initial_velocity * self.t + 0.5 * self.gravity * self.t ** 2
        return self.pos.copy(), self.quat.copy()

    def reset(self):
        """Reset position, orientation, and time to their initial values."""
        self.pos = self.start_pos.copy()
        self.quat = self.start_quat.copy()
        self.t = 0.0


def make_xml_processor(body_names):
    """Return an XML processor that adds missing mocap bodies and welds for body_names."""
    def xml_processor(xml_string):
        root = ET.fromstring(xml_string)

        worldbody = root.find("worldbody")
        equality = root.find("equality")
        if equality is None:
            equality = ET.SubElement(root, "equality")

        for name in body_names:
            full_body_name = f"{name}_main"
            mocap_body_name = f"{full_body_name}_mocap"

            # Keep repeated XML processing idempotent.
            existing_mocap = worldbody.find(f".//body[@name='{mocap_body_name}']")
            if existing_mocap is None:
                mocap_body = ET.Element("body", {
                    "mocap": "true",
                    "name": mocap_body_name,
                    "pos": "0 0 0"
                })
                worldbody.append(mocap_body)
                weld = ET.Element("weld", {
                    "body1": full_body_name,
                    "body2": mocap_body_name,
                    "solimp": "0.9 0.95 0.001",
                    "solref": "0.02 1"
                })
                equality.append(weld)
            else:
                continue

        return ET.tostring(root, encoding="unicode")

    return xml_processor

def extract_trailing_int(s):
    """Return the trailing integer in a string, or None if absent."""
    match = re.search(r'(\d+)$', s)
    return int(match.group(1)) if match else None