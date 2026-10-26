"""The loop: generate -> check -> revise -> repeat, bounded, a record per round, honest when it cannot converge."""
import json

from arch_harness.design import effective_parameters, load_design
from arch_harness.loop import run_loop
from arch_harness.revise import propose_revisions


def test_parameter_fixes_go_to_the_code_minimum_never_below():
    report = {"results": [
        {"rule": "DIN18040-1/4.3.3.2/door-clear-width", "outcome": "failed", "element": "L0-D01",
         "data": {"actual": 850, "required": 900}},
        {"rule": "DIN18040-1/4.3.2/corridor-width", "outcome": "failed", "element": "L0-C",
         "data": {"actual": 1300, "required": 1800}},
        {"rule": "geometry/opening-fits-wall", "outcome": "failed", "element": "L0-D02",
         "data": {"wall_height": 2000, "needed": 2050}},
    ]}
    params = {"door_width": 850, "corridor_width": 1300, "storey_height": 2000}
    revs = {r["param"]: r for r in propose_revisions(report, params)}
    assert revs["door_width"]["to"] == 900
    assert revs["corridor_width"]["to"] == 1800
    assert revs["storey_height"]["to"] == 2100  # raise the wall, never shrink the door
    assert "door_height" not in revs


def test_layout_failures_have_no_deterministic_fix():
    report = {"results": [{"rule": "brief/room-exists-at-area", "outcome": "failed", "element": "Office#1",
                           "data": {"placed": 0}}]}
    assert propose_revisions(report, {}) == []


def test_clinic_converges_and_records_every_round(clinic_design_path, tmp_path):
    d = load_design(clinic_design_path)
    result = run_loop(d, effective_parameters(d), tmp_path, max_rounds=5)
    assert result["converged"] is True
    assert len(result["rounds"]) == 2
    first, last = result["rounds"]
    assert first["passed"] is False and first["by_kind"]["code"]["failed"] > 0
    assert {r["param"]: r["to"] for r in first["revisions"]} == {"door_width": 900, "corridor_width": 1800}
    assert last["passed"] is True
    for kind in ("code", "geometry", "brief"):
        assert last["by_kind"][kind]["failed"] == 0 and last["by_kind"][kind]["passed"] > 0
    recorded = json.loads((tmp_path / "rounds" / "round-01.json").read_text())
    assert recorded["revisions"] == first["revisions"]
    assert (tmp_path / "model.json").exists()


def test_tight_site_stops_and_says_why(tight_design_path, tmp_path):
    d = load_design(tight_design_path)
    result = run_loop(d, effective_parameters(d), tmp_path, max_rounds=5)
    assert result["converged"] is False
    assert len(result["rounds"]) == 1
    assert "buildable depth" in result["reason"]
    assert "brief/room-exists-at-area" in result["reason"]


def test_max_rounds_bounds_the_loop(clinic_design_path, tmp_path):
    d = load_design(clinic_design_path)
    result = run_loop(d, effective_parameters(d), tmp_path, max_rounds=1)
    assert result["converged"] is False
    assert "1 round" in result["reason"]


def test_rounds_continue_after_the_ones_already_recorded(clinic_design_path, tmp_path):
    """The MCP run_loop starts in a project whose hooks already wrote round-01: it must not overwrite it."""
    d = load_design(clinic_design_path)
    rounds = tmp_path / "rounds"
    rounds.mkdir()
    (rounds / "round-01.json").write_text('{"round": 1, "kept": true}\n')
    result = run_loop(d, effective_parameters(d), tmp_path, max_rounds=5)
    assert json.loads((rounds / "round-01.json").read_text()) == {"round": 1, "kept": True}
    assert [r["round"] for r in result["rounds"]] == [2, 3]
    assert sorted(p.name for p in rounds.glob("*.json")) == ["round-01.json", "round-02.json", "round-03.json"]
