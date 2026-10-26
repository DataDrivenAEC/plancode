"""arch-harness MCP server: JSON-RPC 2.0 over stdio (newline-delimited), standard library only.

Any MCP-capable harness connects with:  python -m arch_harness.mcp_server --project <dir>
Implements initialize, ping, tools/list and tools/call. Tools: the four hook-contract calls (ah_*) and the
domain (generators, rules, renders, cost, data sources). Logs go to stderr; stdout carries only protocol.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import pathlib
import sys

from . import __version__, hooks
from .checks import failures, run_rules
from .design import load_design
from .project import MODEL_DIR, build, commit, params_for, render
from .revise import propose_revisions

PROTOCOL_VERSION = "2025-06-18"


def _obj(props=None, required=None):
    return {"type": "object", "properties": props or {}, "required": required or [], "additionalProperties": False}


STR = {"type": "string"}
INT = {"type": "integer"}
OVERRIDES = {"type": "object", "description": "parameter overrides in mm (e.g. {\"door_width\": 900})",
             "additionalProperties": {"type": ["integer", "string"]}}

TOOLS = {
    "ah_context": ("Hook 3: DESIGN.md (the architect's intent) and the project status, for the agent's context.", _obj()),
    "ah_after_step": ("Hook 1: run every rule on the current model, record a round, return the failures and any "
                      "deterministic fixes.", _obj()),
    "ah_before_settle": ("Hook 2: may the agent finish? settle=false while rules fail, until max_rounds since "
                         "since_round; then settle=true with the reason it cannot converge.",
                         _obj({"max_rounds": INT, "since_round": INT})),
    "ah_fork_variant": ("Hook 4: put a design variant on its own git branch variant/<name>.", _obj({"name": STR}, ["name"])),
    "read_design": ("DESIGN.md parsed into data (site, programme, constraints, parameters in mm, ideas, variants).", _obj()),
    "generate_massing": ("Generator: massing from the brief (footprint from the site minus the Abstandsfläche, storeys "
                         "from the programme). Writes model/model.json, OpenUSD layers and plan SVGs. The variant "
                         "defaults to the current branch's; overrides change parameters (mm).",
                         _obj({"variant": STR, "overrides": OVERRIDES})),
    "check_rules": ("Run the rules (code, geometry, brief) on the current model without recording a round.", _obj()),
    "revise_parameters": ("Deterministic parameter fixes for the current failures (to the code minimum).", _obj()),
    "plan_svg": ("The floor plan of one storey as SVG text (mm; every element has data-id and a title).",
                 _obj({"storey": STR}, ["storey"])),
    "export_ifc": ("Export the current model to model/model.ifc (IFC4, mm).", _obj()),
    "estimate_cost": ("Cost and embodied carbon of the current model from a data source (illustrative by default): "
                      "totals by trade, EUR/m², unpriced materials, basis.", _obj({"data_source": STR})),
    "run_loop": ("The deterministic loop without a model: generate, check, revise, repeat up to max_rounds.",
                 _obj({"variant": STR, "max_rounds": INT})),
    "commit": ("Commit the project's current state to git with a message (a decision, a round, a variant).",
               _obj({"message": STR}, ["message"])),
    "list_plugins": ("The registered plugins by type: generator, rules, skill, data_source.", _obj()),
    "query_data_source": ("Rows of one table from a data-source plugin (e.g. unit_prices, carbon_factors).",
                          _obj({"name": STR, "kind": STR}, ["name", "kind"])),
}


class Server:
    def __init__(self, project):
        self.project = pathlib.Path(project).resolve()

    def model_path(self):
        return self.project / MODEL_DIR / "model.json"

    def call(self, name: str, a: dict):
        p = self.project
        if name == "ah_context":
            return hooks.context(p), hooks.status(p)
        if name == "ah_after_step":
            out = hooks.after_step(p)
            return out["text"], out
        if name == "ah_before_settle":
            out = hooks.before_settle(p, a.get("max_rounds", 5), a.get("since_round", 0))
            return ("SETTLE: " if out["settle"] else "DO NOT SETTLE: ") + out["reason"], out
        if name == "ah_fork_variant":
            out = hooks.fork_variant(p, a["name"])
            return f"on branch {out['branch']} (head {out['head']})", out
        if name == "read_design":
            d = load_design(p / "DESIGN.md")
            return json.dumps(d, indent=1, ensure_ascii=False), d
        if name == "generate_massing":
            m = build(p, a.get("variant"), a.get("overrides"))
            rooms = [s for s in m["spaces"] if s["use"] == "room"]
            b = m["building"]
            text = (f"massing: {len(m['storeys'])} storey(s), footprint {b['w']} × {b['d']} mm at ({b['x']}, {b['y']}), "
                    f"height {b['height']} mm, {len(rooms)} rooms, {len(m['doors'])} doors. Parameters: "
                    + json.dumps({k: m["parameters"][k] for k in sorted(m["parameters"])}))
            if m["notes"]:
                text += "\nGenerator notes: " + "; ".join(m["notes"])
            return text, {"building": b, "storeys": len(m["storeys"]), "rooms": len(rooms), "notes": m["notes"]}
        if name == "check_rules":
            report = run_rules(self.model_path())
            fails = failures(report)
            text = f"passed={report['passed']} by_kind={json.dumps(report['by_kind'])}\n" + "\n".join(
                f"- {f['rule']} @ {f['element']}: {f['message']}" for f in fails[:20])
            return text, {"passed": report["passed"], "by_kind": report["by_kind"], "failures": fails}
        if name == "revise_parameters":
            report = run_rules(self.model_path())
            params = json.loads(self.model_path().read_text())["parameters"]
            revs = propose_revisions(report, params)
            return (json.dumps(revs) if revs else "no deterministic fix for the current failures"), {"revisions": revs}
        if name == "plan_svg":
            from .render.svg import plan_svg
            return plan_svg(json.loads(self.model_path().read_text()), a["storey"]), None
        if name == "export_ifc":
            from .render.ifc import export_ifc
            path = export_ifc(json.loads(self.model_path().read_text()), p / MODEL_DIR / "model.ifc")
            return f"wrote {path.relative_to(p)}", {"path": str(path)}
        if name == "estimate_cost":
            from .evaluate.cost_estimate import estimate
            from .plugins import data_source
            from .render.ifc import export_ifc
            ifc = export_ifc(json.loads(self.model_path().read_text()), p / MODEL_DIR / "model.ifc")
            r = estimate(ifc, data_source(a.get("data_source", "illustrative-materials")), outdir=p / MODEL_DIR / "cost")
            text = (f"EUR {r['grand_total_eur']:,.0f} (materials) = EUR {r['eur_per_m2'] or 0:,.0f}/m² over "
                    f"{r['floor_area_m2']:,.0f} m²; by trade {json.dumps(r['by_trade_eur'])}; carbon "
                    f"{r['carbon_kgco2e']:,.0f} kg CO2e; unpriced: {', '.join(r['unpriced_materials']) or 'none'}. "
                    f"Basis: {r['basis']}")
            return text, r
        if name == "run_loop":
            from .loop import run_loop
            design, params = params_for(p, a.get("variant"))
            out = run_loop(design, params, p / MODEL_DIR, max_rounds=a.get("max_rounds", 5))
            render(out["model"], p / MODEL_DIR)
            text = f"converged={out['converged']} after {len(out['rounds'])} round(s): {out['reason']}"
            return text, {"converged": out["converged"], "reason": out["reason"], "rounds": out["rounds"]}
        if name == "commit":
            done = commit(p, a["message"])
            return ("committed" if done else "nothing to commit"), {"committed": done}
        if name == "list_plugins":
            from .plugins import registry
            reg = {k: sorted(v) for k, v in registry().items()}
            return json.dumps(reg), reg
        if name == "query_data_source":
            from .plugins import data_source
            src = data_source(a["name"])
            rows = src.table(a["kind"])
            return json.dumps({"basis": src.basis(), "rows": rows}, ensure_ascii=False), {"basis": src.basis(), "rows": rows}
        raise KeyError(f"unknown tool {name!r}")

    def handle(self, msg: dict):
        method, mid = msg.get("method"), msg.get("id")
        if mid is None:
            return None  # notification
        if method == "initialize":
            requested = (msg.get("params") or {}).get("protocolVersion") or PROTOCOL_VERSION
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": requested, "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "arch-harness", "version": __version__},
                "instructions": "Idea-first design: read ah_context first; after each generate_massing the rules "
                                "run (ah_after_step); do not finish while ah_before_settle says DO NOT SETTLE."}}
        if method == "ping":
            return {"jsonrpc": "2.0", "id": mid, "result": {}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": mid, "result": {"tools": [
                {"name": n, "description": d, "inputSchema": s} for n, (d, s) in TOOLS.items()]}}
        if method == "tools/call":
            params = msg.get("params") or {}
            try:
                with contextlib.redirect_stdout(io.StringIO()):  # keep stdout for protocol only
                    text, structured = self.call(params.get("name"), params.get("arguments") or {})
                result = {"content": [{"type": "text", "text": text}], "isError": False}
                if structured is not None:
                    result["structuredContent"] = json.loads(json.dumps(structured, default=str))
            except Exception as exc:  # a failed tool is a result the agent can read, not a protocol error
                result = {"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}], "isError": True}
            return {"jsonrpc": "2.0", "id": mid, "result": result}
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}


def serve(project, stdin=sys.stdin, stdout=sys.stdout):
    server = Server(project)
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            reply = server.handle(msg)
        if reply is not None:
            stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            stdout.flush()


def main(argv=None):
    ap = argparse.ArgumentParser(description="arch-harness MCP server (stdio)")
    ap.add_argument("--project", default=".", help="the design project directory (holds DESIGN.md)")
    serve(ap.parse_args(argv).project)


if __name__ == "__main__":
    main()
