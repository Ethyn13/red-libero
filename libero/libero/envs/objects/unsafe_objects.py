import os
import re
import numpy as np

from robosuite.models.objects import MujocoXMLObject
from robosuite.utils.mjcf_utils import xml_path_completion

import pathlib

absolute_path = pathlib.Path(__file__).parent.parent.parent.absolute()

from libero.libero.envs.base_object import (
    register_visual_change_object,
    register_object,
)


# ============================================================================
# Unsafe Articulated Objects (from articulated_objects.py)
# ============================================================================

class UnsafeArticulatedObject(MujocoXMLObject):
    def __init__(self, name, obj_name, joints=[dict(type="free", damping="0.0005")], duplicate_collision_geoms=False):
        super().__init__(
            os.path.join(
                str(absolute_path), f"assets/unsafe_objects/{obj_name}.xml"
            ),
            name=name,
            joints=joints,
            obj_type="all",
            duplicate_collision_geoms=duplicate_collision_geoms,
        )
        self.category_name = "_".join(
            re.sub(r"([A-Z])", r" \1", self.__class__.__name__).split()
        ).lower()
        self.rotation = (-np.pi / 2, np.pi / 2)
        self.rotation_axis = "x"

        articulation_object_properties = {
            "default_open_ranges": [],
            "default_close_ranges": [],
        }
        self.object_properties = {
            "articulation": articulation_object_properties,
            "vis_site_names": {},
        }

    def is_open(self, qpos):
        raise NotImplementedError

    def is_close(self, qpos):
        raise NotImplementedError

    def is_almost_close(self, qpos):
        """Check relaxed closure using default_close_ranges, or fall back to is_close if absent."""
        if (hasattr(self, 'object_properties') and
            'articulation' in self.object_properties and
            self.object_properties['articulation'].get('default_close_ranges')):
            close_ranges = self.object_properties['articulation']['default_close_ranges']
            if len(close_ranges) >= 2:
                close_min = min(close_ranges)
                close_max = max(close_ranges)
                if close_min < close_max:
                    relaxed_threshold = close_min - 0.05
                    return qpos > relaxed_threshold
                else:
                    relaxed_threshold = close_max + 0.05
                    return qpos < relaxed_threshold
        return self.is_close(qpos)

@register_object
class Ball(UnsafeArticulatedObject):
    def __init__(
        self,
        name="ball",
        obj_name="ball",
        joints=None,
    ):
        super().__init__(name, obj_name, joints)


@register_object
class WaterBall(UnsafeArticulatedObject):
    def __init__(
        self,
        name="water_ball",
        obj_name="water_ball",
        joints=[dict(type="free", damping="0.0005")],
    ):
        super().__init__(name, obj_name, joints)
        self.z_offset = 0.01
        self.rotation_axis = "x"
@register_object
class Block(UnsafeArticulatedObject):
    def __init__(
        self,
        name="block",
        obj_name="block",
        joints=[dict(type="free", damping="0.0005")],
    ):
        super().__init__(name, obj_name, joints)
@register_object
class BlockSmall(UnsafeArticulatedObject):
    def __init__(
        self,
        name="block_small",
        obj_name="block_small",
        joints=[dict(type="free", damping="0.0005")],
    ):
        super().__init__(name, obj_name, joints)

@register_object
class BlockLarge(UnsafeArticulatedObject):
    def __init__(
        self,
        name="block_large",
        obj_name="block_large",
        joints=[dict(type="free", damping="0.0005")],
    ):
        super().__init__(name, obj_name, joints)

# ============================================================================
# Unsafe Objects from turbosquid_objects (using unsafe_objects path)
# ============================================================================

class UnsafeTurbosquidObjects(MujocoXMLObject):
    def __init__(self, name, obj_name, joints=[dict(type="free", damping="0.0005")]):
        super().__init__(
            os.path.join(
                str(absolute_path),
                f"assets/unsafe_objects/{obj_name}/{obj_name}.xml",
            ),
            name=name,
            joints=joints,
            obj_type="all",
            duplicate_collision_geoms=False,
        )
        self.category_name = "_".join(
            re.sub(r"([A-Z])", r" \1", self.__class__.__name__).split()
        ).lower()
        self.rotation = (0, 0)
        self.rotation_axis = "x"
        self.object_properties = {"vis_site_names": {}}


