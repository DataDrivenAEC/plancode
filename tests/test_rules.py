"""The rules are pytest tests run against a model; these tests prove each rule fails when it should."""
import pytest

from arch_harness.checks import run_rules


def failures(report, rule=None):
    return [r for r in report["results"] if r["outcome"] == "failed" and (rule is None or r["rule"] == rule)]


def test_tiny_model_passes_all_three_kinds(model, write_model):
    report = run_rules(write_model(model))
    assert failures(report) == []
    assert report["passed"] is True
    for kind in ("code", "geometry", "brief"):
        assert report["by_kind"][kind]["failed"] == 0
        assert report["by_kind"][kind]["passed"] > 0


def test_every_rule_cites_a_source(model, write_model):
    report = run_rules(write_model(model))
    for r in report["results"]:
        assert r["source"], r["rule"]
        assert r["kind"] in ("code", "geometry", "brief")


def test_door_narrower_than_90_cm_fails_with_its_minimum(model, write_model):
    model["doors"][0]["width"] = 850
    report = run_rules(write_model(model))
    [f] = failures(report, "DIN18040-1/4.3.3.2/door-clear-width")
    assert f["element"] == "L0-D01" and f["kind"] == "code"
    assert f["data"] == {"actual": 850, "required": 900}


def test_door_lower_than_205_cm_fails(model, write_model):
    model["doors"][1]["height"] = 2000
    report = run_rules(write_model(model))
    [f] = failures(report, "DIN18040-1/4.3.3.2/door-clear-height")
    assert f["element"] == "L0-D02" and f["data"]["required"] == 2050


def test_corridor_narrower_than_150_cm_fails(model, write_model):
    model["spaces"][2]["d"] = 1300
    report = run_rules(write_model(model))
    [f] = failures(report, "DIN18040-1/4.3.2/corridor-width")
    assert f["element"] == "L0-C" and f["data"]["required"] == 1500


def test_corridor_longer_than_15_m_needs_a_passing_area(model, write_model):
    model["spaces"][2]["w"] = 16000
    report = run_rules(write_model(model))
    [f] = failures(report, "DIN18040-1/4.3.2/corridor-width")
    assert f["data"]["required"] == 1800


def test_building_inside_its_abstandsflaeche_fails(model, write_model):
    model["building"]["x"] = 2000  # 0.4 H = 1.2 m, but at least 3 m
    report = run_rules(write_model(model))
    [f] = failures(report, "MBO/6(5)/abstandsflaeche-on-plot")
    assert f["data"]["required"] == 3000 and f["data"]["side"] == "west"


def test_door_wider_than_its_wall_fails_geometry(model, write_model):
    model["doors"][0]["offset"] = 3500
    report = run_rules(write_model(model))
    [f] = failures(report, "geometry/opening-fits-wall")
    assert f["element"] == "L0-D01" and f["kind"] == "geometry"


def test_door_taller_than_its_wall_fails_geometry(model, write_model):
    model["walls"][0]["height"] = 2000
    report = run_rules(write_model(model))
    assert [f["element"] for f in failures(report, "geometry/opening-fits-wall")] == ["L0-D01"]


def test_overlapping_rooms_fail_geometry(model, write_model):
    model["spaces"][1]["x"] = 3000
    report = run_rules(write_model(model))
    [f] = failures(report, "geometry/rooms-do-not-overlap")
    assert f["element"] == "L0-S01|L0-S02"


def test_missing_programme_room_fails_brief(model, write_model):
    del model["spaces"][1]
    model["doors"].pop()
    model["walls"].pop()
    report = run_rules(write_model(model))
    [f] = failures(report, "brief/room-exists-at-area")
    assert f["element"] == "Room B#1" and f["kind"] == "brief"


def test_room_below_its_programme_area_fails_brief(model, write_model):
    model["spaces"][0]["w"] = 3000  # 15 m² < 20 m²
    report = run_rules(write_model(model))
    [f] = failures(report, "brief/room-exists-at-area")
    assert f["element"] == "Room A#1"
    assert f["data"] == {"actual_m2": 15.0, "required_m2": 20.0}


def test_a_kind_with_no_checks_is_not_reported_as_passed(model, write_model):
    model["spaces"] = [s for s in model["spaces"] if s["use"] == "corridor"]
    model["programme"] = []
    model["doors"], model["walls"] = [], []
    report = run_rules(write_model(model))
    assert report["by_kind"]["brief"]["passed"] == 0
    assert "brief" in report["unconfirmed_kinds"]
    assert report["passed"] is False


def test_a_rule_with_nothing_to_check_is_unconfirmed_not_passed(model, write_model):
    model["spaces"] = [s for s in model["spaces"] if s["use"] != "corridor"]  # the corridor rule has no element
    report = run_rules(write_model(model))
    assert report["by_kind"]["code"]["passed"] > 0  # the kind still passes on its other rules
    assert [u["rule"] for u in report["unconfirmed_rules"]] == ["DIN18040-1/4.3.2/corridor-width"]
    assert report["passed"] is False


def test_abstandsflaeche_rounds_up_like_the_generator(model, write_model):
    model["building"]["height"] = 9993  # 0.4 H = 3997.2 mm: 3997 mm is short
    model["building"]["x"] = 3997
    [f] = failures(run_rules(write_model(model)), "MBO/6(5)/abstandsflaeche-on-plot")
    assert f["data"]["required"] == 3998
