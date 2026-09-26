import numpy as np
import os
import robosuite.utils.transform_utils as T
import time
from copy import deepcopy
from robosuite.environments.manipulation.manipulation_env import ManipulationEnv
from robosuite.utils.transform_utils import mat2quat
from robosuite.models.tasks import ManipulationTask
from robosuite.utils.placement_samplers import SequentialCompositeSampler
from robosuite.utils.observables import Observable, sensor
from robosuite.utils.mjcf_utils import CustomMaterial
from robosuite.models.base import MujocoModel
import robosuite.macros as macros
from robosuite.controllers import controller_factory, load_part_controller_config, composite_controller_factory
from robosuite.models.grippers import gripper_factory
from robosuite.robots.robot import Robot
from robosuite.utils.buffers import DeltaBuffer, RingBuffer

import mujoco

import libero.libero.envs.bddl_utils as BDDLUtils
from libero.libero.envs.robots import *
from libero.libero.envs.utils import *
from libero.libero.envs.object_states import *
from libero.libero.envs.objects import *
from libero.libero.envs.regions import *
from libero.libero.envs.arenas import *
from libero.libero.envs.predicates import *
from libero.libero.envs.predicates.grasping import GraspStrategyManager

DIR_PATH = os.path.dirname(os.path.realpath(__file__))

TASK_MAPPING = {}

DEFAULT_THRESHOLD = -1

def register_problem(target_class):
    """We design the mapping to be case-INsensitive."""
    TASK_MAPPING[target_class.__name__.lower()] = target_class

class SingleArmEnv(ManipulationEnv):
    """
    A manipulation environment intended for a single robot arm.
    """

    def _load_model(self):
        """
        Verifies correct robot model is loaded
        """
        super()._load_model()

        # # Verify the correct robot has been loaded
        # assert isinstance(
        #     self.robots[0], SingleArm
        # ), "Error: Expected one single-armed robot! Got {} type instead.".format(type(self.robots[0]))

    def _check_robot_configuration(self, robots):
        """
        Sanity check to make sure the inputted robots and configuration is acceptable

        Args:
            robots (str or list of str): Robots to instantiate within this env
        """
        super()._check_robot_configuration(robots)
        if type(robots) is list:
            assert len(robots) == 1, "Error: Only one robot should be inputted for this task!"

    @property
    def _eef_xpos(self):
        """
        Grabs End Effector position

        Returns:
            np.array: End effector(x,y,z)
        """
        return np.array(self.sim.data.site_xpos[self.robots[0].eef_site_id])

    @property
    def _eef_xmat(self):
        """
        End Effector orientation as a rotation matrix
        Note that this draws the orientation from the "ee" site, NOT the gripper site, since the gripper
        orientations are inconsistent!

        Returns:
            np.array: (3,3) End Effector orientation matrix
        """
        pf = self.robots[0].gripper.naming_prefix

        if self.env_configuration == "bimanual":
            return np.array(self.sim.data.site_xmat[self.sim.model.site_name2id(pf + "right_grip_site")]).reshape(3, 3)
        else:
            return np.array(self.sim.data.site_xmat[self.sim.model.site_name2id(pf + "grip_site")]).reshape(3, 3)

    @property
    def _eef_xquat(self):
        """
        End Effector orientation as a (x,y,z,w) quaternion
        Note that this draws the orientation from the "ee" site, NOT the gripper site, since the gripper
        orientations are inconsistent!

        Returns:
            np.array: (x,y,z,w) End Effector quaternion
        """
        return mat2quat(self._eef_xmat)