@register_object
class Fork(UnsafeTurbosquidObjects):
    def __init__(
        self,
        name="fork",
        obj_name="fork",
        joints=[dict(type="free", damping="0.0005")],
    ):
        super().__init__(name, obj_name, joints)


@register_object
class Candle(UnsafeTurbosquidObjects):
    def __init__(
        self,
        name="candle",
        obj_name="candle",
        joints=[dict(type="free", damping="0.0005")],
    ):
        super().__init__(name, obj_name, joints)


@register_object
class BottledWater(UnsafeTurbosquidObjects):
    def __init__(
        self,
        name="bottled_water",
        obj_name="bottled_water",
        joints=[dict(type="free", damping="0.0005")],
    ):
        super().__init__(name, obj_name, joints)


# ============================================================================
# Custom Objects (using absolute paths)
# ============================================================================
absolute_path = pathlib.Path(__file__).parent.parent.parent.absolute()

class UnsafeCustomObjects(MujocoXMLObject):
    def __init__(self, custom_path, name, obj_name, joints=[dict(type="free", damping="0.0005")]):
        if custom_path:
            xml_path = os.path.join(str(absolute_path), custom_path)
        else:
            xml_path = os.path.join(
                str(absolute_path),
                f"assets/unsafe_objects/{obj_name}/{obj_name}.xml",
            )

        super().__init__(
            xml_path,
            name=name,
            joints=joints,
            obj_type="all",
            duplicate_collision_geoms=False,
        )
        self.category_name = "_".join(
            re.sub(r"([A-Z])", r" \1", self.__class__.__name__).split()
        ).lower()
        self.rotation = (-np.pi/2, -np.pi/2)
        self.object_properties = {"vis_site_names": {}}

z_offset = 0.0
@register_object
class KitchenKnife(UnsafeCustomObjects):
    def __init__(self,
                 name="kitchen_knife",
                 obj_name="kitchen_knife",
                 ):
        super().__init__(
            custom_path='assets/unsafe_objects/kitchen_knife/kitchen_knife.xml',
            name=name,
            obj_name=obj_name,
        )
        self.z_offset = z_offset
        self.rotation_axis = "x"


@register_object
class Knife(UnsafeCustomObjects):
    def __init__(self,
                 name="knife",
                 obj_name="knife",
                 ):
        super().__init__(
            custom_path='assets/unsafe_objects/knife/knife.xml',
            name=name,
            obj_name=obj_name,
        )
        self.z_offset = z_offset
        self.rotation_axis = "x"


@register_object
class KnifeN(UnsafeCustomObjects):
    def __init__(self,
                 name="knife_n",
                 obj_name="knife_n",
                 ):
        super().__init__(
            custom_path='assets/unsafe_objects/knife_n/knife_n.xml',
            name=name,
            obj_name=obj_name,
        )
        self.z_offset = z_offset
        self.rotation_axis = "x"


@register_object
class Hammer(UnsafeCustomObjects):
    def __init__(self,
                 name="hammer",
                 obj_name="hammer",
                 ):
        super().__init__(
            custom_path='assets/unsafe_objects/hammer/hammer.xml',
            name=name,
            obj_name=obj_name,
        )
        self.z_offset = z_offset
        self.rotation_axis = "x"


@register_object
class HammerHandle(UnsafeCustomObjects):
    def __init__(self,
                 name="hammer_handle",
                 obj_name="hammer_handle",
                 ):
        super().__init__(
            custom_path='assets/unsafe_objects/hammer_handle/hammer_handle.xml',
            name=name,
            obj_name=obj_name,
        )
        self.z_offset = z_offset
        self.rotation_axis = "x"


@register_object
class Scissors(UnsafeCustomObjects):
    def __init__(self,
                 name="scissors",
                 obj_name="scissors",
                 ):
        super().__init__(
            custom_path='assets/unsafe_objects/scissors/scissors.xml',
            name=name,
            obj_name=obj_name,
        )
        self.z_offset = z_offset
        self.rotation_axis = "x"


@register_object
class ScissorsN(UnsafeCustomObjects):
    def __init__(self,
                 name="scissors_n",
                 obj_name="scissors_n",
                 ):
        super().__init__(
            custom_path='assets/unsafe_objects/scissors_n/scissors_n.xml',
            name=name,
            obj_name=obj_name,
        )
        self.z_offset = z_offset
        self.rotation_axis = "x"

