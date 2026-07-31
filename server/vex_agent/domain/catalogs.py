"""Playground-specific LLM grounding: task description + available block list.
Keyed by playground id; falls back to "default". Merged from the former
task_catalog.py + block_catalog.py (same shape, same two consumers)."""

TASK_DESCRIPTIONS = {
    "default": "Help the student debug and improve their VEXcode VR program.",
    "GO-Mars": "The student is working in VEXcode VR at https://vr.vex.com/ in the GO Competition playground called Mars Math Expedition. In Stage 4, all tasks are available, each completed task is worth 1 point, and the student should first aim to score at least 5 points and then keep scoring more if possible within the one-minute match. The robot can drive forward and backward, turn, raise and lower its arm, and use an eye sensor to detect objects and object colors. Relevant blocks include Drive for, Turn for, Spin arm motor, Spin arm motor to position, and Wait until with the eye sensor. Common tasks include removing a sample from a crater, moving a sample to the Lab, placing a sample on top of the Lab, tilting the Solar Panel down, clearing the Landing Site, lifting the Rocket Ship upright, removing Fuel Cells from their cradles, and moving Fuel Cells to the Rocket Ship or Landing Site.",
}


def resolve_task_description(playground: str) -> str:
    return TASK_DESCRIPTIONS.get(playground, TASK_DESCRIPTIONS["default"])


AVAILABLE_BLOCKS = {
    "default": [],
    "GO-Mars": [
        "drive [forward/reverse]",
        "drive [forward/reverse] until [object/crash]",
        "drive [forward/reverse] for [number] [mm/inches]",
        "turn [right/left]",
        "turn [right/left] for [number] degrees",
        "turn to heading [number] degrees",
        "turn to rotation [number] degrees",
        "stop driving",
        "set drive velocity to [number] [%]",
        "set turn velocity to [number] [%]",
        "set drive heading to [number] degrees",
        "set drive rotation to [number] degrees",
        "set drive timeout to [number] seconds",
        "drive is done?",
        "drive is moving?",
        "drive heading in degrees",
        "drive rotation in degrees",
        "drive velocity in [%]",
        "spin [ArmMotor] [up/down]",
        "spin [ArmMotor] [up/down] for [number] [degrees/turns]",
        "spin [ArmMotor] to position [number] [degrees/turns]",
        "stop [ArmMotor]",
        "set [ArmMotor] velocity to [number] [%]",
        "set [ArmMotor] timeout to [number] seconds",
        "[ArmMotor] position in [degrees/turns]",
        "set [ArmMotor] position to [number] [degrees/turns]",
        "[ArmMotor] is done?",
        "[ArmMotor] is spinning?",
        "[ArmMotor] velocity in [%]",
        "[FrontEye] found an object?",
        "[FrontEye] detects [red/green/blue/orange/purple]?",
        "[FrontEye] brightness in %",
        "[FrontEye] hue in degrees",
        "detected crash?",
        "print [text/value]",
        "set cursor to next row",
        "clear all rows",
        "set print precision to [1/0.1/0.01/0.001/All Digits]",
        "wait [number] seconds",
        "wait until [condition]",
        "repeat [number]",
        "forever",
        "repeat until [condition]",
        "while [condition]",
        "if [condition] then",
        "if [condition] then else",
        "if [condition] then / else if [condition] then / else",
        "break",
        "stop project",
        "reset timer",
        "timer in seconds",
        "when timer > [number] seconds",
        "when started",
        "when I receive [my_event]",
        "broadcast [my_event]",
        "broadcast [my_event] and wait",
        "[a] [+] [b]",
        "[a] [=] [b]",
        "[condition] [and] [condition]",
        "not [condition]",
        "[a] [<] [b] [<] [c]",
        "pick random [a] to [b]",
        "round [number] to [number] decimal places",
        "[abs] of [number]",
        "atan2 of x: [number] y: [number]",
        "remainder of [a] / [b]",
        "join [text] [text]",
        "letter [number] of [text]",
        "length of [text]",
        "[text] contains [text]?",
        "convert [value] to [text]",
        "[myVariable]",
        "set [myVariable] to [number]",
        "change [myVariable] by [number]",
        "comment",
    ],
}


def resolve_available_blocks(playground: str) -> list[str]:
    return AVAILABLE_BLOCKS.get(playground, AVAILABLE_BLOCKS["default"])
