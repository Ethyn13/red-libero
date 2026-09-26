#!/usr/bin/env python3
"""Convert parsed BDDL dictionaries back to native BDDL text."""

import os
import sys
from pathlib import Path

# Add LIBERO to path
libero_path = os.path.join(os.path.dirname(__file__), 'libero')
if libero_path not in sys.path:
    sys.path.insert(0, libero_path)

# Try different import methods
try:
    from libero.libero.envs import bddl_utils
except ModuleNotFoundError:
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from libero.libero.envs import bddl_utils
    except ModuleNotFoundError:
        # Direct import for development
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "bddl_utils",
            os.path.join(os.path.dirname(__file__), "libero/libero/envs/bddl_utils.py")
        )
        bddl_utils = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bddl_utils)


def format_predicate(pred, indent_level=0):
    """Recursively format a predicate, including nested lists and tuples."""
    indent = "  " * indent_level

    if isinstance(pred, str):
        return pred
    elif isinstance(pred, (list, tuple)):
        if not pred:
            return "()"

        # Unwrap single-element predicate containers before formatting.
        if len(pred) == 1 and isinstance(pred[0], (list, tuple)):
            return format_predicate(pred[0], indent_level)

        if not isinstance(pred[0], str):
            parts = []
            for item in pred:
                if isinstance(item, (list, tuple)):
                    parts.append(format_predicate(item, indent_level))
                else:
                    parts.append(str(item))
            return " ".join(parts)

        first_elem = pred[0]

        # Capitalize logical operators and predicate names for native BDDL.
        if first_elem.lower() in ['and', 'or', 'not', 'cum']:
            first_elem = first_elem.capitalize()
        elif first_elem.lower() in ['on', 'in', 'open', 'closed', 'toggled', 'checkgrasping',
                                      'inside', 'ontop', 'under', 'nextto', 'touching']:
            first_elem = first_elem.capitalize()
            if first_elem.lower() == 'checkgrasping':
                first_elem = 'CheckGrasping'

        if all(isinstance(x, (str, int, float)) for x in pred):
            parts = [first_elem] + [str(x) for x in pred[1:]]
            return "(" + " ".join(parts) + ")"
        else:
            parts = [first_elem]
            for item in pred[1:]:
                if isinstance(item, (list, tuple)):
                    parts.append(format_predicate(item, indent_level))
                else:
                    parts.append(str(item))
            return "(" + " ".join(parts) + ")"
    else:
        return str(pred)


def dict_to_bddl_string(parsed_dict):
    """Serialize a dictionary returned by robosuite_parse_problem as BDDL."""
    lines = []

    # ========== Header ==========
    problem_name = parsed_dict.get("problem_name", "unknown_problem")
    lines.append(f"(define (problem {problem_name})")
    lines.append("  (:domain robosuite)")

    # ========== Language Instruction ==========
    language = parsed_dict.get("language_instruction", [])
    if language:
        if isinstance(language, list):
            lang_str = " ".join(language)
        else:
            lang_str = str(language)
        lines.append(f"  (:language {lang_str})")

    # ========== Regions ==========
    regions = parsed_dict.get("regions", {})
    if regions:
        lines.append("  (:regions")
        for region_full_name, region_data in regions.items():
            # Strip the target prefix from region names when serializing.
            target = region_data.get("target", "")
            if target and "_" in region_full_name:
                clean_name = region_full_name.replace(f"{target}_", "")
            else:
                clean_name = region_full_name

            lines.append(f"    ({clean_name}")

            # Target
            if target:
                lines.append(f"        (:target {target})")

            # Ranges
            if region_data.get("ranges"):
                lines.append("        (:ranges (")
                for r in region_data["ranges"]:
                    lines.append(f"            ({r[0]} {r[1]} {r[2]} {r[3]})")
                lines.append("          )")
                lines.append("        )")

            # Yaw Rotation
            if region_data.get("yaw_rotation") and region_data["yaw_rotation"] != [0, 0]:
                yaw = region_data["yaw_rotation"]
                lines.append("        (:yaw_rotation (")
                lines.append(f"            ({yaw[0]} {yaw[1]})")
                lines.append("          )")
                lines.append("        )")

            # RGBA
            if region_data.get("rgba") and region_data["rgba"] != [0, 0, 1, 0]:
                rgba = region_data["rgba"]
                lines.append(f"        (:rgba ({rgba[0]} {rgba[1]} {rgba[2]} {rgba[3]}))")

            lines.append("    )")
        lines.append("  )")
        lines.append("")

    # ========== Fixtures ==========
    fixtures = parsed_dict.get("fixtures", {})
    if fixtures:
        lines.append("  (:fixtures")
        for fixture_type, fixture_list in fixtures.items():
            for fixture_name in fixture_list:
                lines.append(f"    {fixture_name} - {fixture_type}")
        lines.append("  )")
        lines.append("")

    # ========== Objects ==========
    objects = parsed_dict.get("objects", {})
    if objects:
        lines.append("  (:objects")
        for obj_type, obj_list in objects.items():
            obj_names = " ".join(obj_list)
            lines.append(f"    {obj_names} - {obj_type}")
        lines.append("  )")
        lines.append("")

    # ========== Objects of Interest ==========
    obj_of_interest = parsed_dict.get("obj_of_interest", [])
    if obj_of_interest:
        lines.append("  (:obj_of_interest")
        for obj in obj_of_interest:
            lines.append(f"    {obj}")
        lines.append("  )")
        lines.append("")

    # ========== Initial State ==========
    initial_state = parsed_dict.get("initial_state", [])
    if initial_state:
        lines.append("  (:init")
        for state in initial_state:
            if isinstance(state, (list, tuple)):
                state_str = " ".join(str(s) for s in state)
                lines.append(f"    ({state_str})")
            else:
                lines.append(f"    {state}")
        lines.append("  )")

    # ========== Goal State ==========
    goal_state = parsed_dict.get("goal_state", [])
    if goal_state:
        lines.append("  (:goal")
        # Preserve the existing logical operator instead of nesting another one.
        if len(goal_state) == 1 and isinstance(goal_state[0], list) and len(goal_state[0]) > 0 and goal_state[0][0].lower() in ['and', 'or', 'cum']:
            operator = goal_state[0][0].capitalize()
            sub_predicates = goal_state[0][1:]

            lines.append(f"    ({operator}")
            for pred in sub_predicates:
                formatted_pred = format_predicate(pred)
                lines.append(f"      {formatted_pred}")
            lines.append("    )")
        else:
            lines.append("    (And")
            for goal in goal_state:
                formatted_goal = format_predicate(goal)
                lines.append(f"      {formatted_goal}")
            lines.append("    )")
        lines.append("  )")

    # ========== Cost State ==========
    cost_state = parsed_dict.get("cost_state", [])
    if cost_state:
        lines.append("  (:cost")
        # Preserve the existing cost operator instead of adding another Or.
        if len(cost_state) == 1 and isinstance(cost_state[0], list) and len(cost_state[0]) > 0 and cost_state[0][0].lower() in ['and', 'or', 'cum']:
            operator = cost_state[0][0].capitalize()
            sub_predicates = cost_state[0][1:]

            lines.append(f"    ({operator}")
            for pred in sub_predicates:
                formatted_pred = format_predicate(pred)
                lines.append(f"      {formatted_pred}")
            lines.append("    )")
        else:
            lines.append("    (Or")
            for cost in cost_state:
                formatted_cost = format_predicate(cost)
                lines.append(f"      {formatted_cost}")
            lines.append("    )")
        lines.append("  )")

    # ========== Closing ==========
    lines.append(")")

    return "\n".join(lines)


