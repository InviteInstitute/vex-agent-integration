"""humanize: readable program listing with parameters. Vendored from the
self-check in lm-dashboard/app/runs/humanize.py (no dedicated test file there)."""
from vex_agent.triggers.humanize import humanize_workspace, humanize_text


DEMO = (
    '<xml>'
    '<block type="pg_events_when_started"><next>'
    '  <block type="pg_drivetrain_drive_for">'
    '    <field name="DIRECTION">fwd</field><field name="UNITS">mm</field>'
    '    <field name="anddontwait_mutator">false</field>'
    '    <value name="AMOUNT"><shadow type="math_number"><field name="NUM">200</field></shadow></value>'
    '  <next>'
    '    <block type="pg_control_if_then_else">'
    '      <value name="CONDITION"><block type="pg_operator_not"><value name="OPERAND">'
    '        <block type="pg_operator_and_or"><field name="CHECK">and</field>'
    '          <value name="OPERAND1"><block type="pg_operator_comparison"><field name="COMPARISON">&lt;</field>'
    '            <value name="NUM1"><block type="pg_sensing_distance_distance"><field name="DISTANCE">frontdistance</field></block></value>'
    '            <value name="NUM2"><shadow type="math_number"><field name="NUM">200</field></shadow></value></block></value>'
    '          <value name="OPERAND2"><block type="pg_sensing_optical_near_object"><field name="OPTICAL">fronteye</field></block></value>'
    '        </block></value></block></value>'
    '      <statement name="SUBSTACK"><block type="pg_drivetrain_drive"><field name="DIRECTION">fwd</field></block></statement>'
    '      <statement name="SUBSTACK2"><block type="pg_drivetrain_stop_driving"/></statement>'
    '    </block></next></block>'
    '</next></block></xml>'
)


def test_empty_and_unparseable_return_empty():
    assert humanize_workspace("") == []
    assert humanize_workspace("<xml><unclosed>") == []


def test_value_slot_numbers_are_preserved():
    # the key feature: drive distance "200" lives in a <value> shadow the
    # edit-distance AST drops, but humanize keeps it.
    lines = humanize_workspace(DEMO)
    assert any("200" in ln for ln in lines)


def test_if_else_branch_is_labeled():
    lines = humanize_workspace(DEMO)
    assert any("else:" == ln.strip() for ln in lines)


def test_nested_condition_is_rendered_infix():
    lines = humanize_workspace(DEMO)
    # not ( ... and ... < 200 )
    assert any("not (" in ln and "and" in ln and "< 200" in ln for ln in lines)


def test_mutator_fields_are_hidden():
    # anddontwait_mutator is Blockly plumbing; it must not appear in the output
    lines = humanize_workspace(DEMO)
    assert all("anddontwait_mutator" not in ln for ln in lines)


def test_humanize_text_joins_lines():
    text = humanize_text(DEMO)
    assert isinstance(text, str)
    assert "200" in text
