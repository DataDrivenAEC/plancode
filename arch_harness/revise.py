"""Deterministic parameter fixes: the human is in the idea, not the iteration.

A failure whose fix is a single parameter at its stated minimum (a door to 90 cm, a corridor to 150/180 cm, a
storey raised to fit its door) is fixed here. A failure that needs a layout decision (a room that does not fit,
an opening longer than its wall, a building inside its Abstandsfläche) has no fix here: it goes to the agent or
the architect, with the reason.
"""
from __future__ import annotations

# rule id -> (parameter, how to read the target value from a failure's data)
PARAMETER_FIXES = {
    "DIN18040-1/4.3.3.2/door-clear-width": ("door_width", lambda d: d["required"]),
    "DIN18040-1/4.3.3.2/door-clear-height": ("door_height", lambda d: d["required"]),
    "DIN18040-1/4.3.2/corridor-width": ("corridor_width", lambda d: d["required"]),
}


def propose_revisions(report: dict, params: dict) -> list[dict]:
    targets: dict[str, tuple[int, str]] = {}
    for r in report["results"]:
        if r["outcome"] != "failed":
            continue
        fix = PARAMETER_FIXES.get(r["rule"])
        if fix:
            param, value = fix[0], fix[1](r["data"])
        elif r["rule"] == "geometry/opening-fits-wall" and "wall_height" in r["data"]:
            # raise the wall to the door, never shrink the door below its code minimum
            # (next 100 mm above the door, so a lintel fits, plus the slab above that the wall stops under)
            param, value = "storey_height", (r["data"]["needed"] // 100 + 1) * 100 + params.get("slab_thickness", 0)
        else:
            continue
        if value > targets.get(param, (0, ""))[0]:
            targets[param] = (value, f"{r['rule']} @ {r['element']}")
    return [{"param": k, "from": params.get(k), "to": v, "because": why}
            for k, (v, why) in sorted(targets.items()) if params.get(k) != v]