def save_dict_as_bddl(parsed_dict, output_path):
    """Write a parsed dictionary as BDDL and return the output path."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    bddl_content = dict_to_bddl_string(parsed_dict)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(bddl_content)

    print(f"Saved BDDL file: {output_path}")
    return str(output_path)


def load_bddl_as_dict(bddl_path):
    """Load and parse a BDDL file into a dictionary."""
    if not os.path.exists(bddl_path):
        raise FileNotFoundError(f"BDDL file not found: {bddl_path}")

    parsed_dict = bddl_utils.robosuite_parse_problem(bddl_path)
    print(f"Loaded BDDL file: {bddl_path}")
    return parsed_dict


def test_round_trip(original_bddl_path):
    """Check that BDDL-to-dictionary-to-BDDL conversion preserves key fields."""
    print("=" * 60)
    print("Testing BDDL round-trip conversion...")
    print("=" * 60)

    print(f"\n1. Loading source BDDL: {original_bddl_path}")
    original_dict = load_bddl_as_dict(original_bddl_path)

    print("\n2. Converting to BDDL text...")
    bddl_string = dict_to_bddl_string(original_dict)

    output_path = original_bddl_path.replace('.bddl', '_reconstructed.bddl')
    print(f"\n3. Saving output: {output_path}")
    save_dict_as_bddl(original_dict, output_path)

    print(f"\n4. Reloading and verifying...")
    reconstructed_dict = load_bddl_as_dict(output_path)

    print("\n5. Comparing key fields:")
    keys_to_compare = ['problem_name', 'language_instruction', 'objects',
                      'fixtures', 'obj_of_interest', 'initial_state', 'goal_state']

    all_match = True
    for key in keys_to_compare:
        original = original_dict.get(key)
        reconstructed = reconstructed_dict.get(key)
        match = (original == reconstructed)
        status = "✓" if match else "✗"
        print(f"  {status} {key}: {'match' if match else 'mismatch'}")
        if not match:
            all_match = False

    print("\n" + "=" * 60)
    if all_match:
        print("Round-trip conversion preserved all compared fields")
    else:
        print("Warning: some fields changed during round-trip conversion")
    print("=" * 60)

    return all_match


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Convert between parsed dictionaries and BDDL files")
    parser.add_argument("bddl_file", help="Path to the BDDL file")
    parser.add_argument("--output", "-o", help="Output path (default: append _saved to the source filename)")
    parser.add_argument("--test", action="store_true", help="Test round-trip conversion")

    args = parser.parse_args()

    if args.test:
        test_round_trip(args.bddl_file)
    else:
        parsed_dict = load_bddl_as_dict(args.bddl_file)

        output_path = args.output or args.bddl_file.replace('.bddl', '_saved.bddl')
        save_dict_as_bddl(parsed_dict, output_path)

        print(f"\nConversion completed")
        print(f"Source file: {args.bddl_file}")
        print(f"Output file: {output_path}")

