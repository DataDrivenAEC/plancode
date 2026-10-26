"""Code rule from DIN 18040-1:2010-10, corridors and other circulation areas."""
import pytest

from conftest import fail


@pytest.mark.rule(id="DIN18040-1/4.3.2/corridor-width", kind="code")
def test_corridor_width(corridor):
    """DIN 18040-1:2010-10, 4.3.2 Flure und sonstige Verkehrsflächen: nutzbare Breite mindestens 150 cm, and after
    at most 15 m of corridor length an area of at least 180 cm × 180 cm for passing. Public text: Bayerisches
    Staatsministerium des Innern, für Bau und Verkehr, 'Planungsgrundlagen des barrierefreien Bauens' (2015), p. 10.
    Not applied: the 120 cm relief (≤ 6 m length, no change of direction, a turning possibility before and after),
    because the model cannot confirm the turning possibility. The model has no passing areas, so a corridor longer
    than 15 m must be 180 cm wide along its length."""
    width, length = sorted((corridor["w"], corridor["d"]))
    required = 1800 if length > 15000 else 1500
    if width < required:
        why = "longer than 15 m without a 180 × 180 cm passing area" if required == 1800 else "below 150 cm"
        fail(f"corridor {corridor['id']} clear width {width} mm < {required} mm ({why})",
             actual=width, required=required, length=length)
