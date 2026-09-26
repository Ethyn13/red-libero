"""
BDDL Input Module

This module provides functionality to parse BDDL (Behavior Domain Definition Language) 
descriptions from either string content or file paths, and convert them to dictionary
format using the LIBERO library's robosuite_parse_problem function.

Usage:
    from bddl_input import parse_bddl
    
    # Parse from file
    result = parse_bddl(file_path="path/to/file.bddl")
    
    # Parse from string
    result = parse_bddl(bddl_string="(:domain robosuite ...)")
"""

import os
import tempfile
from typing import Union, Dict, Any

from libero.libero.envs.bddl_utils import robosuite_parse_problem


def parse_bddl(bddl_string: str = None, file_path: str = None) -> Dict[str, Any]:
    """
    Parse BDDL description from string or file and convert to dictionary format.
    
    This function accepts either a BDDL description as a string or a path to a BDDL file,
    and uses the LIBERO library's robosuite_parse_problem function to convert it to a
    dictionary containing the parsed problem information.
    
    Args:
        bddl_string (str, optional): BDDL description as a string. Defaults to None.
        file_path (str, optional): Path to BDDL file. Defaults to None.
        
    Returns:
        Dict[str, Any]: Dictionary containing the parsed BDDL problem information.
        
    Raises:
        ValueError: If neither bddl_string nor file_path is provided, or if both are provided.
        FileNotFoundError: If the specified file_path does not exist.
        Exception: If there's an error parsing the BDDL content.
        
    """
    
    # Validate input parameters
    if bddl_string is None and file_path is None:
        raise ValueError("Either bddl_string or file_path must be provided")
    
    if bddl_string is not None and file_path is not None:
        raise ValueError("Cannot provide both bddl_string and file_path. Please choose one.")
    
    try:
        if bddl_string is not None:
            # Parse from string - create temporary file
            return _parse_from_string(bddl_string)
        else:
            # Parse from file
            return _parse_from_file(file_path)
            
    except Exception as e:
        raise Exception(f"Error parsing BDDL: {str(e)}")


def _parse_from_string(bddl_string: str) -> Dict[str, Any]:
    """
    Helper function to parse BDDL from string content.
    
    Args:
        bddl_string (str): BDDL description as a string.
        
    Returns:
        Dict[str, Any]: Dictionary containing the parsed BDDL problem information.
    """
    # Create a temporary file with the BDDL content
    with tempfile.NamedTemporaryFile(mode='w', suffix='.bddl', delete=False) as temp_file:
        temp_file.write(bddl_string)
        temp_file_path = temp_file.name
    
    try:
        # Parse using the robosuite_parse_problem function
        result = robosuite_parse_problem(temp_file_path)
        return result
    finally:
        # Clean up the temporary file
        try:
            os.unlink(temp_file_path)
        except OSError:
            # Ignore errors if file couldn't be deleted
            pass


def _parse_from_file(file_path: str) -> Dict[str, Any]:
    """
    Helper function to parse BDDL from file path.
    
    Args:
        file_path (str): Path to BDDL file.
        
    Returns:
        Dict[str, Any]: Dictionary containing the parsed BDDL problem information.
    """
    # Check if file exists
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"BDDL file not found: {file_path}")
    
    # Check if it's a file (not a directory)
    if not os.path.isfile(file_path):
        raise ValueError(f"Path is not a file: {file_path}")
    
    # Parse using the robosuite_parse_problem function
    result = robosuite_parse_problem(file_path)
    return result


def get_bddl_info(bddl_string: str = None, file_path: str = None) -> Dict[str, Any]:
    """
    Get basic information about a BDDL problem (lightweight version).
    
    This function returns basic problem information without full parsing,
    which can be useful for quick inspection or validation.
    
    Args:
        bddl_string (str, optional): BDDL description as a string. Defaults to None.
        file_path (str, optional): Path to BDDL file. Defaults to None.
        
    Returns:
        Dict[str, Any]: Dictionary containing basic problem information.
    """
    from libero.libero.envs.bddl_utils import get_problem_info
    
    # Validate input parameters
    if bddl_string is None and file_path is None:
        raise ValueError("Either bddl_string or file_path must be provided")
    
    if bddl_string is not None and file_path is not None:
        raise ValueError("Cannot provide both bddl_string and file_path. Please choose one.")
    
    try:
        if bddl_string is not None:
            # Create temporary file for string input
            with tempfile.NamedTemporaryFile(mode='w', suffix='.bddl', delete=False) as temp_file:
                temp_file.write(bddl_string)
                temp_file_path = temp_file.name
            
            try:
                result = get_problem_info(temp_file_path)
                return result
            finally:
                # Clean up the temporary file
                try:
                    os.unlink(temp_file_path)
                except OSError:
                    pass
        else:
            # Parse from file
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"BDDL file not found: {file_path}")
            
            result = get_problem_info(file_path)
            return result
            
    except Exception as e:
        raise Exception(f"Error getting BDDL info: {str(e)}")


# Example usage and testing functions
if __name__ == "__main__":
    # Example BDDL content for testing
    example_bddl = """
    (define
        (problem test_task)
        (:domain robosuite)
        (:objects
            object1 object2 - object
        )
        (:init
            (ontop object1 table)
            (ontop object2 table)
        )
        (:goal
            (and
                (nextto object1 object2)
            )
        )
        (:language
            "Move object1 next to object2"
        )
    )
    """
    
    print("Testing BDDL parsing functionality...")
    
    try:
        # Test parsing from string
        print("\n1. Testing parse from string:")
        result = parse_bddl(bddl_string=example_bddl)
        print(f"Problem name: {result.get('problem_name', 'N/A')}")
        print(f"Language instruction: {' '.join(result.get('language_instruction', []))}")
        print(f"Objects: {result.get('objects', {})}")
        
        # Test getting basic info
        print("\n2. Testing get basic info:")
        basic_info = get_bddl_info(bddl_string=example_bddl)
        print(f"Basic info: {basic_info}")
        
        print("\nAll tests completed successfully!")
        
    except Exception as e:
        print(f"Error during testing: {e}")
