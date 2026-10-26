# Ported from aec-ai-workshop-2026 (same author), released here under Apache-2.0.
"""Cost estimate (and carbon) from an IFC model and a unit-price data source.

Ported from the workshop's model-cost skill (.claude/skills/model-cost/cost_estimate.py, branch `solution`).
Changes in the port: a function instead of a script (one call per variant); prices and carbon factors come
from a data-source plugin instead of a fixed CSV path; csv instead of pandas; the material map covers the
arch-harness build-ups; method notes read their numbers from the price book; carbon = quantity × factor.
The honesty rules are kept: unpriced materials are listed (never silent zeros), skipped elements are listed,
the basis is stated.

Model has no quantity sets, so quantities are derived from geometry (IfcOpenShell returns metres):
  - m3 materials  -> layer volume (element volume split by layer-thickness fraction)
  - m2 materials  -> face area (wall elevation, or slab/covering footprint)
  - kg materials  -> layer volume x density
  - unit          -> count (doors)
  - windows       -> glazing area (OverallWidth x OverallHeight)
"""
from __future__ import annotations

import argparse
import csv
import datetime
import os
from collections import Counter, defaultdict
from types import SimpleNamespace

STEEL_DENSITY = 7850  # kg/m3

# model material name -> price-list key  (None = deliberately unmapped)
MAT_MAP = {
    # arch-harness build-ups (render/ifc.py)
    "Reinforced concrete C30/37": "concrete_c30",
    "Calcium silicate masonry": "masonry_calcium_silicate",
    "Cross-laminated timber": "clt",
    "Mineral wool insulation": "mineral_wool",
    "Wood fibre insulation": "wood_fibre",
    "Mineral render": "render",
    "Timber cladding": "timber_cladding",
    "Gypsum plaster": "plaster",
    "Gypsum board": "gypsum_board",
    "Cement screed": "screed",
    "Metal stud": None,  # the price book has no stud line: listed as unpriced
    # authoring-tool names seen in the workshop models
    "Concrete - Cast In Situ": "concrete_c30",
    "Concrete": "concrete_c30",
    "Insulation / Thermal Barriers - Semi-rigid insulation": "mineral_wool",
    "Plasterboard": "gypsum_board",
}


def resolve_material(name):
    """Price-book key for a model material name: exact map first, then a
    keyword guess (handles authoring-tool variants like 'Type-X Plasterboard'),
    else None. Exact map always wins, so known models stay unchanged."""
    if not name:
        return None
    if name in MAT_MAP:
        return MAT_MAP[name]
    n = name.lower()
    if "ceiling tile" in n or "acoustic" in n:
        return None                       # suspended ceiling — no price line
    if "plasterboard" in n or "gypsum" in n or "drywall" in n or "wallboard" in n:
        return "gypsum_board"             # incl. 'Type-X' fire-rated board
    if "plaster" in n:
        return "plaster"
    if "calcium silicate" in n or "sand-lime" in n:
        return "masonry_calcium_silicate"
    if "concrete" in n:
        return "concrete_c30"
    if "clt" in n or "cross-laminated" in n:
        return "clt"
    if "wood fibre" in n or "wood fiber" in n:
        return "wood_fibre"
    if "insulation" in n or "mineral wool" in n:
        return "mineral_wool"
    if "screed" in n:
        return "screed"
    if "render" in n or "stucco" in n:
        return "render"
    return None


def compute_floor_area(model):
    """Sum of room (IfcSpace) areas in m², excluding roof spaces. 0 if none found."""
    import ifcopenshell.util.element as eu
    total = 0.0
    for sp in model.by_type("IfcSpace"):
        label = f"{sp.Name or ''} {getattr(sp, 'LongName', '') or ''}".lower()
        if "roof" in label:
            continue
        area = None
        for src in (eu.get_psets(sp, qtos_only=True), eu.get_psets(sp)):
            for d in src.values():
                for k, v in d.items():
                    if isinstance(v, (int, float)) and v > 0 and "area" in k.lower():
                        area = v
                        break
                if area:
                    break
            if area:
                break
        if area:
            total += area
    return total


def project_name(model):
    pr = model.by_type("IfcProject")
    if pr:
        p = pr[0]
        nm = (p.Name or "").strip()
        if nm and nm.lower() not in ("", "0001", "default", "project"):
            return nm
        return (getattr(p, "LongName", None) or nm or None)
    return None


