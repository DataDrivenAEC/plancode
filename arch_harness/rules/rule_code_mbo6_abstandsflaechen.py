"""Code rule from the Musterbauordnung (MBO), § 6 Abstandsflächen."""
import pytest

from conftest import fail


@pytest.mark.rule(id="MBO/6(5)/abstandsflaeche-on-plot", kind="code")
def test_abstandsflaeche_on_plot(model, side):
    """MBO (Fassung November 2002, zuletzt geändert durch Beschluss der Bauministerkonferenz vom 23./24.11.2023),
    § 6 Abs. 5 Satz 1: 'Die Tiefe der Abstandsflächen beträgt 0,4 H, mindestens 3 m.'; § 6 Abs. 2 Satz 1: the
    Abstandsflächen must lie on the plot itself. Simplification: H is the building height in the model (no roof
    pitch, no parapet); the relief onto public land (§ 6 Abs. 2 Satz 2) and the Länder variants are not applied."""
    b, site = model["building"], model["site"]
    required = max(3000, int(round(0.4 * b["height"])))
    distance = {"west": b["x"], "south": b["y"],
                "east": site["width"] - b["x"] - b["w"], "north": site["depth"] - b["y"] - b["d"]}[side]
    if distance < required:
        fail(f"{side} wall is {distance} mm from the plot boundary < Abstandsfläche {required} mm",
             actual=distance, required=required, side=side)