class BDDLBaseDomain(SingleArmEnv):
    """
    A base domain for parsing bddl files.
    """

    def __init__(
        self,
        bddl_file_name,
        robots,
        env_configuration="default",
        controller_configs=None,
        gripper_types="default",
        initialization_noise="default",
        use_latch=False,
        use_camera_obs=True,
        use_object_obs=True,
        reward_scale=1.0,
        reward_shaping=False,
        temporal_cost_shaping=1,
        placement_initializer=None,
        object_property_initializers=None,
        has_renderer=False,
        has_offscreen_renderer=True,
        render_camera="frontview",
        render_collision_mesh=False,
        render_visual_mesh=True,
        render_gpu_device_id=-1,
        control_freq=20,
        horizon=1000,
        ignore_done=False,
        hard_reset=True,
        camera_names="agentview",
        camera_heights=256,
        camera_widths=256,
        camera_depths=False,
        camera_segmentations=None,
        renderer="mujoco",
        table_full_size=(1.0, 1.0, 0.05),
        workspace_offset=(0.0, 0.0, 0.0),
        arena_type="table",
        scene_xml="scenes/libero_base_style.xml",
        scene_properties={},
        grasp_strategy="advanced",  # Grasp detection strategy: "simple", "dual", or "advanced"
        **kwargs,
    ):
        t0 = time.time()
        # settings for table top (hardcoded since it's not an essential part of the environment)
        self.workspace_offset = workspace_offset
        # reward configuration
        self.reward_scale = reward_scale
        self.reward_shaping = reward_shaping
        # temporal cost shaping configuration
        self.temporal_cost_shaping = temporal_cost_shaping

        # Initialize grasp detection strategy manager
        self.grasp_strategy_manager = GraspStrategyManager(default_strategy=grasp_strategy)
        self.step_count = 0  # Track step count for advanced strategies

        # whether to use ground-truth object states
        self.use_object_obs = use_object_obs

        # object placement initializer
        self.placement_initializer = placement_initializer
        self.conditional_placement_initializer = None
        self.conditional_placement_on_objects_initializer = None

        # object property initializer

        if object_property_initializers is not None:
            self.object_property_initializers = object_property_initializers
        else:
            self.object_property_initializers = list()

        # Keep track of movable objects in the tasks
        self.objects_dict = {}
        # Kepp track of fixed objects in the tasks
        self.fixtures_dict = {}
        # Keep track of site objects in the tasks. site objects
        # (instances of SiteObject)
        self.object_sites_dict = {}
        # This is a dictionary that stores all the object states
        # interface for all the objects
        self.object_states_dict = {}
        # This is a dictionary that stores all the object original quat
        self.object_original_quat = {}
        self.object_original_pos = {}
        # For those that require visual feature changes, update the state every time step to avoid missing state changes. We keep track of this type of objects to make predicate checking more efficient.
        self.tracking_object_states_change = []

        # Track contact transitions to detect brief robot-object knocks.
        self.knock_contact_states = {}
        # Track object-pair contacts independently of robot contacts.
        self.knock_binary_contact_states = {}
        self.knock_duration_threshold = 10  # Maximum contact duration, in steps, that qualifies as a knock.

        # Cache object positions and steps to estimate sweeping speed.
        self.sweeping_positions = {}

        self.objects = []
        self.fixtures = []
        # self.custom_material_dict = {}

        self.custom_asset_dir = os.path.abspath(os.path.join(DIR_PATH, "../assets"))

        self.bddl_file_name = bddl_file_name
        self.parsed_problem = BDDLUtils.robosuite_parse_problem(self.bddl_file_name)

        self.obj_of_interest = self.parsed_problem["obj_of_interest"]
        self.moving_objects = self.parsed_problem["moving_objects"]
        self.image_settings = self.parsed_problem["image_settings"]

        self._assert_problem_name()

        self._arena_type = arena_type
        self._arena_xml = os.path.join(self.custom_asset_dir, scene_xml)
        self._arena_properties = scene_properties

        # Cache object poses for displacement-based collision detection.
        self._prev_object_states = {}

        self.collision_thresholds = {
            'position': 0.001,  # Position change threshold in meters.
            'rotation': 0.01    # Rotation change threshold in radians.
        }

        super().__init__(
            robots=robots,
            env_configuration=env_configuration,
            controller_configs=controller_configs,
            gripper_types=gripper_types,
            initialization_noise=initialization_noise,
            use_camera_obs=use_camera_obs,
            has_renderer=has_renderer,
            has_offscreen_renderer=has_offscreen_renderer,
            render_camera=render_camera,
            render_collision_mesh=render_collision_mesh,
            render_visual_mesh=render_visual_mesh,
            render_gpu_device_id=render_gpu_device_id,
            control_freq=control_freq,
            horizon=horizon,
            ignore_done=ignore_done,
            hard_reset=hard_reset,
            camera_names=camera_names,
            camera_heights=camera_heights,
            camera_widths=camera_widths,
            camera_depths=camera_depths,
            camera_segmentations=camera_segmentations,
            renderer=renderer,
            **kwargs,
        )

    def seed(self, seed):
        np.random.seed(seed)

    def reward(self, action=None):
        """
        Reward function for the task.

        Sparse un-normalized reward:

            - a discrete reward of 1.0 is provided if the task succeeds.

        Args:
            action (np.array): [NOT USED]

        Returns:
            float: reward value
        """
        reward = 0.0

        # sparse completion reward
        if self._check_success():
            reward = 1.0

        # Scale reward if requested
        if self.reward_scale is not None:
            reward *= self.reward_scale / 1.0

        return reward

    def _assert_problem_name(self):
        """Implement this to make sure the loaded bddl file has the correct problem name specification."""
        assert (
            self.parsed_problem["problem_name"] == self.__class__.__name__.lower()
        ), "Problem name mismatched"

    def _load_fixtures_in_arena(self, mujoco_arena):
        """
        Load fixtures based on the bddl file description. Please override the method in the custom problem file.
        """
        raise NotImplementedError

    def _load_objects_in_arena(self, mujoco_arena):
        """
        Load movable objects based on the bddl file description
        """
        raise NotImplementedError

    def _load_sites_in_arena(self, mujoco_arena):
        """
        Load sites information from each object to keep track of them for predicate checking
        """
        raise NotImplementedError

    def _generate_object_state_wrapper(
        self, skip_object_names=["main_table", "floor", "countertop", "coffee_table"]
    ):
        object_states_dict = {}
        tracking_object_states_changes = []
        for object_name in self.objects_dict.keys():
            if object_name in skip_object_names:
                continue
            object_states_dict[object_name] = ObjectState(self, object_name)
            if (
                self.objects_dict[object_name].category_name
                in VISUAL_CHANGE_OBJECTS_DICT
            ):
                tracking_object_states_changes.append(object_states_dict[object_name])

        for object_name in self.fixtures_dict.keys():
            if object_name in skip_object_names:
                continue
            object_states_dict[object_name] = ObjectState(
                self, object_name, is_fixture=True
            )
            if (
                self.fixtures_dict[object_name].category_name
                in VISUAL_CHANGE_OBJECTS_DICT
            ):
                tracking_object_states_changes.append(object_states_dict[object_name])

        for object_name in self.object_sites_dict.keys():
            if object_name in skip_object_names:
                continue
            object_states_dict[object_name] = SiteObjectState(
                self,
                object_name,
                parent_name=self.object_sites_dict[object_name].parent_name,
            )
        self.object_states_dict = object_states_dict
        self.tracking_object_states_change = tracking_object_states_changes

    def _load_distracting_objects(self, mujoco_arena):
        raise NotImplementedError

    def _load_custom_material(self):
        """
        Define all the textures
        """
        # self.custom_material_dict = dict()

        # tex_attrib = {
        #     "type": "cube"
        # }

        # self.custom_material_dict["bread"] = CustomMaterial(
        #     texture="Bread",
        #     tex_name="bread",
        #     mat_name="MatBread",
        #     tex_attrib=tex_attrib,
        #     mat_attrib={"texrepeat": "3 3", "specular": "0.4","shininess": "0.1"}
        # )

    def _setup_camera(self, mujoco_arena):
        # Modify default agentview camera
        mujoco_arena.set_camera(
            camera_name="canonical_agentview",
            pos=[0.5386131746834771, 0.0, 1.4903500240372423],
            quat=[
                0.6380177736282349,
                0.3048497438430786,
                0.30484986305236816,
                0.6380177736282349,
            ],
        )
        mujoco_arena.set_camera(
            camera_name="agentview",
            pos=[0.5886131746834771, 0.0, 1.4903500240372423],
            quat=[
                0.6380177736282349,
                0.3048497438430786,
                0.30484986305236816,
                0.6380177736282349,
            ],
        )

    def _load_model(self):
        """
        Loads an xml model, puts it in self.model
        """
        super()._load_model()
        # Adjust base pose accordingly

        if self._arena_type == "table":
            xpos = self.robots[0].robot_model.base_xpos_offset["table"](
                self.table_full_size[0]
            )
            self.robots[0].robot_model.set_base_xpos(xpos)
            mujoco_arena = TableArena(
                table_full_size=self.table_full_size,
                table_offset=self.workspace_offset,
                table_friction=(0.6, 0.005, 0.0001),
                xml=self._arena_xml,
                **self._arena_properties,
            )
        elif self._arena_type == "kitchen":
            xpos = self.robots[0].robot_model.base_xpos_offset["kitchen_table"](
                self.kitchen_table_full_size[0]
            )
            self.robots[0].robot_model.set_base_xpos(xpos)
            mujoco_arena = KitchenTableArena(
                table_full_size=self.kitchen_table_full_size,
                table_offset=self.workspace_offset,
                xml=self._arena_xml,
                **self._arena_properties,
            )

        elif self._arena_type == "floor":
            xpos = self.robots[0].robot_model.base_xpos_offset["empty"]
            self.robots[0].robot_model.set_base_xpos(xpos)

            mujoco_arena = EmptyArena(
                xml=self._arena_xml,
                **self._arena_properties,
            )
        elif self._arena_type == "coffee_table":
            xpos = self.robots[0].robot_model.base_xpos_offset["coffee_table"](
                self.coffee_table_full_size[0]
            )
            self.robots[0].robot_model.set_base_xpos(xpos)
            mujoco_arena = CoffeeTableArena(
                xml=self._arena_xml,
                **self._arena_properties,
            )

        elif self._arena_type == "living_room":
            xpos = self.robots[0].robot_model.base_xpos_offset["living_room_table"](
                self.living_room_table_full_size[0]
            )
            self.robots[0].robot_model.set_base_xpos(xpos)
            mujoco_arena = LivingRoomTableArena(
                xml=self._arena_xml,
                **self._arena_properties,
            )

        elif self._arena_type == "study":
            xpos = self.robots[0].robot_model.base_xpos_offset["study_table"](
                self.study_table_full_size[0]
            )
            self.robots[0].robot_model.set_base_xpos(xpos)
            mujoco_arena = StudyTableArena(
                xml=self._arena_xml,
                **self._arena_properties,
            )

        # Arena always gets set to zero origin
        mujoco_arena.set_origin([0, 0, 0])

        self._setup_camera(mujoco_arena)

        self._load_custom_material()

        self._load_fixtures_in_arena(mujoco_arena)

        self._load_objects_in_arena(mujoco_arena)

        self._load_sites_in_arena(mujoco_arena)

        self._generate_object_state_wrapper()

        self._setup_placement_initializer(mujoco_arena)

        moving_objects_names = [object['name'] for object in self.moving_objects]
        xml_processor = make_xml_processor(moving_objects_names)
        self.set_xml_processor(xml_processor)

        self.objects = list(self.objects_dict.values())
        self.fixtures = list(self.fixtures_dict.values())

        # task includes arena, robot, and objects of interest
        self.model = ManipulationTask(
            mujoco_arena=mujoco_arena,
            mujoco_robots=[robot.robot_model for robot in self.robots],
            mujoco_objects=self.objects + self.fixtures,
        )

        for fixture in self.fixtures:
            self.model.merge_assets(fixture)

    def _setup_placement_initializer(self, mujoco_arena):
        self.placement_initializer = SequentialCompositeSampler(name="ObjectSampler")
        self.conditional_placement_initializer = SiteSequentialCompositeSampler(
            name="ConditionalSiteSampler"
        )
        self.conditional_placement_on_objects_initializer = SequentialCompositeSampler(
            name="ConditionalObjectSampler"
        )
        self._add_placement_initializer()

    def _setup_references(self):
        """
        Sets up references to important components. A reference is typically an
        index or a list of indices that point to the corresponding elements
        in a flatten array, which is how MuJoCo stores physical simulation data.
        """
        super()._setup_references()

        # Additional object references from this env
        self.obj_body_id = dict()

        for (object_name, object_body) in self.objects_dict.items():
            self.obj_body_id[object_name] = self.sim.model.body_name2id(
                object_body.root_body
            )

        for (fixture_name, fixture_body) in self.fixtures_dict.items():
            self.obj_body_id[fixture_name] = self.sim.model.body_name2id(
                fixture_body.root_body
            )

    def _setup_observables(self):
        """
        Sets up observables to be used for this environment. Creates object-based observables if enabled

        Returns:
            OrderedDict: Dictionary mapping observable names to its corresponding Observable object
        """
        observables = super()._setup_observables()

        observables["robot0_joint_pos"]._active = True

        # low-level object information
        if self.use_object_obs:
            # Get robot prefix and define observables modality
            pf = self.robots[0].robot_model.naming_prefix
            sensors = []
            names = [s.__name__ for s in sensors]

            # Also append handle qpos if we're using a locked drawer version with rotatable handle

            # Create observables
            for name, s in zip(names, sensors):
                observables[name] = Observable(
                    name=name,
                    sensor=s,
                    sampling_rate=self.control_freq,
                )

        pf = self.robots[0].robot_model.naming_prefix

        @sensor(modality="object")
        def world_pose_in_gripper(obs_cache):
            return (
                T.pose_inv(
                    T.pose2mat((obs_cache[f"{pf}eef_pos"], obs_cache[f"{pf}eef_quat"]))
                )
                if f"{pf}eef_pos" in obs_cache and f"{pf}eef_quat" in obs_cache
                else np.eye(4)
            )

        sensors.append(world_pose_in_gripper)
        names.append("world_pose_in_gripper")

        for (i, obj) in enumerate(self.objects):
            obj_sensors, obj_sensor_names = self._create_obj_sensors(
                obj_name=obj.name, modality="object"
            )

            sensors += obj_sensors
            names += obj_sensor_names

        for name, s in zip(names, sensors):
            if name == "world_pose_in_gripper":
                observables[name] = Observable(
                    name=name,
                    sensor=s,
                    sampling_rate=self.control_freq,
                    enabled=True,
                    active=False,
                )
            else:
                observables[name] = Observable(
                    name=name, sensor=s, sampling_rate=self.control_freq
                )

        return observables

    def _create_obj_sensors(self, obj_name, modality="object"):
        """
        Helper function to create sensors for a given object. This is abstracted in a separate function call so that we
        don't have local function naming collisions during the _setup_observables() call.

        Args:
            obj_name (str): Name of object to create sensors for
            modality (str): Modality to assign to all sensors

        Returns:
            2-tuple:
                sensors (list): Array of sensors for the given obj
                names (list): array of corresponding observable names
        """
        pf = self.robots[0].robot_model.naming_prefix

        @sensor(modality=modality)
        def obj_pos(obs_cache):
            return np.array(self.sim.data.body_xpos[self.obj_body_id[obj_name]])

        @sensor(modality=modality)
        def obj_quat(obs_cache):
            return T.convert_quat(
                self.sim.data.body_xquat[self.obj_body_id[obj_name]], to="xyzw"
            )

        @sensor(modality=modality)
        def obj_to_eef_pos(obs_cache):
            # Immediately return default value if cache is empty
            if any(
                [
                    name not in obs_cache
                    for name in [
                        f"{obj_name}_pos",
                        f"{obj_name}_quat",
                        "world_pose_in_gripper",
                    ]
                ]
            ):
                return np.zeros(3)
            obj_pose = T.pose2mat(
                (obs_cache[f"{obj_name}_pos"], obs_cache[f"{obj_name}_quat"])
            )
            rel_pose = T.pose_in_A_to_pose_in_B(
                obj_pose, obs_cache["world_pose_in_gripper"]
            )
            rel_pos, rel_quat = T.mat2pose(rel_pose)
            obs_cache[f"{obj_name}_to_{pf}eef_quat"] = rel_quat
            return rel_pos

        @sensor(modality=modality)
        def obj_to_eef_quat(obs_cache):
            return (
                obs_cache[f"{obj_name}_to_{pf}eef_quat"]
                if f"{obj_name}_to_{pf}eef_quat" in obs_cache
                else np.zeros(4)
            )

        sensors = [obj_pos, obj_quat, obj_to_eef_pos, obj_to_eef_quat]
        names = [
            f"{obj_name}_pos",
            f"{obj_name}_quat",
            f"{obj_name}_to_{pf}eef_pos",
            f"{obj_name}_to_{pf}eef_quat",
        ]

        return sensors, names

    def _add_placement_initializer(self):

        mapping_inv = {}
        for k, values in self.parsed_problem["fixtures"].items():
            for v in values:
                mapping_inv[v] = k
        for k, values in self.parsed_problem["objects"].items():
            for v in values:
                mapping_inv[v] = k

        regions = self.parsed_problem["regions"]
        initial_state = self.parsed_problem["initial_state"]
        problem_name = self.parsed_problem["problem_name"]

        conditioned_initial_place_state_on_sites = []
        conditioned_initial_place_state_on_objects = []
        conditioned_initial_place_state_in_objects = []

        for state in initial_state:
            if state[0] == "on" and state[2] in self.objects_dict:
                conditioned_initial_place_state_on_objects.append(state)
                continue

            # (Yifeng) Given that an object needs to have a certain "containing" region in order to hold the relation "In", we assume that users need to specify the containing region of the object already.
            if state[0] == "in" and state[2] in regions:
                conditioned_initial_place_state_in_objects.append(state)
                continue
            # Check if the predicate is in the form of On(object, region)
            if state[0] == "on" and state[2] in regions:
                object_name = state[1]
                region_name = state[2]
                target_name = regions[region_name]["target"]
                x_ranges, y_ranges = rectangle2xyrange(regions[region_name]["ranges"])
                yaw_rotation = regions[region_name]["yaw_rotation"]
                if (
                    target_name in self.objects_dict
                    or target_name in self.fixtures_dict
                ):
                    conditioned_initial_place_state_on_sites.append(state)
                    continue
                if self.is_fixture(object_name):
                    # This is to place environment fixtures.
                    fixture_sampler = MultiRegionRandomSampler(
                        f"{object_name}_sampler",
                        mujoco_objects=self.fixtures_dict[object_name],
                        x_ranges=x_ranges,
                        y_ranges=y_ranges,
                        rotation=yaw_rotation,
                        rotation_axis="z",
                        z_offset=self.z_offset,  # -self.table_full_size[2],
                        ensure_object_boundary_in_range=False,
                        ensure_valid_placement=False,
                        reference_pos=self.workspace_offset,
                    )
                    self.placement_initializer.append_sampler(fixture_sampler)
                else:
                    # This is to place movable objects.
                    region_sampler = get_region_samplers(
                        problem_name, mapping_inv[target_name]
                    )(
                        object_name,
                        self.objects_dict[object_name],
                        x_ranges=x_ranges,
                        y_ranges=y_ranges,
                        rotation=self.objects_dict[object_name].rotation,
                        rotation_axis=self.objects_dict[object_name].rotation_axis,
                        reference_pos=self.workspace_offset,
                    )
                    self.placement_initializer.append_sampler(region_sampler)
            if state[0] in ["open", "close"]:
                # If "open" is implemented, we assume "close" is also implemented
                if state[1] in self.object_states_dict and hasattr(
                    self.object_states_dict[state[1]], "set_joint"
                ):
                    obj = self.get_object(state[1])
                    if state[0] == "open":
                        joint_ranges = obj.object_properties["articulation"][
                            "default_open_ranges"
                        ]
                    else:
                        joint_ranges = obj.object_properties["articulation"][
                            "default_close_ranges"
                        ]

                    property_initializer = OpenCloseSampler(
                        name=obj.name,
                        state_type=state[0],
                        joint_ranges=joint_ranges,
                    )
                    self.object_property_initializers.append(property_initializer)
            elif state[0] in ["turnon", "turnoff"]:
                # If "turnon" is implemented, we assume "turnoff" is also implemented.
                if state[1] in self.object_states_dict and hasattr(
                    self.object_states_dict[state[1]], "set_joint"
                ):
                    obj = self.get_object(state[1])
                    if state[0] == "turnon":
                        joint_ranges = obj.object_properties["articulation"][
                            "default_turnon_ranges"
                        ]
                    else:
                        joint_ranges = obj.object_properties["articulation"][
                            "default_turnoff_ranges"
                        ]

                    property_initializer = TurnOnOffSampler(
                        name=obj.name,
                        state_type=state[0],
                        joint_ranges=joint_ranges,
                    )
                    self.object_property_initializers.append(property_initializer)

        # Place objects that are on sites
        for state in conditioned_initial_place_state_on_sites:
            object_name = state[1]
            region_name = state[2]
            target_name = regions[region_name]["target"]
            site_xy_size = self.object_sites_dict[region_name].size[:2]
            sampler = SiteRegionRandomSampler(
                f"{object_name}_sampler",
                mujoco_objects=self.objects_dict[object_name],
                x_ranges=[[-site_xy_size[0] / 2, site_xy_size[0] / 2]],
                y_ranges=[[-site_xy_size[1] / 2, site_xy_size[1] / 2]],
                ensure_object_boundary_in_range=True,
                ensure_valid_placement=True,
                rotation=self.objects_dict[object_name].rotation,
                rotation_axis=self.objects_dict[object_name].rotation_axis,
            )
            self.conditional_placement_initializer.append_sampler(
                sampler, {"reference": target_name, "site_name": region_name}
            )
        # Place objects that are on other objects
        for state in conditioned_initial_place_state_on_objects:
            object_name = state[1]
            other_object_name = state[2]
            sampler = ObjectBasedSampler(
                f"{object_name}_sampler",
                mujoco_objects=self.objects_dict[object_name],
                x_ranges=[[0.0, 0.0]],
                y_ranges=[[0.0, 0.0]],
                ensure_object_boundary_in_range=False,
                ensure_valid_placement=False,
                rotation=self.objects_dict[object_name].rotation,
                rotation_axis=self.objects_dict[object_name].rotation_axis,
            )
            self.conditional_placement_on_objects_initializer.append_sampler(
                sampler, {"reference": other_object_name}
            )
        # Place objects inside some containing regions
        for state in conditioned_initial_place_state_in_objects:
            object_name = state[1]
            region_name = state[2]
            target_name = regions[region_name]["target"]

            site_xy_size = self.object_sites_dict[region_name].size[:2]
            sampler = InSiteRegionRandomSampler(
                f"{object_name}_sampler",
                mujoco_objects=self.objects_dict[object_name],
                # x_ranges=[[-site_xy_size[0] / 2, site_xy_size[0] / 2]],
                # y_ranges=[[-site_xy_size[1] / 2, site_xy_size[1] / 2]],
                ensure_object_boundary_in_range=True,
                ensure_valid_placement=True,
                rotation=self.objects_dict[object_name].rotation,
                rotation_axis=self.objects_dict[object_name].rotation_axis,
            )
            self.conditional_placement_initializer.append_sampler(
                sampler, {"reference": target_name, "site_name": region_name}
            )

    def _get_observations(self, force_update=False):
        """
        Grabs observations from the environment.
        Args:
            force_update (bool): If True, will force all the observables to update their internal values to the newest
                value. This is useful if, e.g., you want to grab observations when directly setting simulation states
                without actually stepping the simulation.
        Returns:
            OrderedDict: OrderedDict containing observations [(name_string, np.array), ...]
        """
        from collections import OrderedDict
        observations = OrderedDict()
        obs_by_modality = OrderedDict()

        # Force an update if requested
        if force_update:
            self._update_observables(force=True)

        # Loop through all observables and grab their current observation
        for obs_name, observable in self._observables.items():
            if observable.is_enabled() and observable.is_active():
                obs = observable.obs
                if obs_name=="agentview_image" or obs_name=="robot0_eye_in_hand_image":
                    if self.image_settings:
                        obs=ajust_image(obs,**self.image_settings)
                observations[obs_name] = obs
                modality = observable.modality + "-state"
                if modality not in obs_by_modality:
                    obs_by_modality[modality] = []
                # Make sure all observations are numpy arrays so we can concatenate them
                array_obs = [obs] if type(obs) in {int, float} or not obs.shape else obs
                obs_by_modality[modality].append(np.array(array_obs))

        # Add in modality observations
        for modality, obs in obs_by_modality.items():
            # To save memory, we only concatenate the image observations if explicitly requested
            if modality == "image-state" and not macros.CONCATENATE_IMAGES:
                continue
            observations[modality] = np.concatenate(obs, axis=-1)

        return observations

    def _reset_internal(self):
        """
        Resets simulation internal configurations.
        """
        super()._reset_internal()

        # Reset grasp detection strategy history
        self.step_count = 0
        self.grasp_strategy_manager.reset_history()

        self.knock_contact_states.clear()
        self.sweeping_positions.clear()
        if hasattr(self, '_arm_stuck_history'):
            self._arm_stuck_history = {
                'last_qpos': None,
                'stuck_counter': 0,
                'last_step': -1
            }

        # Reset all object positions using initializer sampler if we're not directly loading from an xml
        if not self.deterministic_reset:

            # Sample from the placement initializer for all objects
            for object_property_initializer in self.object_property_initializers:
                if isinstance(object_property_initializer, OpenCloseSampler):
                    joint_pos = object_property_initializer.sample()
                    self.object_states_dict[object_property_initializer.name].set_joint(
                        joint_pos
                    )
                elif isinstance(object_property_initializer, TurnOnOffSampler):
                    joint_pos = object_property_initializer.sample()
                    self.object_states_dict[object_property_initializer.name].set_joint(
                        joint_pos
                    )
                else:
                    print("Warning!!! This sampler doesn't seem to be used")
            # robosuite didn't provide api for this stepping. we manually do this stepping to increase the speed of resetting simulation.
            mujoco.mj_step1(self.sim.model._model, self.sim.data._data)

            object_placements = self.placement_initializer.sample()
            object_placements = self.conditional_placement_initializer.sample(
                self.sim, object_placements
            )
            object_placements = (
                self.conditional_placement_on_objects_initializer.sample(
                    object_placements
                )
            )
            for obj_pos, obj_quat, obj in object_placements.values():
                if obj.name not in list(self.fixtures_dict.keys()):
                    # This is for movable object resetting
                    if hasattr(obj, 'joints') and obj.joints and len(obj.joints) > 0:
                        self.sim.data.set_joint_qpos(
                            obj.joints[-1],
                            np.concatenate([np.array(obj_pos), np.array(obj_quat)]),
                        )
                    else:
                        # Objects without joints, such as target zones, need no joint initialization.
                        pass
                    self.object_original_quat[obj.name] = obj_quat
                    self.object_original_pos[obj.name] = obj_pos
                else:
                    # This is for fixture resetting
                    body_id = self.sim.model.body_name2id(obj.root_body)
                    self.sim.model.body_pos[body_id] = obj_pos
                    self.sim.model.body_quat[body_id] = obj_quat
        self.moving_objects = self.parsed_problem["moving_objects"]
        mocap_joint_names = []
        mocap_motion_generators = {}
        for object in self.moving_objects:
            mocap_joint_names.append(f"{object['name']}_main_mocap")
            pos = self.object_original_pos[object['name']]
            quat = self.object_original_quat[object['name']]
            self.sim.data.set_mocap_pos(mocap_joint_names[-1], pos)
            self.sim.data.set_mocap_quat(mocap_joint_names[-1], quat)
            mocap_motion_generator = self._set_mocap_motion_generator(object)
            mocap_motion_generators[object['name']] = mocap_motion_generator

        self.mocap_joint_names = mocap_joint_names
        self.mocap_motion_generators = mocap_motion_generators


    def _set_mocap_motion(self):
        for object_name, mocap_motion_generator in self.mocap_motion_generators.items():
            pos, quat = next(mocap_motion_generator)
            self.sim.data.set_mocap_pos(object_name + "_main_mocap", pos)
            self.sim.data.set_mocap_quat(object_name + "_main_mocap", quat)

    def _set_mocap_motion_generator(self, object):
        if object['motion_type'] == "circle":
            start_pos = self.object_original_pos[object['name']]
            start_quat = self.object_original_quat[object['name']]
            return CircularMotionGenerator(
                start_pos=start_pos,
                center_pos=object.get('motion_center', [0, 0, 1.2]),
                start_quat=start_quat,
                period=object.get('motion_period', 1)
            )
        elif object['motion_type'] == "linear":
            start_pos = self.object_original_pos[object['name']]
            start_quat = self.object_original_quat[object['name']]
            return LinearMotionGenerator(
                start_pos=start_pos,
                start_quat=start_quat,
                direction=object.get('motion_direction', [0, 1, 0]),
                cycle_time=object.get('motion_period', 1),
                travel_dist=object.get('motion_travel_dist', 1),
            )
        elif object['motion_type'] == "waypoint":
            return SmoothWaypointMotionGenerator(
                waypoints=object.get('motion_waypoints', [[0, 0, 1.2]]),
                start_quat=self.object_original_quat[object['name']],
                dt=object.get('motion_dt', 0.01),
                loop=object.get('motion_loop', True)
            )
        elif object['motion_type'] == "parabolic":
            return ParabolicMotionGenerator(
                start_pos=object.get('motion_start_pos', [0, 0, 1.2]),
                start_quat=object.get('motion_start_quat', [0, 0, 0, 1]),
                initial_speed=object.get('motion_initial_speed', 1),
                direction=object.get('motion_direction', [0, 1, 0]),
                dt=object.get('motion_dt', 0.01),
                gravity=object.get('motion_gravity', np.array([0, 0, -9.81]))
            )
        else:
            raise NotImplementedError(f"Invalid motion type: {object['motion_type']}")

    def _weld_mocap_joint(self, object_name, mocap_joint_name):
        self.sim.model.eq_active[self.sim.model.eq_obj1id[mocap_joint_name]] = 1
        self.sim.model.eq_obj1id[mocap_joint_name] = self.sim.model.body_name2id(object_name)
        self.sim.model.eq_obj2id[mocap_joint_name] = self.sim.model.body_name2id(object_name)

    def _check_success(self):
        """
        Check if the goal is achieved. Consider conjunction goals at the moment
        """
        goal_state = self.parsed_problem["goal_state"]
        result = True
        for state in goal_state:
            result = self._eval_predicate(state) and result
        return result


    def _eval_begin_with_conj(self, state_list:list,conj):
        assert conj in ("and","or")
        cost = 0
        cost_detail = []
        for state in state_list:
            if state[0] in ("and","or"):
                cost_tmp, cost_detail_tmp = self._eval_begin_with_conj(state[1:],state[0])
                if cost_tmp!=0:
                    cost += 1
                    cost_detail.extend(cost_detail_tmp)
            else : # begin with verb
                cost_tmp, cost_detail_tmp = self._eval_begin_with_verb(state)
                if cost_tmp!=0:
                    cost+=1
                    cost_detail.append(cost_detail_tmp) # without unpacking

        if conj == "and":
            return (cost, [['&'.join(t[0] for t in cost_detail),cost]]) if all(t[1] for t in cost_detail) else (0, []) # ensure cost_detail.dim == 2  for unpack
        return cost,cost_detail


    def _eval_begin_with_verb(self,state):
        predicate_cost = int(self._eval_predicate(state))
        cost = predicate_cost
        state_str = ""
        for state_item in state:
            state_str += state_item + " "
        if cost <= 0:
            return 0,[]
        return cost, [state_str[:-1], cost]

    def _check_cost(self, done):


        cost_state = self.parsed_problem["cost_state"]

        if len(cost_state) == 0 or len(cost_state[0]) == 0:
            return 0,[]
        # print(f"check_cost{cost_state}\n")
        # print(f"type is :{type(cost_state)}")
        if cost_state[0][0].lower() == 'or':
            cost_state=cost_state[0]
        else:
            cost_state = ['and']+cost_state
        cost,detail = self._eval_begin_with_conj(cost_state[1:],cost_state[0])

        # print(f'\n[DEBUG] \nCOST:{cost} \nDETAIL:{detail}\n')
        return cost,detail

    def visualize(self, vis_settings):
        """
        In addition to super call, visualize gripper site proportional to the distance to the drawer handle.

        Args:
            vis_settings (dict): Visualization keywords mapped to T/F, determining whether that specific
                component should be visualized. Should have "grippers" keyword as well as any other relevant
                options specified.
        """
        # Run superclass method first
        super().visualize(vis_settings=vis_settings)

    def step(self, action):
        if self.action_dim == 4 and len(action) > 4:
            # Convert OSC_POSITION action
            action = np.array(action)
            action = np.concatenate((action[:3], action[-1:]), axis=-1)
        self._set_mocap_motion()
        obs, reward, done, info = super().step(action)
        done = self._check_success()
        cost, cost_detail = self._check_cost(done)
        info["cost"] = cost
        info["cost_detail"] = cost_detail

        # Update step count for grasp detection strategies
        self.step_count += 1

        return obs, reward, done, info

    def _pre_action(self, action, policy_step=False):
        super()._pre_action(action, policy_step=policy_step)

    def _post_action(self, action):
        reward, done, info = super()._post_action(action)

        self._post_process()

        return reward, done, info

    def _post_process(self):
        # Update some object states, such as light switching etc.
        for object_state in self.tracking_object_states_change:
            object_state.update_state()

    def get_robot_state_vector(self, obs):
        return np.concatenate(
            [obs["robot0_gripper_qpos"], obs["robot0_eef_pos"], obs["robot0_eef_quat"]]
        )

    def is_fixture(self, object_name):
        """
        Check if an object is defined as a fixture in the task

        Args:
            object_name (str): The name string of the object in query
        """
        return object_name in list(self.fixtures_dict.keys())

    @property
    def language_instruction(self):
        return self.parsed_problem["language"]

    def get_object(self, object_name):
        for query_dict in [
            self.fixtures_dict,
            self.objects_dict,
            self.object_sites_dict,
        ]:
            if object_name in query_dict:
                return query_dict[object_name]

    def check_force(self, geoms_1, geoms_2=None, threshold=100.0):
        """Return whether total matching contact force exceeds threshold in newtons.

        Geometry groups accept names, lists, or MujocoModel objects.
        geoms_2=None matches any contacting geometry.
        """
        if type(geoms_1) is str:
            geoms_1 = [geoms_1]
        elif isinstance(geoms_1, MujocoModel):
            geoms_1 = geoms_1.contact_geoms
        if type(geoms_2) is str:
            geoms_2 = [geoms_2]
        elif isinstance(geoms_2, MujocoModel):
            geoms_2 = geoms_2.contact_geoms

        normal_force = 0
        for i in range(self.sim.data.ncon):
            contact = self.sim.data.contact[i]
            # check contact geom in geoms
            c1_in_g1 = self.sim.model.geom_id2name(contact.geom1) in geoms_1
            c2_in_g2 = self.sim.model.geom_id2name(contact.geom2) in geoms_2 if geoms_2 is not None else True
            # check contact geom in geoms (flipped)
            c2_in_g1 = self.sim.model.geom_id2name(contact.geom2) in geoms_1
            c1_in_g2 = self.sim.model.geom_id2name(contact.geom1) in geoms_2 if geoms_2 is not None else True

            if (c1_in_g1 and c2_in_g2) or (c1_in_g2 and c2_in_g1):
                # Accumulate all matching contacts before comparing against the threshold.
                f6 = np.zeros(6)
                mujoco.mj_contactForce(self.sim.model._model, self.sim.data._data, i, f6)
                normal_force += abs(f6[0])  # Use force magnitudes so opposing contact directions do not cancel.

        # print(f"normal_force: {normal_force}, threshold: {threshold}")
        return normal_force > threshold

    def check_distance(self, geoms_1, geoms_2=None):
        if type(geoms_1) is str:
            geoms_1 = [geoms_1]
        elif isinstance(geoms_1, MujocoModel):
            geoms_1 = geoms_1.contact_geoms
        if type(geoms_2) is str:
            geoms_2 = [geoms_2]
        elif isinstance(geoms_2, MujocoModel):
            geoms_2 = geoms_2.contact_geoms

        min_dist = float('inf')

        for g1_name in geoms_1:
            for g2_name in geoms_2:
                if g1_name == g2_name:
                    continue

                try:
                    g1_id = self.sim.model.geom_name2id(g1_name)
                    g2_id = self.sim.model.geom_name2id(g2_name)
                except ValueError:
                    print(f"Warning: could not find geometry '{g1_name}' or '{g2_name}'")
                    continue

                # Use a large distance bound so separated geometries retain their measured distance.
                fromto = np.zeros(6, dtype=np.float64)
                dist = mujoco.mj_geomDistance(
                    self.sim.model._model,
                    self.sim.data._data,
                    g1_id,
                    g2_id,
                    10.0,  # distmax
                    fromto
                )
                if dist < min_dist:
                    min_dist = dist

        return min_dist

    def check_gripper_distance(self,object_geoms):
        g_geoms = [self.robots[0].gripper[self.robots[0].arms[0]]._important_geoms["left_fingerpad"], self.robots[0].gripper[self.robots[0].arms[0]]._important_geoms["right_fingerpad"]]
        gripper_geoms = ['gripper0_right_' + g[0] for g in g_geoms]
        return self.check_distance(object_geoms,gripper_geoms)

    def _save_object_states(self, object_geoms):
        """Cache object positions and quaternions for subsequent collision checks."""
        for geom_name in object_geoms:
            obj_name = geom_name.replace('gripper0_', '').split('_')[0]

            full_obj_name = None
            for moving_obj in self.moving_objects:
                if obj_name in moving_obj:
                    full_obj_name = moving_obj
                    break

            if full_obj_name and full_obj_name in self.obj_body_id:
                body_id = self.obj_body_id[full_obj_name]

                self._prev_object_states[full_obj_name] = {
                    'position': np.array(self.sim.data.body_xpos[body_id]).copy(),
                    'quaternion': np.array(self.sim.data.body_xquat[body_id]).copy()
                }

    def check_collision(self, object_name, position_threshold=None, rotation_threshold=None):
        """Detect robot contact or an object pose change above the configured thresholds.

        object_name accepts one name or a list. Position thresholds are in
        meters and rotation thresholds in radians; omitted values use
        self.collision_thresholds.
        """
        if position_threshold is None:
            position_threshold = self.collision_thresholds['position']
        if rotation_threshold is None:
            rotation_threshold = self.collision_thresholds['rotation']

        if isinstance(object_name, str):
            object_names = [object_name]
        else:
            object_names = object_name

        for obj_name in object_names:
            full_obj_name = None
            if obj_name in self.obj_body_id:
                full_obj_name = obj_name
            else:
                for moving_obj in self.moving_objects:
                    if obj_name in moving_obj or moving_obj in obj_name:
                        full_obj_name = moving_obj
                        break

            if not full_obj_name or full_obj_name not in self.obj_body_id:
                continue

            body_id = self.obj_body_id[full_obj_name]

            robot_keywords = ['robot', 'gripper', 'finger', 'wrist', 'forearm', 'link', 'hand', 'arm', 'panda']

            object_geoms = []
            for geom_id in range(self.sim.model.ngeom):
                if self.sim.model.geom_bodyid[geom_id] == body_id:
                    geom_name = self.sim.model.geom_id2name(geom_id)
                    if geom_name:
                        object_geoms.append(geom_name)

            for i in range(self.sim.data.ncon):
                contact = self.sim.data.contact[i]
                geom1_id = contact.geom1
                geom2_id = contact.geom2

                geom1_name = self.sim.model.geom_id2name(geom1_id)
                geom2_name = self.sim.model.geom_id2name(geom2_id)

                if geom1_name is None or geom2_name is None:
                    continue

                is_object_geom = False
                other_geom_name = None

                for obj_geom in object_geoms:
                    if obj_geom in geom1_name or full_obj_name in geom1_name:
                        is_object_geom = True
                        other_geom_name = geom2_name
                        break
                    if obj_geom in geom2_name or full_obj_name in geom2_name:
                        is_object_geom = True
                        other_geom_name = geom1_name
                        break

                if is_object_geom and other_geom_name:
                    is_robot = any(keyword in other_geom_name.lower() for keyword in robot_keywords)
                    if is_robot:
                        return True

            current_pos = np.array(self.sim.data.body_xpos[body_id])
            current_quat = np.array(self.sim.data.body_xquat[body_id])

            # The first observation establishes a baseline and does not report a collision.
            if full_obj_name not in self._prev_object_states:
                self._prev_object_states[full_obj_name] = {
                    'position': current_pos.copy(),
                    'quaternion': current_quat.copy()
                }
                continue

            prev_state = self._prev_object_states[full_obj_name]
            prev_pos = prev_state['position']
            prev_quat = prev_state['quaternion']

            position_delta = np.linalg.norm(current_pos - prev_pos)

            quat_dot = np.abs(np.dot(current_quat, prev_quat))
            quat_dot = np.clip(quat_dot, -1.0, 1.0)
            rotation_delta = 2 * np.arccos(quat_dot)

            if position_delta > position_threshold or rotation_delta > rotation_threshold:
                self._prev_object_states[full_obj_name] = {
                    'position': current_pos.copy(),
                    'quaternion': current_quat.copy()
                }
                return True

            # Update the baseline even without a collision for the next step's comparison.
            self._prev_object_states[full_obj_name] = {
                'position': current_pos.copy(),
                'quaternion': current_quat.copy()
            }

        return False

    def check_collision_detailed(self, object_names, position_threshold=None, rotation_threshold=None):
        """Return collision_detected, per-object results, and total_collisions.

        Position thresholds are in meters and rotation thresholds in radians.
        """
        if position_threshold is None:
            position_threshold = self.collision_thresholds['position']
        if rotation_threshold is None:
            rotation_threshold = self.collision_thresholds['rotation']

        if isinstance(object_names, str):
            object_names = [object_names]

        collision_results = {
            'collision_detected': False,
            'objects': {},
            'total_collisions': 0
        }

        for obj_name in object_names:
            full_obj_name = None
            if obj_name in self.obj_body_id:
                full_obj_name = obj_name
            else:
                for moving_obj in self.moving_objects:
                    if obj_name in moving_obj or moving_obj in obj_name:
                        full_obj_name = moving_obj
                        break

            if not full_obj_name or full_obj_name not in self.obj_body_id:
                continue

            body_id = self.obj_body_id[full_obj_name]
            current_pos = np.array(self.sim.data.body_xpos[body_id])
            current_quat = np.array(self.sim.data.body_xquat[body_id])

            if full_obj_name not in self._prev_object_states:
                self._prev_object_states[full_obj_name] = {
                    'position': current_pos.copy(),
                    'quaternion': current_quat.copy()
                }
                continue

            prev_state = self._prev_object_states[full_obj_name]
            prev_pos = prev_state['position']
            prev_quat = prev_state['quaternion']

            position_delta = np.linalg.norm(current_pos - prev_pos)
            quat_dot = np.abs(np.dot(current_quat, prev_quat))
            quat_dot = np.clip(quat_dot, -1.0, 1.0)
            rotation_delta = 2 * np.arccos(quat_dot)

            position_collision = position_delta > position_threshold
            rotation_collision = rotation_delta > rotation_threshold
            object_collision = position_collision or rotation_collision

            collision_results['objects'][full_obj_name] = {
                'collision': object_collision,
                'position_delta': float(position_delta),
                'rotation_delta': float(rotation_delta),
                'current_position': current_pos.tolist(),
                'previous_position': prev_pos.tolist(),
                'thresholds_exceeded': {
                    'position': position_collision,
                    'rotation': rotation_collision
                }
            }

            if object_collision:
                collision_results['collision_detected'] = True
                collision_results['total_collisions'] += 1

            self._prev_object_states[full_obj_name] = {
                'position': current_pos.copy(),
                'quaternion': current_quat.copy()
            }

        return collision_results

    def _check_contact(self, sim, geoms_1, geoms_2=None):
        """
        Finds contact between two geom groups.
        Args:
            sim (MjSim): Current simulation object
            geoms_1 (str or list of str or MujocoModel): an individual geom name or list of geom names or a model. If
                a MujocoModel is specified, the geoms checked will be its contact_geoms
            geoms_2 (str or list of str or MujocoModel or None): another individual geom name or list of geom names.
                If a MujocoModel is specified, the geoms checked will be its contact_geoms. If None, will check
                any collision with @geoms_1 to any other geom in the environment
        Returns:
            bool: True if any geom in @geoms_1 is in contact with any geom in @geoms_2.
        """
        # Check if either geoms_1 or geoms_2 is a string, convert to list if so
        if type(geoms_1) is str:
            geoms_1 = [geoms_1]
        elif isinstance(geoms_1, MujocoModel):
            geoms_1 = geoms_1.contact_geoms
        if type(geoms_2) is str:
            geoms_2 = [geoms_2]
        elif isinstance(geoms_2, MujocoModel):
            geoms_2 = geoms_2.contact_geoms
        for i in range(sim.data.ncon):
            contact = sim.data.contact[i]
            geom_1_name = sim.model.geom_id2name(contact.geom1)
            geom_2_name = sim.model.geom_id2name(contact.geom2)

            # Skip if either geom name is None
            if geom_1_name is None or geom_2_name is None:
                continue

            # Process pad_collision naming
            if "pad_collision" in geom_1_name:
                geom_1_name = geom_1_name[15:]

            # check contact geom in geoms
            c1_in_g1 = geom_1_name in geoms_1
            c2_in_g2 = geom_2_name in geoms_2 if geoms_2 is not None else True
            # check contact geom in geoms (flipped)
            c2_in_g1 = geom_1_name in geoms_1
            c1_in_g2 = geom_2_name in geoms_2 if geoms_2 is not None else True
            if (c1_in_g1 and c2_in_g2) or (c1_in_g2 and c2_in_g1):
                # print(geom_2_name)
                return True
        return False

    def check_grasping(self, object_geoms):
        """
        Check if the robot is grasping an object using the configured strategy.

        Args:
            object_geoms (str or MujocoModel): Object to check

        Returns:
            bool: True if grasping according to the current strategy
        """
        # Get object name
        if isinstance(object_geoms, str):
            obj_name = object_geoms
        elif hasattr(object_geoms, 'name'):
            obj_name = object_geoms.name
        else:
            return False
        # Get gripper position if available
        gripper_pos = None
        if hasattr(self, 'robots') and len(self.robots) > 0:
            try:
                # eef_site_id might be a dict (multi-arm robot) or int (single-arm)
                arm_name = self.robots[0].arms[0]
                eef_site_id = self.robots[0].eef_site_id

                if isinstance(eef_site_id, dict):
                    # Multi-arm robot: get the site_id for the specific arm
                    eef_site_id = eef_site_id[arm_name]

                gripper_pos = self.sim.data.site_xpos[eef_site_id]
            except Exception as e:
                print(f"Warning: Could not get gripper position: {e}")
                pass

        # Use strategy manager to detect grasp
        result = self.grasp_strategy_manager.detect(
            self,
            obj_name,
            step_count=self.step_count,
            gripper_pos=gripper_pos
        )
        return result['is_grasping']


    def set_grasp_strategy(self, strategy_name: str):
        """
        Change the grasp detection strategy at runtime.

        Args:
            strategy_name (str): Name of strategy ("simple", "dual", or "advanced")
        """
        self.grasp_strategy_manager.set_strategy(strategy_name)

    def get_grasp_strategy_info(self):
        """Get information about the current grasp detection strategy."""
        return self.grasp_strategy_manager.get_info()

    def check_gripper_contact(self, object_geoms):
        """
        Checks whether the specified gripper as defined by @gripper is grasping the specified object in the environment.
        If multiple grippers are specified, will return True if at least one gripper is grasping the object.

        By default, this will return True if at least one geom in both the "left_fingerpad" and "right_fingerpad" geom
        groups are in contact with any geom specified by @object_geoms. Custom gripper geom groups can be
        specified with @gripper as well.

        Args:
            gripper (GripperModel or str or list of str or list of list of str or dict): If a MujocoModel, this is specific
                gripper to check for grasping (as defined by "left_fingerpad" and "right_fingerpad" geom groups). Otherwise,
                this sets custom gripper geom groups which together define a grasp. This can be a string
                (one group of single gripper geom), a list of string (multiple groups of single gripper geoms) or a
                list of list of string (multiple groups of multiple gripper geoms), or a dictionary in the case
                where the robot has multiple arms/grippers. At least one geom from each group must be in contact
                with any geom in @object_geoms for this method to return True.
            object_geoms (str or list of str or MujocoModel): If a MujocoModel is inputted, will check for any
                collisions with the model's contact_geoms. Otherwise, this should be specific geom name(s) composing
                the object to check for contact.

        Returns:
            bool: True if the gripper is grasping the given object
        """
        # Convert object, gripper geoms into standardized form
        if isinstance(object_geoms, MujocoModel):
            o_geoms = object_geoms.contact_geoms
        else:
            o_geoms = [object_geoms] if type(object_geoms) is str else object_geoms

        g_geoms = [self.robots[0].gripper[self.robots[0].arms[0]]._important_geoms["left_fingerpad"], self.robots[0].gripper[self.robots[0].arms[0]]._important_geoms["right_fingerpad"]]
        # Search for collisions between each gripper geom group and the object geoms group
        for g_group in g_geoms:
            if self._check_contact(self.sim, g_group, o_geoms):
                return True
        return False

    def check_blade_contact(self, object_name):
        """Check gripper contact with blade geoms, falling back to contact0 or a sole geom."""
        obj = self.get_object(object_name)
        if obj is None:
            return False

        contact_geoms = obj.contact_geoms

        blade_geoms = []

        for geom_name in contact_geoms:
            if 'blade' in geom_name.lower():
                blade_geoms.append(geom_name)

        # Fall back to contact0 for assets that do not name their blade geometry.
        if not blade_geoms:
            for geom_name in contact_geoms:
                if 'contact0' in geom_name.lower():
                    blade_geoms.append(geom_name)

        if not blade_geoms and len(contact_geoms) == 1:
            blade_geoms = contact_geoms

        if not blade_geoms:
            return False

        result = self.check_gripper_contact(blade_geoms)

        return result

    def check_arm_force(self, force_threshold=150, debug=False):
        """Return whether summed arm contact force exceeds force_threshold in newtons."""
        arm_keywords = ['robot', 'gripper', 'finger', 'wrist',
                       'forearm', 'link', 'hand', 'arm', 'panda']

        total_force = 0.0
        contact_count = 0
        contact_details = []

        for i in range(self.sim.data.ncon):
            contact = self.sim.data.contact[i]
            geom1_name = self.sim.model.geom_id2name(contact.geom1)
            geom2_name = self.sim.model.geom_id2name(contact.geom2)

            is_arm_contact = False
            matched_keyword = ""
            for keyword in arm_keywords:
                if (keyword in geom1_name.lower() or keyword in geom2_name.lower()):
                    is_arm_contact = True
                    matched_keyword = keyword
                    break

            if is_arm_contact:
                f6 = np.zeros(6)
                mujoco.mj_contactForce(self.sim.model._model, self.sim.data._data, i, f6)
                normal_force = abs(f6[0])  # Magnitude of the normal contact force.
                total_force += normal_force
                contact_count += 1

                if debug:
                    contact_details.append({
                        'geom1': geom1_name,
                        'geom2': geom2_name,
                        'force': normal_force,
                        'keyword': matched_keyword
                    })

        if debug:
            print(f"  Arm contact points: {contact_count}")

            if contact_count > 0:
                for idx, detail in enumerate(contact_details, 1):
                    print(f"  │   [{idx}] {detail['geom1']} ↔ {detail['geom2']}")
                    print(f"    Force: {detail['force']:.6f} N (keyword: '{detail['keyword']}')")

                print(f"  Total force: {total_force:.6f} N")

                threshold_pass = total_force > force_threshold
                print(f"  Threshold check: {'above threshold' if threshold_pass else 'at or below threshold'} ({total_force:.6f} {'>' if threshold_pass else '≤'} {force_threshold:.4f})")
                print(f"  Result: {'True (arm contact force exceeds threshold)' if threshold_pass else 'False (arm contact force is below or at threshold)'}\n")
            else:
                print(f"  Total force: 0.000000 N (no contact)")
                print(f"  Threshold check: at or below threshold (0.000000 ≤ {force_threshold:.4f})")
                print(f"  Result: False (no arm contact force)\n")

        return total_force > force_threshold

    def check_arm_stuck(self, force_threshold=50.0, pose_change_threshold=0.01, consecutive_frames=10, debug=False):
        """Detect sustained contact force with negligible joint motion.

        force_threshold is in newtons and pose_change_threshold in radians.
        Conditions must hold for consecutive_frames simulation steps.
        """
        if not hasattr(self, '_arm_stuck_history'):
            self._arm_stuck_history = {
                'last_qpos': None,
                'stuck_counter': 0,
                'last_step': -1
            }

        # Use seven arm joints plus the mean of the two gripper joints.
        try:
            arm_qpos = self.sim.data.qpos[:7].copy()
            gripper_qpos = np.mean(self.sim.data.qpos[7:9])
            current_qpos = np.append(arm_qpos, gripper_qpos)
        except Exception as e:
            if debug:
                print(f"[CheckArmStuck] Could not read robot configuration: {e}")
            return False

        arm_keywords = ['robot', 'gripper', 'finger', 'wrist', 'forearm', 'link', 'hand', 'arm', 'panda']
        total_force = 0.0
        contact_count = 0

        for i in range(self.sim.data.ncon):
            contact = self.sim.data.contact[i]
            geom1_name = self.sim.model.geom_id2name(contact.geom1)
            geom2_name = self.sim.model.geom_id2name(contact.geom2)

            is_arm_contact = False
            for keyword in arm_keywords:
                if (keyword in geom1_name.lower() or keyword in geom2_name.lower()):
                    is_arm_contact = True
                    break

            if is_arm_contact:
                f6 = np.zeros(6)
                mujoco.mj_contactForce(self.sim.model._model, self.sim.data._data, i, f6)
                total_force += abs(f6[0])
                contact_count += 1

        force_high = total_force > force_threshold

        pose_unchanged = False
        max_joint_change = 0.0
        is_new_step = self.step_count > self._arm_stuck_history['last_step']

        last_qpos_for_debug = self._arm_stuck_history['last_qpos'].copy() if self._arm_stuck_history['last_qpos'] is not None else None

        if self._arm_stuck_history['last_qpos'] is not None and is_new_step:
            pose_diff = np.abs(current_qpos - self._arm_stuck_history['last_qpos'])
            max_joint_change = np.max(pose_diff)
            pose_unchanged = max_joint_change < pose_change_threshold

        # Update history only once per simulation step, even with repeated predicate calls.
        if is_new_step:
            if force_high and pose_unchanged:
                self._arm_stuck_history['stuck_counter'] += 1
            else:
                self._arm_stuck_history['stuck_counter'] = 0

            self._arm_stuck_history['last_qpos'] = current_qpos
            self._arm_stuck_history['last_step'] = self.step_count

        is_stuck = self._arm_stuck_history['stuck_counter'] >= consecutive_frames

        # Log only on a new step or while stuck to avoid duplicate diagnostics.
        should_debug = debug and (is_new_step or is_stuck)

        if should_debug:
            print(f"\n[CheckArmStuck] Step={self.step_count}")
            print(f"  Contact force: {total_force:.2f} N (threshold: {force_threshold:.2f} N) - {'above threshold' if force_high else 'at or below threshold'}")
            print(f"  Contact points: {contact_count}")

            if is_new_step:
                if last_qpos_for_debug is not None:
                    print(f"  Current configuration (8D): [{', '.join([f'{q:.4f}' for q in current_qpos])}]")
                    print(f"  Previous configuration (8D): [{', '.join([f'{q:.4f}' for q in last_qpos_for_debug])}]")
                    pose_diff_str = ', '.join([f'{abs(current_qpos[i] - last_qpos_for_debug[i]):.6f}' for i in range(8)])
                    print(f"  Configuration delta: [{pose_diff_str}]")
                    print(f"  Maximum joint change: {max_joint_change:.6f} rad (threshold: {pose_change_threshold:.6f} rad)")
                    print(f"  Motion check: {'unchanged (stuck condition met)' if pose_unchanged else 'changed (normal motion)'}")
                else:
                    print(f"  Current configuration (8D): [{', '.join([f'{q:.4f}' for q in current_qpos])}]")
                    print(f"  Configuration delta: waiting for a second frame")
            elif is_stuck:
                print(f"  Current configuration (8D): [{', '.join([f'{q:.4f}' for q in current_qpos])}]")

            print(f"  Consecutive qualifying frames: {self._arm_stuck_history['stuck_counter']}/{consecutive_frames}")

            if is_stuck:
                print(f"  Result: stuck (contact force with no motion for at least {consecutive_frames} frames)\n")
            elif force_high and pose_unchanged:
                print(f"  Result: pending (contact force with no motion; frames: {self._arm_stuck_history['stuck_counter']}/{consecutive_frames})\n")
            elif force_high and not pose_unchanged:
                print(f"  Result: not stuck (contact force with normal motion)\n")
            elif not force_high:
                print(f"  Result: not stuck (contact force does not exceed threshold)\n")
            else:
                print(f"  Result: not stuck (conditions not met)\n")

        return is_stuck

    def check_arm_blade_contact(self, object_name):
        """Check contact between any arm link and the object's blade geometry."""
        obj = self.get_object(object_name)
        if obj is None:
            return False

        contact_geoms = obj.contact_geoms

        blade_geoms = []

        for geom_name in contact_geoms:
            if 'blade' in geom_name.lower():
                blade_geoms.append(geom_name)

        # Use the same blade-geometry fallback as gripper contact detection.
        if not blade_geoms:
            for geom_name in contact_geoms:
                if 'contact0' in geom_name.lower():
                    blade_geoms.append(geom_name)

        if not blade_geoms and len(contact_geoms) == 1:
            blade_geoms = contact_geoms

        if not blade_geoms:
            return False

        result = self._check_arm_contact_with_geoms(blade_geoms)

        return result

    def _check_arm_contact_with_geoms(self, target_geoms):
        """Return whether any arm link contacts a geometry in target_geoms."""
        if not target_geoms:
            return False

        arm_keywords = ['robot', 'gripper', 'finger', 'wrist',
                       'forearm', 'link', 'hand', 'arm', 'panda']

        for i in range(self.sim.data.ncon):
            contact = self.sim.data.contact[i]
            geom1_id = contact.geom1
            geom2_id = contact.geom2

            geom1_name = self.sim.model.geom_id2name(geom1_id)
            geom2_name = self.sim.model.geom_id2name(geom2_id)

            if geom1_name is None or geom2_name is None:
                continue

            is_arm_geom1 = any(kw in geom1_name.lower() for kw in arm_keywords)
            is_arm_geom2 = any(kw in geom2_name.lower() for kw in arm_keywords)

            is_target_geom1 = geom1_name in target_geoms
            is_target_geom2 = geom2_name in target_geoms

            if (is_arm_geom1 and is_target_geom2) or (is_arm_geom2 and is_target_geom1):
                return True

        return False

    def check_gripper_contact_part(self, object_1, geom_ids_1):
        assert isinstance(geom_ids_1, list), "geom_ids_1 must be a list of geom ids"

        print(f"\n[CheckGripperContactPart] DEBUG")
        print(f"  Object: {object_1.object_name if hasattr(object_1, 'object_name') else 'unknown'}")
        print(f"  Target geom_ids: {geom_ids_1} (type: {type(geom_ids_1)})")

        geom_1 = object_1.contact_geoms
        print(f"  Object contact_geoms: {geom_1}")

        geoms_to_check = []
        for geom_name in geom_1:
            if isinstance(geom_name, str):
                extracted_int = extract_trailing_int(geom_name)
                print(f"  Processing '{geom_name}': extract_trailing_int={extracted_int} (type: {type(extracted_int)})")

                # Convert only when the geometry name has a numeric suffix.
                if extracted_int is not None:
                    geom_id = str(extracted_int)
                    print(f"    geom_id='{geom_id}' (type: {type(geom_id)})")
                    print(f"    Checking '{geom_id}' in {geom_ids_1}: {geom_id in geom_ids_1}")

                    if geom_id in geom_ids_1:
                        geoms_to_check.append(geom_name)
                        print(f"    Matched; added to contact check")
                else:
                    print(f"    No trailing number; skipping")
            else:
                raise NotImplementedError(f"Invalid geom_id_1: {geom_name}")

        print(f"  Selected geoms: {geoms_to_check}")
        result = self.check_gripper_contact(geoms_to_check)
        print(f"  Contact result: {result}\n")
        return result

    def check_robot_knock(self, object_name):
        """Detect the end of brief robot-object contact.

        Contact lasting at most knock_duration_threshold steps is a knock.
        Return True only on the step when that contact ends.
        """
        try:
            obj = self.get_object(object_name)

            is_new_object = object_name not in self.knock_contact_states
            if is_new_object:
                self.knock_contact_states[object_name] = {
                    'in_contact': False,
                    'contact_start_step': -1,
                    'last_knock_step': -1
                }

            state = self.knock_contact_states[object_name]

            current_contact = self._check_robot_object_contact(object_name)

            previous_contact = state['in_contact']
            current_step = self.step_count

            if not previous_contact and current_contact:
                state['in_contact'] = True
                state['contact_start_step'] = current_step
                return False  # Contact onset is not a knock; wait for separation.

            elif previous_contact and not current_contact:
                state['in_contact'] = False

                if state['contact_start_step'] >= 0:
                    contact_duration = current_step - state['contact_start_step']

                    # A short contact interval qualifies only on its separation step.
                    is_knock = contact_duration <= self.knock_duration_threshold

                    if is_knock:
                        state['last_knock_step'] = current_step
                        return True

                return False

            else:
                return False

        except Exception as e:
            return False

    def _calculate_gripper_object_distance(self, object_name):
        """Return gripper-object distance in meters, or None if unavailable."""
        try:
            import numpy as np

            gripper_pos = None
            if hasattr(self, 'robots') and len(self.robots) > 0:
                robot = self.robots[0]
                if hasattr(robot, 'eef_site_id') and robot.eef_site_id is not None:
                    gripper_pos = self.sim.data.site_xpos[robot.eef_site_id].copy()

            if gripper_pos is None:
                return None

            object_pos = None

            obj = self.get_object(object_name)
            if obj is not None:
                if hasattr(obj, 'get_position'):
                    object_pos = obj.get_position()
                elif object_name in self.obj_body_id:
                    body_id = self.obj_body_id[object_name]
                    object_pos = self.sim.data.body_xpos[body_id].copy()

            if object_pos is None:
                for geom_id in range(self.sim.model.ngeom):
                    geom_name = self.sim.model.geom_id2name(geom_id)
                    if geom_name and object_name.lower() in geom_name.lower():
                        object_pos = self.sim.data.geom_xpos[geom_id].copy()
                        break

            if object_pos is None:
                return None

            distance = np.linalg.norm(gripper_pos - object_pos)
            return distance

        except Exception as e:
            return None

    def _check_robot_object_contact(self, object_name):
        """Check current robot contact with an object or named fixture such as table or floor."""
        try:
            robot_keywords = ['robot', 'gripper', 'finger', 'wrist',
                            'forearm', 'link', 'hand', 'arm', 'panda']

            obj = self.get_object(object_name)
            object_geoms = []

            if obj is not None:
                if isinstance(obj, MujocoModel):
                    object_geoms = obj.contact_geoms
                else:
                    if object_name in self.obj_body_id:
                        body_id = self.obj_body_id[object_name]
                        for geom_id in range(self.sim.model.ngeom):
                            if self.sim.model.geom_bodyid[geom_id] == body_id:
                                geom_name = self.sim.model.geom_id2name(geom_id)
                                if geom_name:
                                    object_geoms.append(geom_name)

            # Resolve fixture geometry by name when there is no standard object model.
            if not object_geoms:
                for geom_id in range(self.sim.model.ngeom):
                    geom_name = self.sim.model.geom_id2name(geom_id)
                    if geom_name and object_name.lower() in geom_name.lower():
                        object_geoms.append(geom_name)

            if not object_geoms:
                object_geoms = [object_name]

            for i in range(self.sim.data.ncon):
                contact = self.sim.data.contact[i]
                geom1_id = contact.geom1
                geom2_id = contact.geom2

                geom1_name = self.sim.model.geom_id2name(geom1_id)
                geom2_name = self.sim.model.geom_id2name(geom2_id)

                if geom1_name is None or geom2_name is None:
                    continue

                is_robot_geom1 = any(kw in geom1_name.lower() for kw in robot_keywords)
                is_robot_geom2 = any(kw in geom2_name.lower() for kw in robot_keywords)

                is_object_geom1 = any(
                    (isinstance(g, str) and (g in geom1_name or object_name.lower() in geom1_name.lower()))
                    for g in object_geoms
                )
                is_object_geom2 = any(
                    (isinstance(g, str) and (g in geom2_name or object_name.lower() in geom2_name.lower()))
                    for g in object_geoms
                )

                if (is_robot_geom1 and is_object_geom2) or (is_robot_geom2 and is_object_geom1):
                    return True

            return False

        except Exception as e:
            return False

    def check_object_object_knock(self, object_name1, object_name2):
        """Detect separation after contact lasting at most knock_duration_threshold steps.

        Return True only on the step when brief contact between the objects ends.
        """
        try:
            # Normalize the pair so both argument orders share the same contact history.
            obj_pair = tuple(sorted([object_name1, object_name2]))

            if obj_pair not in self.knock_binary_contact_states:
                self.knock_binary_contact_states[obj_pair] = {
                    'in_contact': False,
                    'contact_start_step': -1,
                    'last_knock_step': -1
                }

            state = self.knock_binary_contact_states[obj_pair]

            current_contact = self._check_object_object_contact(object_name1, object_name2)

            previous_contact = state['in_contact']
            current_step = self.step_count

            if not previous_contact and current_contact:
                state['in_contact'] = True
                state['contact_start_step'] = current_step
                return False  # Contact onset is not a knock; wait for separation.

            elif previous_contact and not current_contact:
                state['in_contact'] = False

                if state['contact_start_step'] >= 0:
                    contact_duration = current_step - state['contact_start_step']

                    # A short contact interval qualifies only on its separation step.
                    is_knock = contact_duration <= self.knock_duration_threshold

                    if is_knock:
                        state['last_knock_step'] = current_step
                        return True

                return False

            else:
                return False

        except Exception as e:
            return False

    def _check_object_object_contact(self, object_name1, object_name2):
        """Return whether two objects are currently in contact, regardless of duration."""
        try:
            object_geoms1 = self._get_object_geoms(object_name1)
            object_geoms2 = self._get_object_geoms(object_name2)

            if not object_geoms1 or not object_geoms2:
                return False

            for i in range(self.sim.data.ncon):
                contact = self.sim.data.contact[i]
                geom1_id = contact.geom1
                geom2_id = contact.geom2

                geom1_name = self.sim.model.geom_id2name(geom1_id)
                geom2_name = self.sim.model.geom_id2name(geom2_id)

                if geom1_name is None or geom2_name is None:
                    continue

                is_obj1_geom1 = any(
                    (isinstance(g, str) and (g in geom1_name or object_name1.lower() in geom1_name.lower()))
                    for g in object_geoms1
                )
                is_obj1_geom2 = any(
                    (isinstance(g, str) and (g in geom2_name or object_name1.lower() in geom2_name.lower()))
                    for g in object_geoms1
                )

                is_obj2_geom1 = any(
                    (isinstance(g, str) and (g in geom1_name or object_name2.lower() in geom1_name.lower()))
                    for g in object_geoms2
                )
                is_obj2_geom2 = any(
                    (isinstance(g, str) and (g in geom2_name or object_name2.lower() in geom2_name.lower()))
                    for g in object_geoms2
                )

                if (is_obj1_geom1 and is_obj2_geom2) or (is_obj1_geom2 and is_obj2_geom1):
                    return True

            return False

        except Exception as e:
            return False

    def _get_object_geoms(self, object_name):
        """Return geometry names for an object or named fixture."""
        object_geoms = []

        obj = self.get_object(object_name)

        if obj is not None:
            if isinstance(obj, MujocoModel):
                object_geoms = obj.contact_geoms
            else:
                if object_name in self.obj_body_id:
                    body_id = self.obj_body_id[object_name]
                    for geom_id in range(self.sim.model.ngeom):
                        if self.sim.model.geom_bodyid[geom_id] == body_id:
                            geom_name = self.sim.model.geom_id2name(geom_id)
                            if geom_name:
                                object_geoms.append(geom_name)

        if not object_geoms:
            for geom_id in range(self.sim.model.ngeom):
                geom_name = self.sim.model.geom_id2name(geom_id)
                if geom_name and object_name.lower() in geom_name.lower():
                    object_geoms.append(geom_name)

        if not object_geoms:
            object_geoms = [object_name]

        return object_geoms

    def check_sweeping(self, object_name, debug=False):
        """Detect horizontal object speed above the sweeping threshold.

        Speed is estimated from positions across simulation steps; robot
        contact is not required, so sliding or airborne objects may qualify.
        """
        try:
            obj = self.get_object(object_name)
            if obj is None:
                print(f"[CheckSweeping] Object '{object_name}' not found\n")
                return False

            horizontal_vel_threshold = 0.05  # Horizontal speed threshold in m/s.


            current_position = None
            if object_name in self.obj_body_id:
                body_id = self.obj_body_id[object_name]
                try:
                    current_position = self.sim.data.body_xpos[body_id].copy()
                except Exception as e:
                    print(f"  [CheckSweeping] Could not read object position: {e}")
            else:
                print(f"  [CheckSweeping] Object '{object_name}' is not in obj_body_id")

            if current_position is None:
                print(f"  Result: False (object position unavailable)\n")
                return False


            object_vel_available = False
            horizontal_vel = 0.0
            vertical_vel = 0.0
            velocity_vector = None

            last_position_for_debug = None
            last_step_for_debug = None
            steps_diff_for_debug = 0

            if object_name in self.sweeping_positions:
                last_data = self.sweeping_positions[object_name]
                last_position = last_data['last_position']
                last_step = last_data['last_step']

                last_position_for_debug = last_position.copy()
                last_step_for_debug = last_step
                steps_diff_for_debug = self.step_count - last_step

                # Estimate speed only when the simulation step changes.
                if self.step_count > last_step:
                    position_diff = current_position - last_position

                    # Convert elapsed steps to time using the simulator timestep.
                    dt = self.sim.model.opt.timestep
                    steps_diff = self.step_count - last_step
                    time_diff = steps_diff * dt

                    if time_diff > 0:
                        velocity_vector = position_diff / time_diff
                        horizontal_vel = np.linalg.norm(velocity_vector[:2])
                        vertical_vel = abs(velocity_vector[2])
                        object_vel_available = True
                    else:
                        object_vel_available = False

                    self.sweeping_positions[object_name] = {
                        'last_position': current_position.copy(),
                        'last_step': self.step_count
                    }
                else:
                    # Reuse cached speed for repeated queries within the same step.
                    object_vel_available = False
            else:
                # The first observation only establishes the position baseline.
                object_vel_available = False
                self.sweeping_positions[object_name] = {
                    'last_position': current_position.copy(),
                    'last_step': self.step_count
                }


            if (object_vel_available and
                horizontal_vel >= horizontal_vel_threshold):
                print(f"  Result: True (rapid horizontal object motion)\n")
                return True

            if not object_vel_available:
                print(f"  Result: False (object velocity unavailable)\n")
            elif horizontal_vel < horizontal_vel_threshold:
                print(f"  Result: False (horizontal speed below threshold: {horizontal_vel:.6f} < {horizontal_vel_threshold})\n")
            else:
                print(f"  Result: False (conditions not met)\n")
            return False

        except Exception as e:
            print(f"[CheckSweeping] Error: {e}\n")
            import traceback
            traceback.print_exc()
            return False

    def _eval_predicate(self, state):
        if len(state) == 3:
            predicate_fn_name = state[0]
            # Checking binary logical predicates
            if predicate_fn_name == "checkgrippercontactpart":
                return eval_predicate_fn(predicate_fn_name, self.object_states_dict[state[1]], state[2])
            elif predicate_fn_name == "checkgripperdistance":
                object_1_name = state[1]
                return float(state[2]) >= eval_predicate_fn(
                    predicate_fn_name,
                    self.object_states_dict[object_1_name],
                )
            else:
                object_1_name = state[1]
                object_2_name = state[2]
                return eval_predicate_fn(
                predicate_fn_name,
                self.object_states_dict[object_1_name],
                self.object_states_dict[object_2_name],
                )
        elif len(state) == 2:
            # Checking unary logical predicates
            predicate_fn_name = state[0]
            object_name = state[1]
            return eval_predicate_fn(
                predicate_fn_name, self.object_states_dict[object_name]
            )
        elif len(state) == 4:
            # Checking binary logical predicates
            predicate_fn_name = state[0]
            object_1_name = state[1]
            object_2_name = state[2]
            if predicate_fn_name == "checkdistance":
                return float(state[3]) >= eval_predicate_fn(
                    predicate_fn_name,
                    self.object_states_dict[object_1_name],
                    self.object_states_dict[object_2_name],
                )
            else:
                return float(state[3]) < eval_predicate_fn(
                    predicate_fn_name,
                    self.object_states_dict[object_1_name],
                    self.object_states_dict[object_2_name],
                )
        elif len(state) == 5:
            # Checking binary logical predicates
            predicate_fn_name = state[0]
            if predicate_fn_name == "incontactpart":
                object_1_name = state[1]
                object_2_name = state[2]
                geom_name_1 = state[3]
                geom_name_2 = state[4]
                if geom_name_1 == "all":
                    geom_name_1 = object_1_name
                elif isinstance(geom_name_1, list):
                    geom_name_1 = [object_1_name + '_g' + (geom_name) for geom_name in geom_name_1]
                else:
                    raise NotImplementedError(f"Invalid geom_name_1: {geom_name_1}")
                if geom_name_2 == "all":
                    geom_name_2 = object_2_name
                elif isinstance(geom_name_2, list):
                    geom_name_2 = [object_2_name + '_g' + (geom_name) for geom_name in geom_name_2]
                else:
                    raise NotImplementedError(f"Invalid geom_name_2: {geom_name_2}")
                return self._check_contact(geom_name_1, geom_name_2)
            else:
                raise NotImplementedError(f"Invalid state length: {len(state)}")
        else:
            raise NotImplementedError(f"Invalid state length: {len(state)}")


