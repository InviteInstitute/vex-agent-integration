TASK_DESCRIPTIONS = {
    "default": "Help the student debug and improve their VEXcode VR program.",
    "GO-Mars": "The student is working in VEXcode VR at https://vr.vex.com/ in the GO Competition playground called Mars Math Expedition. In Stage 4, all tasks are available, each completed task is worth 1 point, and the student should first aim to score at least 5 points and then keep scoring more if possible within the one-minute match. The robot can drive forward and backward, turn, raise and lower its arm, and use an eye sensor to detect objects and object colors. Relevant blocks include Drive for, Turn for, Spin arm motor, Spin arm motor to position, and Wait until with the eye sensor. Common tasks include removing a sample from a crater, moving a sample to the Lab, placing a sample on top of the Lab, tilting the Solar Panel down, clearing the Landing Site, lifting the Rocket Ship upright, removing Fuel Cells from their cradles, and moving Fuel Cells to the Rocket Ship or Landing Site.",
}


def resolve_task_description(playground: str) -> str:
    return TASK_DESCRIPTIONS.get(playground, TASK_DESCRIPTIONS["default"])
