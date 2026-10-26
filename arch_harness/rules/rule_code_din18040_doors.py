"""Code rules from DIN 18040-1:2010-10 (Barrierefreies Bauen, öffentlich zugängliche Gebäude), doors."""
import pytest

from conftest import fail

SOURCE_URL = ("https://www.bauministerium.bayern.de/assets/stmi/buw/baurechtundtechnik/"
              "planungsgrundlagen_barrierefreies_bauen.pdf")


@pytest.mark.rule(id="DIN18040-1/4.3.3.2/door-clear-width", kind="code")
def test_door_clear_width(door):
    """DIN 18040-1:2010-10, 4.3.3.2 Maßliche Anforderungen, Tabelle 1 Zeile 1: Durchgang, lichte Breite ≥ 90 cm
    (alle Türen). Public text: Bayerisches Staatsministerium des Innern, für Bau und Verkehr, 'DIN 18040-1 und
    DIN 18040-2 – Planungsgrundlagen des barrierefreien Bauens' (2015, reproduced with DIN's permission), p. 10–11.
    The model's door width is its clear width."""
    if door["width"] < 900:
        fail(f"door {door['id']} clear width {door['width']} mm < 900 mm", actual=door["width"], required=900)


@pytest.mark.rule(id="DIN18040-1/4.3.3.2/door-clear-height", kind="code")
def test_door_clear_height(door):
    """DIN 18040-1:2010-10, 4.3.3.2, Tabelle 1 Zeile 2: Durchgang, lichte Höhe über OFF ≥ 205 cm (alle Türen).
    Public text: Bayerisches Staatsministerium des Innern, für Bau und Verkehr, 'Planungsgrundlagen des
    barrierefreien Bauens' (2015), p. 11."""
    if door["height"] < 2050:
        fail(f"door {door['id']} clear height {door['height']} mm < 2050 mm", actual=door["height"], required=2050)
