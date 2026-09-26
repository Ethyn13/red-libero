"""Keyboard and mouse reference for Scene Studio."""


def get_help_text() -> str:
    return "Scene Studio keyboard reference\n\nScene: Shift+S save; Shift+I load; Shift+R reset; Shift+E resample.\nModes: Space cycles Physics / Free / Human; Ctrl+Enter enters AI from Physics; Enter starts the run in AI mode.\nMouse: left-click selects a parent object; Alt+left-click selects a part.\n       Right-click toggles a joint; Alt+right-click toggles the clicked part.\n       Drag moves in XY; the wheel adjusts the selected object's height.\nFree edit: Shift+A adds an object; Shift+Delete removes the selected object.\nNumPad translation: 2/8 = X+/-; 6/4 = Y+/-; 5/0 = Z+/-. \nNumPad rotation: 7/9 = yaw+/-; */divide = roll+/-; 1/3 = pitch+/-. \nCalibration: Ctrl+C starts; Ctrl+V shows history; Ctrl+A saves; Ctrl+L lists.\nPolicy/task: Shift+M chooses a model; Shift+T chooses a task.\nHelp: F1 opens the keyboard guide; H prints this reference.\n\nLeave AI mode before changing a model.\n"


def get_short_help_keys() -> list:
    return [
        ("=== MODE ===", ""),
        ("Space", "Cycle Mode"),
        ("Ctrl+Enter", "AI Mode"),
        ("", ""),
        ("=== MOUSE ===", ""),
        ("LClick", "Select Parent"),
        ("Alt+LClick", "Select Part"),
        ("RClick", "Toggle Parent"),
        ("Alt+RClick", "Toggle Part"),
        ("Wheel", "Adjust Height"),
        ("", ""),
        ("=== SCENE ===", ""),
        ("Shift+S", "Save Scene"),
        ("Shift+I", "Load Scene"),
        ("Shift+R", "Reset"),
        ("Shift+E", "Resample"),
        ("", ""),
        ("=== OBJECTS ===", ""),
        ("Shift+A", "Add Object"),
        ("Shift+Del", "Delete Obj"),
        ("", ""),
        ("=== 6-DOF ===", ""),
        ("NumPad", "Pos/Rot"),
        ("2/8", "X-axis"),
        ("4/6", "Y-axis"),
        ("5/0", "Z-axis"),
        ("7/9", "Yaw"),
        ("", ""),
        ("=== OTHER ===", ""),
        ("Shift+J", "Joints Info"),
        ("Shift+M", "Switch Model"),
        ("Shift+T", "Switch Task"),
        ("H", "Help"),
        ("Esc", "Quit"),
    ]
