"""Floor plan SVG per storey, in mm, readable by the agent: every element carries data-id and a <title>."""
from __future__ import annotations

from xml.sax.saxutils import escape

from ..generators.massing import setback
from ..model import solids


def plan_svg(model: dict, storey: str) -> str:
    site, b = model["site"], model["building"]
    pad = 2000
    W, D = site["width"], site["depth"]
    flip = lambda y: D - y  # SVG y grows downwards; the model's y is north
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{-pad} {-pad} {W + 2 * pad} {D + 2 * pad}" '
           f'width="{(W + 2 * pad) // 40}" height="{(D + 2 * pad) // 40}" font-family="sans-serif">',
           f'<title>{escape(model["project"]["name"])}: plan {storey} (mm, north up)</title>',
           f'<rect data-id="site" x="0" y="0" width="{W}" height="{D}" fill="none" stroke="#2a7" '
           f'stroke-width="60"><title>site {W} × {D} mm</title></rect>']
    s = setback(b["height"])
    out.append(f'<rect data-id="abstandsflaeche" x="{b["x"] - s}" y="{flip(b["y"] + b["d"] + s)}" '
               f'width="{b["w"] + 2 * s}" height="{b["d"] + 2 * s}" fill="none" stroke="#2a7" stroke-width="30" '
               f'stroke-dasharray="300 200"><title>Abstandsfläche {s} mm (MBO § 6 Abs. 5)</title></rect>')
    for sp in model["spaces"]:
        if sp["storey"] != storey:
            continue
        area = sp["w"] * sp["d"] / 1e6
        fill = "#eef3f8" if sp["use"] == "corridor" else "#dbe9f6"
        y = flip(sp["y"] + sp["d"])
        out.append(f'<g data-id="{sp["id"]}"><title>{sp["id"]} {escape(sp["name"])} {area:.1f} m² '
                   f'({sp["w"]} × {sp["d"]} mm)</title>'
                   f'<rect x="{sp["x"]}" y="{y}" width="{sp["w"]}" height="{sp["d"]}" fill="{fill}"/>'
                   f'<text x="{sp["x"] + sp["w"] / 2}" y="{y + sp["d"] / 2}" font-size="380" text-anchor="middle">'
                   f'<tspan x="{sp["x"] + sp["w"] / 2}">{escape(sp["name"])}</tspan>'
                   f'<tspan x="{sp["x"] + sp["w"] / 2}" dy="460">{area:.1f} m²</tspan></text></g>')
    for box in solids(model):
        if box["storey"] != storey or box["kind"] not in ("wall", "door"):
            continue
        (x0, y0, _), (x1, y1, _) = box["min"], box["max"]
        color = "#333" if box["kind"] == "wall" else "#c60"
        out.append(f'<rect data-id="{box["id"]}" x="{x0}" y="{flip(y1)}" width="{x1 - x0}" height="{y1 - y0}" '
                   f'fill="{color}"><title>{box["kind"]} {box["id"]}</title></rect>')
    out.append("</svg>")
    return "\n".join(out) + "\n"
