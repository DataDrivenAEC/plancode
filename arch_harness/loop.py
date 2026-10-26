"""The design loop: generate -> check -> revise -> repeat, bounded, one record per round.

Done means all three rule kinds ran and passed. When a round has failures and no deterministic fix, or the
rounds run out, the loop stops and says why; it never reports compliance a check did not confirm.
"""
from __future__ import annotations

import json
import pathlib

from .checks import failures, run_rules
from .generators.massing import generate
from .model import write_model
from .revise import propose_revisions


def _summary(fails: list[dict], limit: int = 6) -> str:
    rules = {}
    for f in fails:
        rules.setdefault(f["rule"], []).append(f)
    parts = []
    for rule, fs in sorted(rules.items()):
        parts.append(f"{rule} ×{len(fs)} (e.g. {fs[0]['message']})")
    return "; ".join(parts[:limit])


def run_loop(design: dict, params: dict, outdir, max_rounds: int = 5, on_round=None) -> dict:
    outdir = pathlib.Path(outdir)
    (outdir / "rounds").mkdir(parents=True, exist_ok=True)
    params = dict(params)
    rounds = []
    converged, reason, model = False, "", None
    for n in range(1, max_rounds + 1):
        model = generate(design, params)
        model_path = write_model(model, outdir / "model.json")
        report = run_rules(model_path)
        fails = failures(report)
        revisions = [] if report["passed"] else propose_revisions(report, model["parameters"])
        record = {"round": n, "parameters": {k: model["parameters"][k] for k in sorted(model["parameters"])},
                  "passed": report["passed"], "by_kind": report["by_kind"],
                  "unconfirmed_kinds": report["unconfirmed_kinds"],
                  "failures": [{k: f[k] for k in ("rule", "kind", "element", "message")} for f in fails],
                  "generator_notes": model["notes"], "revisions": revisions}
        (outdir / "rounds" / f"round-{n:02d}.json").write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n")
        rounds.append(record)
        if on_round:
            on_round(record, model)
        if report["passed"]:
            converged, reason = True, f"all three rule kinds pass after {n} round(s)"
            break
        if not revisions:
            notes = "; ".join(model["notes"]) or "none"
            unconf = f" Unconfirmed kinds: {', '.join(report['unconfirmed_kinds'])}." if report["unconfirmed_kinds"] else ""
            reason = (f"cannot converge: no parameter fix for the remaining failures, which need a layout or brief "
                      f"decision. Failures: {_summary(fails)}.{unconf} Generator notes: {notes}")
            break
        for r in revisions:
            params[r["param"]] = r["to"]
    else:
        reason = f"did not converge within {max_rounds} round(s); last failures: {_summary(fails)}"
    return {"converged": converged, "reason": reason, "rounds": rounds, "model": model,
            "model_path": str(outdir / "model.json")}
