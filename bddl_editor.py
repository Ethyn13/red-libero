#!/usr/bin/env python3
"""Edit BDDL objects, regions, placements, and safety cost rules."""

import sys
import os
from typing import Optional, List, Tuple, Dict, Union
from copy import deepcopy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'libero'))
from libero.libero.envs import bddl_utils
from bddl_save_utils import dict_to_bddl_string, save_dict_as_bddl


class BDDLEditor:
    """Editor for parsed BDDL scene definitions."""

    def __init__(self, bddl_file_path: Optional[str] = None):
        """Load a BDDL file, or create an empty scene when no path is provided."""
        if bddl_file_path:
            self.parsed_dict = bddl_utils.robosuite_parse_problem(bddl_file_path)
            self.source_file = bddl_file_path
        else:
            self.parsed_dict = {
                "problem_name": "new_problem",
                "fixtures": {},
                "regions": {},
                "objects": {},
                "scene_properties": {},
                "initial_state": [],
                "goal_state": [],
                "language_instruction": [],
                "obj_of_interest": [],
                "cost_state": [],
                "moving_objects": [],
                "image_settings": {}
            }
            self.source_file = None

    # ============================================================
    # ============================================================

    def add_object_with_region(
        self,
        obj_name: str,
        obj_type: str,
        position: Tuple[float, float],
        yaw_rotation: Optional[Tuple[float, float]] = None,
        region_half_len: float = 0.01,
        target: str = "main_table",
        add_to_interest: bool = False
    ) -> str:
        """Add an object at an (x, y) region on target and return the region name.

        yaw_rotation sets the angle range; region_half_len sets the half-size.
        add_to_interest controls membership in the objects-of-interest list.
        """
        if obj_type not in self.parsed_dict["objects"]:
            self.parsed_dict["objects"][obj_type] = []
        if obj_name not in self.parsed_dict["objects"][obj_type]:
            self.parsed_dict["objects"][obj_type].append(obj_name)

        region_name = f"{target}_{obj_name}_region"
        x, y = position

        region_data = {
            "target": target,
            "ranges": [[
                x - region_half_len,
                y - region_half_len,
                x + region_half_len,
                y + region_half_len
            ]],
            "extra": [],
            "yaw_rotation": list(yaw_rotation) if yaw_rotation else [0, 0],
            "rgba": [0, 0, 1, 0]
        }

        self.parsed_dict["regions"][region_name] = region_data

        init_predicate = ["on", obj_name, region_name]
        if init_predicate not in self.parsed_dict["initial_state"]:
            self.parsed_dict["initial_state"].append(init_predicate)

        if add_to_interest and obj_name not in self.parsed_dict["obj_of_interest"]:
            self.parsed_dict["obj_of_interest"].append(obj_name)

        print(f"Added object: {obj_name} ({obj_type}) in region {region_name}")
        return region_name

    def add_object_on_object(
        self,
        obj_name: str,
        obj_type: str,
        base_object: str,
        relation: str = "on",
        add_to_interest: bool = False
    ):
        """Add an object on or in an existing object or region."""
        assert relation in ["on", "in"], "relation must be 'on' or 'in'"

        if obj_type not in self.parsed_dict["objects"]:
            self.parsed_dict["objects"][obj_type] = []
        if obj_name not in self.parsed_dict["objects"][obj_type]:
            self.parsed_dict["objects"][obj_type].append(obj_name)

        init_predicate = [relation, obj_name, base_object]
        if init_predicate not in self.parsed_dict["initial_state"]:
            self.parsed_dict["initial_state"].append(init_predicate)

        if add_to_interest and obj_name not in self.parsed_dict["obj_of_interest"]:
            self.parsed_dict["obj_of_interest"].append(obj_name)

        print(f"Added object: {obj_name} ({obj_type}) {relation} {base_object}")

    # ============================================================
    # ============================================================

    def move_object(
        self,
        obj_name: str,
        new_position: Optional[Tuple[float, float]] = None,
        new_yaw_rotation: Optional[Tuple[float, float]] = None,
        region_half_len: Optional[float] = None
    ):
        """Update an object's region position, yaw, or half-size; None leaves a field unchanged."""
        region_name = None
        for reg_name in self.parsed_dict["regions"].keys():
            if obj_name in reg_name:
                region_name = reg_name
                break

        if not region_name:
            raise ValueError(f"No region found for object {obj_name}")

        region_data = self.parsed_dict["regions"][region_name]

        if new_position:
            x, y = new_position
            half_len = region_half_len if region_half_len else 0.01

            if region_data.get("ranges") and len(region_data["ranges"]) > 0:
                old_range = region_data["ranges"][0]
                half_len = (old_range[2] - old_range[0]) / 2

            region_data["ranges"] = [[
                x - half_len,
                y - half_len,
                x + half_len,
                y + half_len
            ]]
            print(f"Moved object {obj_name} to ({x}, {y})")

        if new_yaw_rotation:
            region_data["yaw_rotation"] = list(new_yaw_rotation)
            print(f"Rotated object {obj_name} to {new_yaw_rotation}")

    # ============================================================
    # ============================================================

    def swap_objects(self, obj1_name: str, obj2_name: str):
        """Swap the placement regions of two objects."""
        region1_name = None
        region2_name = None

        for reg_name in self.parsed_dict["regions"].keys():
            if obj1_name in reg_name:
                region1_name = reg_name
            if obj2_name in reg_name:
                region2_name = reg_name

        if not region1_name or not region2_name:
            raise ValueError(f"Region not found for {obj1_name} or {obj2_name}")

        region1_data = deepcopy(self.parsed_dict["regions"][region1_name])
        region2_data = deepcopy(self.parsed_dict["regions"][region2_name])

        temp_ranges = region1_data["ranges"]
        temp_yaw = region1_data["yaw_rotation"]

        region1_data["ranges"] = region2_data["ranges"]
        region1_data["yaw_rotation"] = region2_data["yaw_rotation"]

        region2_data["ranges"] = temp_ranges
        region2_data["yaw_rotation"] = temp_yaw

        self.parsed_dict["regions"][region1_name] = region1_data
        self.parsed_dict["regions"][region2_name] = region2_data

        print(f"Swapped object positions: {obj1_name} <-> {obj2_name}")

    # ============================================================
    # ============================================================

    def remove_object(self, obj_name: str):
        """Remove an object and its references from the scene."""
        for obj_type, obj_list in self.parsed_dict["objects"].items():
            if obj_name in obj_list:
                obj_list.remove(obj_name)
                print(f"Removed from objects: {obj_name}")
                break

        regions_to_remove = [
            reg_name for reg_name in self.parsed_dict["regions"].keys()
            if obj_name in reg_name
        ]
        for reg_name in regions_to_remove:
            del self.parsed_dict["regions"][reg_name]
            print(f"Removed region: {reg_name}")

        self.parsed_dict["initial_state"] = [
            state for state in self.parsed_dict["initial_state"]
            if obj_name not in (state if isinstance(state, list) else [state])
        ]

        self.parsed_dict["goal_state"] = [
            goal for goal in self.parsed_dict["goal_state"]
            if obj_name not in (goal if isinstance(goal, list) else [goal])
        ]

        if obj_name in self.parsed_dict["obj_of_interest"]:
            self.parsed_dict["obj_of_interest"].remove(obj_name)
            print(f"Removed from objects of interest: {obj_name}")

        print(f"Removed object: {obj_name}")

    # ============================================================
    # ============================================================

    def add_cost_rule(
        self,
        predicate: Union[str, List],
        operator: str = "or"
    ):
        """Add a predicate under a cost operator such as or, and, or cum.

        Predicates may be strings or nested lists, for example
        ["checkgrasping", "knife_1"].
        """
        if not isinstance(self.parsed_dict["cost_state"], list):
            self.parsed_dict["cost_state"] = []

        if isinstance(predicate, str):
            predicate = [predicate]

        if len(self.parsed_dict["cost_state"]) == 0:
            self.parsed_dict["cost_state"] = [[operator.lower(), predicate]]
        else:
            if (len(self.parsed_dict["cost_state"]) == 1 and
                isinstance(self.parsed_dict["cost_state"][0], list) and
                self.parsed_dict["cost_state"][0][0].lower() == operator.lower()):
                self.parsed_dict["cost_state"][0].append(predicate)
            else:
                old_cost = deepcopy(self.parsed_dict["cost_state"])
                self.parsed_dict["cost_state"] = [[operator.lower(), *old_cost, predicate]]

        print(f"Added cost rule: {predicate}")

    def remove_cost_rule(self, predicate: Union[str, List]):
        """Remove a predicate from the cost expression."""
        if not self.parsed_dict["cost_state"]:
            print("No cost rules to remove")
            return

        if isinstance(predicate, str):
            predicate = [predicate]

        def remove_from_list(lst):
            if not isinstance(lst, list):
                return lst

            result = []
            for item in lst:
                if isinstance(item, list):
                    if item == predicate:
                        continue
                    else:
                        processed = remove_from_list(item)
                        if processed:
                            result.append(processed)
                else:
                    result.append(item)

            return result if len(result) > 1 or (len(result) == 1 and isinstance(result[0], str)) else (result[0] if result else [])

        old_cost = deepcopy(self.parsed_dict["cost_state"])
        self.parsed_dict["cost_state"] = remove_from_list(old_cost)

        if not self.parsed_dict["cost_state"]:
            self.parsed_dict["cost_state"] = []

        print(f"Removed cost rule: {predicate}")

    def clear_all_costs(self):
        """Clear all cost rules."""
        self.parsed_dict["cost_state"] = []
        print("Cleared all cost rules")

    # ============================================================
    # ============================================================

    def get_all_objects(self) -> Dict[str, List[str]]:
        """Return movable objects, excluding fixtures."""
        return self.parsed_dict["objects"]

    def get_all_fixtures(self) -> Dict[str, List[str]]:
        """Return scene fixtures such as tables, cabinets, and stoves."""
        if "fixtures" in self.parsed_dict:
            fixtures = self.parsed_dict["fixtures"]

            print(f"[DEBUG] fixtures type: {type(fixtures)}")
            print(f"[DEBUG] fixtures value: {fixtures}")

            if isinstance(fixtures, dict):
                return fixtures
            elif isinstance(fixtures, list):
                fixtures_dict = {}
                for item in fixtures:
                    if isinstance(item, (list, tuple)) and len(item) == 2:
                        name, type_name = item
                        if type_name not in fixtures_dict:
                            fixtures_dict[type_name] = []
                        fixtures_dict[type_name].append(name)
                return fixtures_dict
            elif isinstance(fixtures, str):
                fixtures_dict = {}
                for line in fixtures.strip().split('\n'):
                    line = line.strip()
                    if '-' in line:
                        parts = line.split('-')
                        if len(parts) == 2:
                            name = parts[0].strip()
                            type_name = parts[1].strip()
                            if type_name not in fixtures_dict:
                                fixtures_dict[type_name] = []
                            fixtures_dict[type_name].append(name)
                return fixtures_dict
        return {}

    def get_object_position(self, obj_name: str) -> Optional[Tuple[float, float]]:
        """Return an object's (x, y) region position, or None if unavailable."""
        for reg_name, reg_data in self.parsed_dict["regions"].items():
            if obj_name in reg_name and reg_data.get("ranges"):
                ranges = reg_data["ranges"][0]
                x = (ranges[0] + ranges[2]) / 2
                y = (ranges[1] + ranges[3]) / 2
                return (x, y)
        return None

    def list_all_objects(self):
        """Print all scene objects and their positions."""
        print("\nScene objects:")
        print("=" * 50)
        for obj_type, obj_list in self.parsed_dict["objects"].items():
            for obj_name in obj_list:
                pos = self.get_object_position(obj_name)
                pos_str = f"Position: ({pos[0]:.3f}, {pos[1]:.3f})" if pos else "Position: N/A"
                print(f"  - {obj_name} ({obj_type}) | {pos_str}")
        print("=" * 50)

    def list_all_costs(self):
        """Print all cost rules."""
        print("\nCost rules:")
        print("=" * 50)
        if self.parsed_dict["cost_state"]:
            import json
            print(json.dumps(self.parsed_dict["cost_state"], indent=2))
        else:
            print("  (no cost rules)")
        print("=" * 50)

    def save(self, output_path: str):
        """Write the scene to a BDDL file."""
        save_dict_as_bddl(self.parsed_dict, output_path)
        print(f"Saved file: {output_path}")

    def to_bddl_string(self) -> str:
        """Serialize the scene as BDDL text."""
        return dict_to_bddl_string(self.parsed_dict)


