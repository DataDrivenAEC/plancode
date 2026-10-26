"""The design loop: generate -> check -> revise -> repeat, bounded, one record per round.

Done means all three rule kinds ran and passed. When a round has failures and no deterministic fix, or the
rounds run out, the loop stops and says why; it never reports compliance a check did not confirm.
"""
from __future__ import annotations

import pathlib

from .checks import fail_text, run_rules, write_round
from .generators.massing import generate
from .model import write_model
from .revise import propose_revisions


def run_loop(design: dict, params: dict, outdir, max_rounds: int = 5, on_round=None) -> dict:
    outdir = pathlib.Path(outdir)
    (outdir / "rounds").mkdir(parents=True, exist_ok=True)
    params = dict(params)
    rounds = []
    converged, reason, model = False, "", None
    for n in range(1, max_rounds + 1):  # n counts this run's rounds; the record's number continues the files'
        model = generate(design, params)
        model_path = write_model(model, outdir / "model.json")
        report = run_rules(model_path)
        revisions = [] if report["passed"] else propose_revisions(report, model["parameters"])
        record = write_round(outdir / "rounds", report, model["parameters"], revisions,
                             generator_notes=model["notes"])
        rounds.append(record)
        if on_round:
            on_round(record, model)
        if report["passed"]:
            converged, reason = True, f"all three rule kinds pass after {n} round(s)"
            break
        if not revisions:
            notes = "; ".join(model["notes"]) or "none"
            reason = (f"cannot converge: no parameter fix for the remaining failures, which need a layout or brief "
                      f"decision. Generator notes: {notes}\n{fail_text(record, 6)}")
            break
        for r in revisions:
            params[r["param"]] = r["to"]
    else:
        reason = f"did not converge within {max_rounds} round(s); last failures:\n{fail_text(record, 6)}"
    return {"converged": converged, "reason": reason, "rounds": rounds, "model": model,
            "model_path": str(outdir / "model.json")}
