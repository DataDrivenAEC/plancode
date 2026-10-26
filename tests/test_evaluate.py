"""Plugins (four types), the illustrative data source, and the per-variant evaluation (cost, carbon)."""
import pathlib
import urllib.request

import pytest

from arch_harness.design import effective_parameters, load_design
from arch_harness.evaluate.cost_estimate import estimate
from arch_harness.generators.massing import generate
from arch_harness.plugins import PLUGIN_TYPES, data_source, registry
from arch_harness.render.ifc import export_ifc

ROOT = pathlib.Path(__file__).resolve().parents[1]
BSI_SAMPLE = ("https://raw.githubusercontent.com/buildingSMART/Sample-Test-Files/"
              "80d976a9b193a26a8e928c3e79bff67af1de68a8/IFC%204.0.2.1%20(IFC%204%20ADD2%20TC1)/Simple-Scene/"
              "Building-Architecture.ifc")


def test_four_plugin_types_are_registered():
    assert PLUGIN_TYPES == ("generator", "rules", "skill", "data_source")
    reg = registry()
    assert "massing" in reg["generator"]
    assert "illustrative-materials" in reg["data_source"]
    assert {"design-loop", "model-cost"} <= set(reg["skill"])
    assert reg["rules"]


def test_data_source_contract():
    src = data_source("illustrative-materials")
    assert set(src.provides) == {"unit_prices", "carbon_factors"}
    assert "illustrative" in src.basis().lower()
    rows = src.table("unit_prices")
    assert {"material", "unit", "unit_price_eur", "trade_group"} <= set(rows[0])
    carbon = src.table("carbon_factors")
    assert {"material", "unit", "kgco2e_per_unit"} <= set(carbon[0])
    with pytest.raises(KeyError):
        src.table("climate")


@pytest.fixture(scope="module")
def variant_ifcs(tmp_path_factory):
    d = load_design(ROOT / "examples" / "clinic" / "DESIGN.md")
    out = {}
    for v in ("masonry", "timber"):
        p = effective_parameters(d, v)
        p.update(door_width=900, corridor_width=1800)
        out[v] = export_ifc(generate(d, p), tmp_path_factory.mktemp(v) / "model.ifc")
    return out


def test_cost_is_honest_about_what_it_cannot_price(variant_ifcs, tmp_path):
    src = data_source("illustrative-materials")
    r = estimate(variant_ifcs["masonry"], src, outdir=tmp_path)
    assert r["grand_total_eur"] > 0
    assert {"Structure", "Envelope", "Openings", "Finishes"} <= set(r["by_trade_eur"])
    assert "Metal stud" in r["unpriced_materials"]          # listed, never a silent zero
    assert r["doors"]["exterior"] == 1 and r["doors"]["interior"] > 10
    assert r["floor_area_m2"] > 400 and r["eur_per_m2"] > 0
    assert "order-of-magnitude" in r["basis"].lower() and "illustrative" in r["basis"].lower()
    assert r["carbon_kgco2e"] > 0
    assert (tmp_path / "cost-summary.md").exists() and (tmp_path / "cost-breakdown.csv").exists()


def test_variants_differ_in_cost_and_carbon(variant_ifcs):
    src = data_source("illustrative-materials")
    m = estimate(variant_ifcs["masonry"], src)
    t = estimate(variant_ifcs["timber"], src)
    assert m["grand_total_eur"] != t["grand_total_eur"]
    assert m["carbon_kgco2e"] != t["carbon_kgco2e"]


@pytest.mark.network
def test_cost_runs_on_a_real_buildingsmart_ifc():
    cache = ROOT / ".cache" / "Building-Architecture.ifc"
    if not cache.exists():
        try:
            cache.parent.mkdir(exist_ok=True)
            urllib.request.urlretrieve(BSI_SAMPLE, cache)
        except OSError as exc:
            pytest.skip(f"offline: cannot download the buildingSMART sample ({exc})")
    r = estimate(cache, data_source("illustrative-materials"))
    assert r["rows"] > 0
    # authoring-tool materials this small price book does not know are listed, not zeroed
    assert r["unpriced_materials"] or r["skipped"]
