"""Canonical OpenUSD writer: one root layer plus one text layer per storey, byte-stable for clean git diffs.

Every element is a UsdGeom.Cube scaled to its box from model.solids() (mm, Z up, metersPerUnit 0.001). Prim
names are the model ids with '-' as '_'; the exact id is kept in customData 'ah:id'. Exact solids from NVIDIA
usd-brep (milestone 2) replace the Cube authoring in _author_box, not the layer layout.
"""
from __future__ import annotations

import pathlib

from ..model import solids

COLORS = {"wall": (0.85, 0.83, 0.78), "door": (0.55, 0.36, 0.2), "slab": (0.7, 0.7, 0.72),
          "space": (0.55, 0.75, 0.9)}


def _name(id_: str) -> str:
    return "e_" + "".join(c if c.isalnum() else "_" for c in id_)


def _author_box(stage, path: str, box: dict):
    from pxr import Gf, Sdf, UsdGeom, Vt
    cube = UsdGeom.Cube.Define(stage, path)
    cube.CreateSizeAttr(1.0)
    mn, mx = box["min"], box["max"]
    center = Gf.Vec3d(*[(a + b) / 2 for a, b in zip(mn, mx)])
    scale = Gf.Vec3f(*[float(b - a) for a, b in zip(mn, mx)])
    cube.AddTranslateOp().Set(center)
    cube.AddScaleOp().Set(scale)
    cube.CreateExtentAttr(Vt.Vec3fArray([Gf.Vec3f(-0.5, -0.5, -0.5), Gf.Vec3f(0.5, 0.5, 0.5)]))
    cube.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*COLORS[box["kind"]])]))
    if box["kind"] == "space":
        cube.CreateDisplayOpacityAttr(Vt.FloatArray([0.25]))
    prim = cube.GetPrim()
    prim.SetCustomDataByKey("ah:id", box["id"])
    prim.SetCustomDataByKey("ah:kind", box["kind"])
    prim.CreateAttribute("ah:storey", Sdf.ValueTypeNames.String).Set(box["storey"])


def _stage():
    from pxr import Usd, UsdGeom
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.SetStageMetersPerUnit(stage, 0.001)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.Xform.Define(stage, "/Building")
    stage.SetDefaultPrim(stage.GetPrimAtPath("/Building"))
    return stage


def write_usd(model: dict, outdir) -> list[pathlib.Path]:
    from pxr import UsdGeom
    outdir = pathlib.Path(outdir)
    (outdir / "storeys").mkdir(parents=True, exist_ok=True)
    boxes = solids(model)
    written = []
    sublayers = []
    for st in model["storeys"]:
        stage = _stage()
        UsdGeom.Xform.Define(stage, f"/Building/{st['id']}")
        for box in boxes:
            if box["storey"] == st["id"]:
                _author_box(stage, f"/Building/{st['id']}/{_name(box['id'])}", box)
        path = outdir / "storeys" / f"{st['id']}.usda"
        path.write_text(stage.GetRootLayer().ExportToString(), encoding="utf-8")
        written.append(path)
        sublayers.append(f"./storeys/{st['id']}.usda")
    root = _stage()
    prim = root.GetPrimAtPath("/Building")
    prim.SetCustomDataByKey("ah:project", model["project"]["name"])
    prim.SetCustomDataByKey("ah:schema", model["schema"])
    layer = root.GetRootLayer()
    layer.subLayerPaths = list(reversed(sublayers))  # strongest first; storeys do not overlap
    layer.documentation = "arch-harness render of model.json (the source of truth). Do not edit by hand."
    path = outdir / "building.usda"
    path.write_text(layer.ExportToString(), encoding="utf-8")
    return [path] + written
