"""Identity-switch detection, vendored from lm-dashboard/app/pipeline/switches.py.

Pure: decides when a tracked student's identity "switched". Two kinds:
  * casing -- same handle arrives spelled differently (cobra3 -> Cobra3).
  * class  -- same handle turns up under a different classCode.
"""


def detect_switches(prev_id, prev_class, curr_id, curr_class):
    """Return the switches this event represents for one tracked student.

    Args, all strings (or None/"" when there's no prior value yet):
        prev_id     last-seen studentID casing   (e.g. "cobra3")
        prev_class  last-seen classCode          (e.g. "FPFVDH")
        curr_id     this event's studentID casing (e.g. "Cobra3")
        curr_class  this event's classCode        (e.g. "AFURRR")

    Returns a list of (kind, from_value, to_value) tuples, casing before class.
    Both can fire from one event. Returns [] when nothing switched; a missing
    prior value (None or "") is never a switch.
    """
    switches = []
    if prev_id and curr_id and prev_id != curr_id and prev_id.lower() == curr_id.lower():
        switches.append(("casing", prev_id, curr_id))
    if prev_class and curr_class and prev_class != curr_class:
        switches.append(("class", prev_class, curr_class))
    return switches