# ============================================================
# ============================================================

def demo():
    """Demonstrate object and cost-rule edits."""
    print("=" * 70)
    print("BDDL editor example")
    print("=" * 70)

    editor = BDDLEditor("libero/libero/bddl_files/libero_goal/put_the_bowl_on_the_plate.bddl")

    print("\n[Original scene]")
    editor.list_all_objects()

    print("\n[Step 1: Add an object in a region]")
    editor.add_object_with_region(
        obj_name="new_cup_1",
        obj_type="cup",
        position=(0.2, 0.3),
        yaw_rotation=(0, 0),
        add_to_interest=True
    )

    print("\n[Step 2: Add an object on an existing object]")
    editor.add_object_on_object(
        obj_name="new_spoon_1",
        obj_type="spoon",
        base_object="plate_1",
        relation="on"
    )

    print("\n[Step 3: Move an object]")
    editor.move_object("new_cup_1", new_position=(0.1, 0.1))

    print("\n[Step 4: Add cost rules]")
    editor.add_cost_rule(["checkgrasping", "new_spoon_1"], operator="or")
    editor.add_cost_rule(["cum", ["on", "new_cup_1", "plate_1"]], operator="or")

    editor.list_all_costs()

    print("\n[Modified scene]")
    editor.list_all_objects()

    print("\n[Save results]")
    editor.save("libero/libero/bddl_files/libero_goal/put_the_bowl_on_the_plate_edited.bddl")

    print("\n" + "=" * 70)
    print("Example completed")
    print("=" * 70)


if __name__ == "__main__":
    demo()