def estimate(model_path, source, outdir=None) -> dict:
    """Estimate one IFC model against a data source (unit_prices, optional carbon_factors)."""
    import ifcopenshell
    import ifcopenshell.geom as geom
    import ifcopenshell.util.element as eu
    import ifcopenshell.util.shape as ushape
    import ifcopenshell.util.unit

    m = ifcopenshell.open(str(model_path))
    PRICE = {r["material"]: SimpleNamespace(**r) for r in source.table("unit_prices")}
    CARBON = ({r["material"]: r["kgco2e_per_unit"] for r in source.table("carbon_factors")}
              if "carbon_factors" in source.provides else {})
    settings = geom.settings()
    unit_scale = ifcopenshell.util.unit.calculate_unit_scale(m)  # project length unit -> metres

    def geom_metrics(el):
        """Return (volume, footprint_area, side_area) in m / m2 / m3, or None on failure."""
        try:
            shp = geom.create_shape(settings, el)
        except Exception:
            return None
        g = shp.geometry
        vol = ushape.get_volume(g)
        verts = ushape.get_vertices(g)
        mn, mx = ushape.get_bbox(verts)
        dx, dy, dz = (mx - mn)
        footprint = float(dx * dy)
        horiz = sorted([float(dx), float(dy)])
        side_area = horiz[1] * float(dz)   # length x height
        return float(vol), footprint, side_area

    def layers(el):
        """List of (material_name, thickness) for a layered element, else None."""
        for rel in getattr(el, "HasAssociations", []) or []:
            if rel.is_a("IfcRelAssociatesMaterial"):
                mat = rel.RelatingMaterial
                mls = (mat.ForLayerSet if mat.is_a("IfcMaterialLayerSetUsage")
                       else mat if mat.is_a("IfcMaterialLayerSet") else None)
                if mls:
                    return [(l.Material.Name if l.Material else None, l.LayerThickness)
                            for l in mls.MaterialLayers]
        return None

    def single_material(el):
        ms = eu.get_materials(el)
        return ms[0].Name if ms else None

    def host_wall_is_external(door):
        for r in getattr(door, "FillsVoids", []) or []:
            op = r.RelatingOpeningElement
            for r2 in getattr(op, "VoidsElements", []) or []:
                w = r2.RelatingBuildingElement
                return eu.get_psets(w).get("Pset_WallCommon", {}).get("IsExternal")
        return None

    rows = []          # breakdown rows
    skipped = []       # (guid, type, reason)
    unmapped_seen = {} # material -> count of elements
    no_carbon = {}     # priced material key -> count with no carbon factor
    carbon_total = 0.0

    def add_line(el, material_name, qty, unit, price_key):
        nonlocal carbon_total
        pr = PRICE.get(price_key) if price_key else None
        if pr is None:
            unmapped_seen[material_name] = unmapped_seen.get(material_name, 0) + 1
            rows.append([el.GlobalId, el.is_a(), material_name, round(qty, 4), unit or "",
                         0.0, 0.0, "(unpriced)", "", "missing from price list"])
            return
        line_total = qty * pr.unit_price_eur
        factor = CARBON.get(pr.material)
        if factor is None:
            no_carbon[pr.material] = no_carbon.get(pr.material, 0) + 1
            carbon = ""
        else:
            carbon = round(qty * factor, 2)
            carbon_total += qty * factor
        rows.append([el.GlobalId, el.is_a(), material_name, round(qty, 4), pr.unit,
                     pr.unit_price_eur, round(line_total, 2), pr.trade_group, carbon, ""])

    WALL_LIKE = ("IfcWall", "IfcWallStandardCase")
    SLAB_LIKE = ("IfcSlab", "IfcRoof", "IfcCovering", "IfcFooting", "IfcStair", "IfcStairFlight")

    def cost_layered_element(el, gm):
        vol, footprint, side_area = gm
        ls = layers(el)
        area_basis = side_area if el.is_a() in WALL_LIKE else footprint
        if not ls:
            return False
        total_t = sum(t for _, t in ls if t) or 1.0
        for name, t in ls:
            if not name:
                continue
            key = resolve_material(name)
            pr = PRICE.get(key) if key else None
            if pr is None:
                add_line(el, name, vol * (t / total_t), "m3", None)  # unpriced, qty informational
                continue
            if pr.unit == "m3":
                add_line(el, name, vol * (t / total_t), "m3", key)
            elif pr.unit == "m2":
                add_line(el, name, area_basis, "m2", key)
            elif pr.unit == "kg":
                add_line(el, name, vol * (t / total_t) * STEEL_DENSITY, "kg", key)
        return True

    def cost_single_material(el, gm, name):
        vol, footprint, side_area = gm
        key = resolve_material(name)
        pr = PRICE.get(key) if key else None
        if pr is None:
            add_line(el, name, vol, "m3", None)
            return
        if pr.unit == "m3":
            add_line(el, name, vol, "m3", key)
        elif pr.unit == "m2":
            add_line(el, name, footprint if el.is_a() in SLAB_LIKE else side_area, "m2", key)
        elif pr.unit == "kg":
            add_line(el, name, vol * STEEL_DENSITY, "kg", key)

    # ---- doors ----
    n_ext_doors = n_int_doors = 0
    for d in m.by_type("IfcDoor"):
        ext = host_wall_is_external(d)
        if ext:
            n_ext_doors += 1
        else:
            n_int_doors += 1
        key = "door_exterior_security" if ext else "door_interior_wood"
        add_line(d, "(exterior door)" if ext else "(interior door)", 1, "unit", key)

    # ---- windows ----
    n_windows = 0
    for w in m.by_type("IfcWindow"):
        ow, oh = w.OverallWidth, w.OverallHeight
        if not ow or not oh:
            skipped.append((w.GlobalId, "IfcWindow", "missing OverallWidth/Height"))
            continue
        n_windows += 1
        add_line(w, "(glazing)", float(ow) * float(oh) * unit_scale ** 2, "m2", "window_double_glazed")

    # ---- fabric (walls, slabs, roof, footings, beams, members, coverings, stairs, railings) ----
    FABRIC = ("IfcWall", "IfcSlab", "IfcRoof", "IfcFooting", "IfcBeam",
              "IfcMember", "IfcCovering", "IfcStair", "IfcStairFlight", "IfcRailing")
    done = set()
    for t in FABRIC:
        for el in m.by_type(t):
            if el.GlobalId in done:
                continue
            done.add(el.GlobalId)
            ls = layers(el)
            sm = single_material(el)
            if not ls and not sm:
                skipped.append((el.GlobalId, el.is_a(), "no material assigned"))
                continue
            gm = geom_metrics(el)
            if gm is None or gm[0] <= 0:
                skipped.append((el.GlobalId, el.is_a(), "no usable geometry/volume"))
                continue
            if ls:
                cost_layered_element(el, gm)
            else:
                cost_single_material(el, gm, sm)

    # ---- roll up ----
    trade_tot = defaultdict(float)
    for r in rows:
        if r[7] not in ("(unpriced)",):
            trade_tot[r[7]] += r[6]
    grand = sum(trade_tot.values())
    proj = project_name(m) or os.path.splitext(os.path.basename(str(model_path)))[0]
    gfa = compute_floor_area(m)
    basis = ("Order-of-magnitude design estimate, not a tender bill of quantities. Materials only: no labour, "
             "preliminaries, contingency, reinforcement or MEP unless modelled. Quantities derived from the 3D "
             "geometry. " + source.basis())

    result = {
        "project": proj, "rows": len(rows), "grand_total_eur": round(grand, 2),
        "by_trade_eur": {k: round(v, 2) for k, v in trade_tot.items()},
        "floor_area_m2": round(gfa, 2), "eur_per_m2": round(grand / gfa, 2) if gfa else None,
        "carbon_kgco2e": round(carbon_total, 1),
        "kgco2e_per_m2": round(carbon_total / gfa, 1) if gfa else None,
        "unpriced_materials": dict(unmapped_seen), "no_carbon_factor": dict(no_carbon),
        "skipped": [list(s) for s in skipped],
        "doors": {"exterior": n_ext_doors, "interior": n_int_doors}, "windows": n_windows,
        "basis": basis, "data_source": source.name,
    }
    if outdir is not None:
        _write(result, rows, trade_tot, skipped, PRICE, outdir)
    return result


