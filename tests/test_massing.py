"""The massing generator: footprint from the site, storeys from the programme, deterministic."""
import json

from arch_harness.checks import run_rules
from arch_harness.design import effective_parameters, load_design
from arch_harness.generators.massing import generate
from arch_harness.model import dumps_model, validate_model


def by_kind(report, kind):
    return [r for r in report["results"] if r["kind"] == kind and r["outcome"] == "failed"]


def test_generation_is_deterministic(clinic_design_path):
    d = load_design(clinic_design_path)
    p = effective_parameters(d)
    assert dumps_model(generate(d, p)) == dumps_model(generate(d, p))


def test_clinic_massing_respects_the_site_and_needs_two_storeys(clinic_design_path, write_model):
    d = load_design(clinic_design_path)
    m = generate(d, effective_parameters(d))
    validate_model(m)
    assert [s["id"] for s in m["storeys"]] == ["L0", "L1"]
    assert m["building"]["height"] == 6400
    report = run_rules(write_model(m))
    assert by_kind(report, "geometry") == []
    assert by_kind(report, "brief") == []
    assert [r for r in by_kind(report, "code") if r["rule"].startswith("MBO")] == []


def test_first_sketch_parameters_fail_the_code_rules(clinic_design_path, write_model):
    d = load_design(clinic_design_path)
    report = run_rules(write_model(generate(d, effective_parameters(d))))
    rules = {r["rule"] for r in by_kind(report, "code")}
    assert rules == {"DIN18040-1/4.3.3.2/door-clear-width", "DIN18040-1/4.3.2/corridor-width"}


def test_a_small_programme_fits_one_storey(clinic_design_path):
    d = load_design(clinic_design_path)
    d["programme"] = [{"name": "Office", "area_m2": 15.0, "count": 4, "storey": "any"}]
    m = generate(d, effective_parameters(d))
    assert len(m["storeys"]) == 1


def test_the_core_stacks_on_every_storey(clinic_design_path):
    d = load_design(clinic_design_path)
    m = generate(d, effective_parameters(d))
    cores = [s for s in m["spaces"] if s["programme"] == "Stair and lift core"]
    assert len(cores) == 2
    assert {(s["x"], s["y"], s["w"], s["d"]) for s in cores} == {(cores[0]["x"], cores[0]["y"], cores[0]["w"], cores[0]["d"])}


def test_fixed_storey_rooms_stay_on_their_storey(clinic_design_path):
    d = load_design(clinic_design_path)
    m = generate(d, effective_parameters(d))
    assert {s["storey"] for s in m["spaces"] if s["programme"] == "Treatment room"} == {"L0"}


def test_tight_site_reports_why_it_does_not_fit(tight_design_path):
    d = load_design(tight_design_path)
    m = generate(d, effective_parameters(d))
    assert any("buildable depth" in n for n in m["notes"])
    assert [s for s in m["spaces"] if s["use"] == "room"] == []


def test_model_json_is_canonical(clinic_design_path):
    d = load_design(clinic_design_path)
    text = dumps_model(generate(d, effective_parameters(d)))
    assert text == json.dumps(json.loads(text), sort_keys=True, indent=1, ensure_ascii=False) + "\n"