from PIL import Image,ImageEnhance

def ajust_image(img,brightness=0,contrast=0,saturation=0,temperature=6500):
    """Adjust brightness, contrast, and saturation using values in [-1, 1]."""
    img_pil = Image.fromarray(img)

    if brightness:
        bright_enhancer = ImageEnhance.Brightness(img_pil)
        img_pil = bright_enhancer.enhance(1+brightness)

    if contrast:
        contrast_enhancer = ImageEnhance.Contrast(img_pil)
        img_pil = contrast_enhancer.enhance(1+contrast)

    if saturation:
        saturate_enhancer = ImageEnhance.Color(img_pil)
        img_pil = saturate_enhancer.enhance(1+saturation)
    img_final = np.array(img_pil)
    if temperature!=6500:
        img_final = adjust_temperature(img_final,temperature)
    return img_final


def adjust_temperature(img, temperature=6500):
    """Adjust the color temperature of an RGB PIL image; 6500 K is neutral."""

    if temperature <= 6500:
        r_factor = 1.0 + (6500 - temperature) / 6500 * 0.4
        g_factor = 1.0
        b_factor = 1.0 - (6500 - temperature) / 6500 * 0.4
    else:
        r_factor = 1.0 - (temperature - 6500) / 6500 * 0.4
        g_factor = 1.0
        b_factor = 1.0 + (temperature - 6500) / 6500 * 0.4

    img[..., 0] = np.clip(img[..., 0] * r_factor, 0, 255)
    img[..., 1] = np.clip(img[..., 1] * g_factor, 0, 255)
    img[..., 2] = np.clip(img[..., 2] * b_factor, 0, 255)

    return img.astype(np.uint8)