"""Renders of the model: OpenUSD text layers (stable diffs), a plan SVG the agent can read, IFC export."""
import xml.etree.ElementTree as ET

import pytest

from arch_harness.design import effective_parameters, load_design
from arch_harness.generators.massing import generate
from arch_harness.model import solids
from arch_harness.render.svg import plan_svg
from arch_harness.render.usd import write_usd


@pytest.fixture(scope="module")
def clinic():
    from conftest import EXAMPLES
    d = load_design(EXAMPLES / "clinic" / "DESIGN.md")
    p = effective_parameters(d)
    p.update(door_width=900, corridor_width=1800)
    return generate(d, p)


def test_usd_layers_are_byte_stable(clinic, tmp_path):
    a = write_usd(clinic, tmp_path / "a")
    b = write_usd(clinic, tmp_path / "b")
    names = sorted(p.relative_to(tmp_path / "a").as_posix() for p in a)
    assert names == ["building.usda", "storeys/L0.usda", "storeys/L1.usda"]
    for pa in a:
        pb = tmp_path / "b" / pa.relative_to(tmp_path / "a")
        assert pa.read_bytes() == pb.read_bytes()


def test_usd_stage_composes_every_element_in_mm(clinic, tmp_path):
    from pxr import Usd, UsdGeom
    write_usd(clinic, tmp_path)
    stage = Usd.Stage.Open(str(tmp_path / "building.usda"))
    assert UsdGeom.GetStageMetersPerUnit(stage) == pytest.approx(0.001)
    assert UsdGeom.GetStageUpAxis(stage) == UsdGeom.Tokens.z
    ids = {p.GetCustomDataByKey("ah:id") for p in stage.Traverse() if p.GetCustomDataByKey("ah:id")}
    assert ids == {s["id"] for s in solids(clinic)}
    wall = next(s for s in solids(clinic) if s["kind"] == "wall")
    prim = next(p for p in stage.Traverse() if p.GetCustomDataByKey("ah:id") == wall["id"])
    rng = UsdGeom.Boundable(prim).ComputeWorldBound(Usd.TimeCode.Default(), "default").ComputeAlignedRange()
    assert list(rng.GetMin()) == pytest.approx(wall["min"]) and list(rng.GetMax()) == pytest.approx(wall["max"])


def test_plan_svg_names_every_space_and_door(clinic):
    svg = plan_svg(clinic, "L0")
    root = ET.fromstring(svg)
    ids = {el.get("data-id") for el in root.iter() if el.get("data-id")}
    on_l0 = {e["id"] for e in clinic["spaces"] + clinic["doors"] if e["storey"] == "L0"}
    assert on_l0 <= ids
    assert "Reception and waiting" in svg and "m²" in svg


def test_ifc_export_structure_and_units(clinic, tmp_path):
    import ifcopenshell
    import ifcopenshell.geom
    import ifcopenshell.util.element as eu
    from arch_harness.render.ifc import export_ifc
    path = export_ifc(clinic, tmp_path / "model.ifc")
    f = ifcopenshell.open(str(path))
    storeys = f.by_type("IfcBuildingStorey")
    assert [s.Name for s in storeys] == ["Storey 0", "Storey 1"]
    space = f.by_type("IfcSpace")[0]
    assert space.Decomposes[0].RelatingObject.is_a("IfcBuildingStorey")      # spaces are aggregated
    wall = f.by_type("IfcWall")[0]
    assert wall.ContainedInStructure[0].RelatingStructure.is_a("IfcBuildingStorey")  # elements are contained
    door = f.by_type("IfcDoor")[0]
    assert door.FillsVoids and door.OverallWidth == 900
    assert len(f.by_type("IfcDoor")) == len(clinic["doors"])
    assert eu.get_psets(f.by_type("IfcWall")[0])["Pset_WallCommon"]["IsExternal"] in (True, False)
    # ifcopenshell geometry comes back in metres: convert at the boundary
    model_wall = next(w for w in clinic["walls"] if w["id"] == wall.Name)
    settings = ifcopenshell.geom.settings()
    settings.set("disable-opening-subtractions", True)
    shape = ifcopenshell.geom.create_shape(settings, wall)
    import ifcopenshell.util.shape as us
    mn, mx = us.get_bbox(us.get_vertices(shape.geometry))
    box = next(s for s in solids(clinic) if s["id"] == wall.Name)
    assert [round(v * 1000) for v in (mx - mn)] == [b - a for a, b in zip(box["min"], box["max"])]
    assert model_wall["height"] == round((mx - mn)[2] * 1000)