TRADE_ORDER = ["Structure", "Envelope", "Openings", "Finishes", "MEP"]


def _write(result, rows, trade_tot, skipped, PRICE, outdir):
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "cost-breakdown.csv"), "w", newline="") as fh:
        wtr = csv.writer(fh)
        wtr.writerow(["GUID", "ifc_type", "material", "quantity", "unit",
                      "unit_price", "line_total", "trade_group", "kgco2e", "note"])
        wtr.writerows(rows)
    grand, gfa = result["grand_total_eur"], result["floor_area_m2"]
    lines = [f"# Cost estimate — {result['project']}\n",
             f"**Data source:** `{result['data_source']}` · **Generated:** {datetime.date.today().isoformat()}\n",
             f"> {result['basis']}\n",
             "## Cost by trade group\n", "| Trade group | Cost (€) |", "|---|---:|"]
    for tr in TRADE_ORDER:
        if tr in trade_tot:
            lines.append(f"| {tr} | {trade_tot[tr]:,.0f} |")
    lines.append(f"| **Grand total** | **{grand:,.0f}** |")
    lines.append("")
    if gfa > 0:
        lines.append(f"_Floor area (sum of room areas, excl. roof): **{gfa:,.0f} m²** → "
                     f"indicative **€{grand / gfa:,.0f}/m²**_\n")
    else:
        lines.append("_No room areas found in the model, so €/m² is not reported._\n")
    lines.append(f"**Embodied carbon (materials with a factor):** {result['carbon_kgco2e']:,.0f} kg CO2e"
                 + (f" ({result['kgco2e_per_m2']:,.0f} kg CO2e/m²)" if result["kgco2e_per_m2"] else "") + "\n")
    lines.append("## Materials in the model with no price (added to nothing — flag for next time)\n")
    if result["unpriced_materials"]:
        lines.append("| Material | Elements affected | Likely price-list gap |")
        lines.append("|---|---:|---|")
        hint = {"Metal stud": "steel-stud framing (per m² partition)",
                "Misc. Air Layers - Air Space": "n/a — air cavity, no cost"}
        for mat, n in sorted(result["unpriced_materials"].items(), key=lambda kv: -kv[1]):
            lines.append(f"| {mat} | {n} | {hint.get(mat, 'add to price list')} |")
    else:
        lines.append("_None._")
    lines.append("")
    lines.append("## Skipped elements (no material or no usable geometry)\n")
    if skipped:
        sc = Counter((t, reason) for _, t, reason in skipped)
        lines.append("| IFC type | Reason | Count |")
        lines.append("|---|---|---:|")
        for (t, reason), n in sc.most_common():
            lines.append(f"| {t} | {reason} | {n} |")
    else:
        lines.append("_None._")
    lines.append("")
    lines.append("## Method notes & assumptions\n")
    lines.append("- **Material names** are matched to the price book by exact name, then by keyword; "
                 "anything unmatched is listed above, not silently zeroed.")
    lines.append("- **Layered walls** are costed by their material layers — board faces are priced per m² "
                 "even when a stud cavity is the thickest layer, so partitions aren't undercounted.")
    d = result["doors"]
    if d["exterior"] or d["interior"]:
        ext, inn = PRICE.get("door_exterior_security"), PRICE.get("door_interior_wood")
        price = lambda p: f" (€{p.unit_price_eur:,.0f})" if p else " (unpriced)"
        lines.append(f"- **Doors**: {d['exterior']} hosted in external walls priced as exterior doors{price(ext)}; "
                     f"{d['interior']} as interior doors{price(inn)}.")
    if result["no_carbon_factor"]:
        lines.append(f"- **Carbon**: no factor for {', '.join(sorted(result['no_carbon_factor']))}; "
                     "those lines carry no carbon (not zero carbon).")
    lines.append("- Reinforcement, MEP, screeds (unless modelled) and paint are **not modelled**, so €0 here — "
                 "a real estimate carries allowances.")
    with open(os.path.join(outdir, "cost-summary.md"), "w") as fh:
        fh.write("\n".join(lines) + "\n")


def main(argv=None):
    from ..data_sources.illustrative_materials import CSV, IllustrativeMaterials
    ap = argparse.ArgumentParser(description="Cost estimate from an IFC model + a unit-price book.")
    ap.add_argument("--model", required=True, help="path to the .ifc model")
    ap.add_argument("--prices", default=str(CSV), help="price CSV (data-source format)")
    ap.add_argument("--outdir", default="outputs", help="directory for the two output files")
    args = ap.parse_args(argv)
    r = estimate(args.model, IllustrativeMaterials(args.prices), args.outdir)
    print(f"rows={r['rows']}  skipped={len(r['skipped'])}  grand=EUR {r['grand_total_eur']:,.0f}  "
          f"carbon={r['carbon_kgco2e']:,.0f} kgCO2e")
    for tr in TRADE_ORDER:
        if tr in r["by_trade_eur"]:
            print(f"  {tr:10} {r['by_trade_eur'][tr]:12,.0f}")
    print("unmapped materials:", r["unpriced_materials"])


if __name__ == "__main__":
    main()
