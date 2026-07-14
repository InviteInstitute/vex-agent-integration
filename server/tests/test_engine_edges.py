"""Edge-case coverage for the vendored engine: distance cache/multi-root/field
changes, workspace-XML extraction variants, and JSON-string event content."""
from src.triggers.distance import compute_edit_distance, cached_edit_distance, clear_cache
from src.triggers.ast_builder import xml_to_block_ast, extract_workspace_xml
from src.triggers.run_sequence import compute_run_edit_distances

XMLNS = 'xmlns="https://developers.google.com/blockly/xml"'
EMPTY = f"<xml {XMLNS}></xml>"


def test_distance_cache_hit_and_clear():
    clear_cache()
    a, b = xml_to_block_ast("<x/>"), xml_to_block_ast(EMPTY)
    first = cached_edit_distance("<x/>", EMPTY, a, b)
    second = cached_edit_distance("<x/>", EMPTY, a, b)  # served from cache
    assert first == second
    clear_cache()


def test_multi_root_and_empty_distance():
    two_roots = xml_to_block_ast(
        f'<xml {XMLNS}><block type="a" id="1"></block><block type="b" id="2"></block></xml>'
    )
    assert len(two_roots["roots"]) == 2
    assert compute_edit_distance(two_roots, xml_to_block_ast(EMPTY)) > 0


def test_field_only_change_costs():
    a = xml_to_block_ast(f'<xml {XMLNS}><block type="t" id="1"><field name="N">1</field></block></xml>')
    b = xml_to_block_ast(f'<xml {XMLNS}><block type="t" id="1"><field name="N">2</field></block></xml>')
    assert compute_edit_distance(a, b) > 0


def test_extract_workspace_xml_variants():
    assert extract_workspace_xml({"project": {"workspace": "<w/>"}}) == "<w/>"
    assert extract_workspace_xml({"project": '{"workspace":"<w/>"}'}) == "<w/>"
    assert extract_workspace_xml({"project": "not-json"}) == ""
    assert extract_workspace_xml({"project": 123}) == ""
    assert extract_workspace_xml("not-a-dict") == ""
    assert extract_workspace_xml({"project": {}}) == ""


def test_keep_shadow_blocks():
    ast = xml_to_block_ast(f'<xml {XMLNS}><shadow type="s" id="1"></shadow></xml>', keep_shadow=True)
    assert "1" in ast["nodes"]


def test_run_sequence_accepts_json_string_content():
    content = '{"project":{"workspace":"<x/>"},"playground":"P"}'
    events = [
        {"event_type": "runProject", "content": content, "ts": 1},
        {"event_type": "runProject", "content": content, "ts": 2},
    ]
    runs = compute_run_edit_distances(events)["runs"]
    assert runs[0]["edit_distance"] is None
    assert runs[1]["edit_distance"] == 0
