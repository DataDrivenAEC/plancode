"""Brief conformance: the model delivers the programme written in DESIGN.md."""
import pytest

from conftest import fail


@pytest.mark.rule(id="brief/room-exists-at-area", kind="brief")
def test_room_exists_at_area(model, required_room):
    """Brief conformance (DESIGN.md, section Programme): every programme room exists, as often as its count says
    (storey 'each' = once per storey), with a clear floor area of at least its programme area."""
    name, k, area_m2 = required_room
    spaces = sorted((s for s in model["spaces"] if s.get("programme") == name), key=lambda s: s["id"])
    if len(spaces) < k:
        fail(f"programme room '{name}' #{k} is missing ({len(spaces)} placed)", placed=len(spaces))
    s = spaces[k - 1]
    actual = round(s["w"] * s["d"] / 1e6, 2)
    if actual < area_m2:
        fail(f"'{name}' #{k} ({s['id']}) has {actual} m² < {area_m2} m²", actual_m2=actual, required_m2=area_m2)
