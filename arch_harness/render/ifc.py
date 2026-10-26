"""IFC4 export via IfcOpenShell: a render target, written from the model, never read back as the truth.

Project units are millimetres, matching the model. (IfcOpenShell's geometry engine returns metres; readers convert
at that boundary.) IfcSpace is aggregated into its storey; walls, slabs and doors are contained in it. Doors fill
an opening that voids their host wall. Material build-ups per structure are illustrative.
"""
from __future__ import annotations

import pathlib

import numpy as np

from ..model import solids

# structure -> element role -> layers (material name, thickness mm). Illustrative build-ups, outermost first.
BUILD_UPS = {
    "masonry": {
        "external": [("Mineral render", 15), ("Mineral wool insulation", 160), ("Calcium silicate masonry", 175),
                     ("Gypsum plaster", 15)],
        "internal": [("Gypsum board", 12), ("Metal stud", 91), ("Gypsum board", 12)],
        "slab": [("Reinforced concrete C30/37", 220)],
    },
    "timber": {
        "external": [("Timber cladding", 25), ("Wood fibre insulation", 160), ("Cross-laminated timber", 100),
                     ("Gypsum board", 15)],
        "internal": [("Gypsum board", 12), ("Metal stud", 91), ("Gypsum board", 12)],
        "slab": [("Cross-laminated timber", 160), ("Cement screed", 60)],
    },
}


def _layers(structure: str, role: str, thickness: int) -> list[tuple[str, float]]:
    layers = BUILD_UPS[structure][role]
    total = sum(t for _, t in layers)
    return [(name, t * thickness / total) for name, t in layers]  # scaled to the element's thickness


def export_ifc(model: dict, path) -> pathlib.Path:
    import ifcopenshell
    import ifcopenshell.api as api
    from ifcopenshell.util.shape_builder import ShapeBuilder

    f = ifcopenshell.file(schema="IFC4")
    project = api.run("root.create_entity", f, ifc_class="IfcProject", name=model["project"]["name"])
    api.run("unit.assign_unit", f)  # millimetres, m², m³
    ctx = api.run("context.add_context", f, context_type="Model")
    body = api.run("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW",
                   parent=ctx)
    site = api.run("root.create_entity", f, ifc_class="IfcSite", name="Site")
    building = api.run("root.create_entity", f, ifc_class="IfcBuilding", name=model["project"]["name"])
    api.run("aggregate.assign_object", f, relating_object=project, products=[site])
    api.run("aggregate.assign_object", f, relating_object=site, products=[building])
    storeys = {}
    for st in model["storeys"]:
        s = api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name=st["name"])
        s.Elevation = float(st["elevation"])
        api.run("aggregate.assign_object", f, relating_object=building, products=[s])
        storeys[st["id"]] = s
    builder = ShapeBuilder(f)
    structure = model["parameters"].get("structure", "masonry")
    materials, layer_sets = {}, {}

    def material(name):
        if name not in materials:
            materials[name] = api.run("material.add_material", f, name=name)
        return materials[name]

    def layer_set(role, thickness):
        key = (role, round(thickness))
        if key not in layer_sets:
            ls = api.run("material.add_material_set", f, name=f"{structure} {role} {round(thickness)}",
                         set_type="IfcMaterialLayerSet")
            for name, t in _layers(structure, role, thickness):
                layer = api.run("material.add_layer", f, layer_set=ls, material=material(name))
                layer.LayerThickness = float(t)
            layer_sets[key] = ls
        return layer_sets[key]

    def place_box(entity, box, extra=0.0):
        mn, mx = np.array(box["min"], float), np.array(box["max"], float)
        mn[1] -= extra
        mx[1] += extra
        size = mx - mn
        rect = builder.rectangle(size=(size[0], size[1]))
        solid = builder.extrude(rect, magnitude=size[2])
        rep = builder.get_representation(body, [solid])
        api.run("geometry.assign_representation", f, product=entity, representation=rep)
        matrix = np.eye(4)
        matrix[:3, 3] = mn
        api.run("geometry.edit_object_placement", f, product=entity, matrix=matrix, is_si=False)

    by_id = {b["id"]: b for b in solids(model)}
    walls = {}
    for w in model["walls"]:
        e = api.run("root.create_entity", f, ifc_class="IfcWall", name=w["id"])
        place_box(e, by_id[w["id"]])
        api.run("spatial.assign_container", f, relating_structure=storeys[w["storey"]], products=[e])
        pset = api.run("pset.add_pset", f, product=e, name="Pset_WallCommon")
        api.run("pset.edit_pset", f, pset=pset, properties={"IsExternal": bool(w["external"])})
        api.run("material.assign_material", f, products=[e], type="IfcMaterialLayerSet",
                material=layer_set("external" if w["external"] else "internal", w["thickness"]))
        walls[w["id"]] = e
    for d in model["doors"]:
        box = by_id[d["id"]]
        opening = api.run("root.create_entity", f, ifc_class="IfcOpeningElement", name=f"{d['id']} opening")
        place_box(opening, box)
        api.run("feature.add_feature", f, feature=opening, element=walls[d["wall"]])
        e = api.run("root.create_entity", f, ifc_class="IfcDoor", name=d["id"])
        # The model states one door width, the clear width (DIN 18040-1); it has no leaf or frame width, so
        # OverallWidth carries that clear width, not a frame width.
        e.OverallWidth, e.OverallHeight = float(d["width"]), float(d["height"])
        place_box(e, {"min": box["min"], "max": box["max"]})
        api.run("feature.add_filling", f, opening=opening, element=e)
        api.run("spatial.assign_container", f, relating_structure=storeys[d["storey"]], products=[e])
    for s in model["slabs"]:
        e = api.run("root.create_entity", f, ifc_class="IfcSlab", name=s["id"],
                    predefined_type="ROOF" if s["role"] == "roof" else "FLOOR")
        place_box(e, by_id[s["id"]])
        api.run("spatial.assign_container", f, relating_structure=storeys[s["storey"]], products=[e])
        api.run("material.assign_material", f, products=[e], type="IfcMaterialLayerSet",
                material=layer_set("slab", s["thickness"]))
    for sp in model["spaces"]:
        e = api.run("root.create_entity", f, ifc_class="IfcSpace", name=sp["id"])
        e.LongName = sp["name"]
        place_box(e, by_id[sp["id"]])
        api.run("aggregate.assign_object", f, relating_object=storeys[sp["storey"]], products=[e])
        qto = api.run("pset.add_qto", f, product=e, name="Qto_SpaceBaseQuantities")
        api.run("pset.edit_qto", f, qto=qto, properties={"NetFloorArea": sp["w"] * sp["d"] / 1e6})
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    f.write(str(path))
    return path
