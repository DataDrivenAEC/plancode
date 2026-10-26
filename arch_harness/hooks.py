"""The hook contract: four calls any agent harness makes (also exposed as MCP tools and as a CLI).

1. after_step(project)      run the rules after a generator step; record the round; return failures as text
2. before_settle(project)   block settling while rules fail (bounded rounds; says why when it cannot converge)
3. context(project)         DESIGN.md plus the current status, to load as context before the agent starts
4. fork_variant(project, n) put a variant on its own git branch `variant/<n>`

Status is read from the round records in model/rounds/, never kept elsewhere. See docs/hook-contract.md.
"""
from __future__ import annotations

import json
import pathlib

from .checks import fail_text, kinds_line, run_rules, write_round
from .project import MODEL_DIR, git
from .revise import propose_revisions


def _rounds(project) -> list[pathlib.Path]:
    return sorted((pathlib.Path(project) / MODEL_DIR / "rounds").glob("round-*.json"), key=lambda p: int(p.stem[6:]))


def after_step(project) -> dict:
    project = pathlib.Path(project)
    model_path = project / MODEL_DIR / "model.json"
    if not model_path.exists():
        return {"round": None, "passed": False, "text": "arch-harness: no model to check yet (model/model.json)."}
    report = run_rules(model_path)
    params = json.loads(model_path.read_text())["parameters"]
    revisions = [] if report["passed"] else propose_revisions(report, params)
    record = write_round(project / MODEL_DIR / "rounds", report, params, revisions, source="after_step")
    n = record["round"]
    text = (f"arch-harness rules, round {n}: " + ("ALL PASS" if report["passed"] else "FAILING") + " — " +
            kinds_line(report["by_kind"]))
    if report["unconfirmed_kinds"]:
        text += f"; unconfirmed (nothing checked): {', '.join(report['unconfirmed_kinds'])}"
    if record["failures"] or record["unconfirmed_rules"]:
        text += "\n" + fail_text(record)
    if revisions:
        text += "\nDeterministic fixes (apply as overrides): " + ", ".join(
            f"{r['param']} {r['from']}→{r['to']}" for r in revisions)
    elif not report["passed"]:
        text += "\nNo parameter fix: these need a layout decision (see plan_svg and the generator notes)."
    return {"round": n, "passed": report["passed"], "by_kind": record["by_kind"], "failures": record["failures"],
            "unconfirmed_rules": record["unconfirmed_rules"],
            "revisions": revisions, "text": text}


def before_settle(project, max_rounds: int = 5, since_round: int = 0) -> dict:
    rounds = _rounds(project)
    if not rounds:
        return {"settle": True, "reason": "no model has been checked; nothing to hold"}
    last = json.loads(rounds[-1].read_text())
    if last["passed"]:
        return {"settle": True, "reason": f"all three rule kinds pass (round {last['round']})"}
    summary = fail_text(last, 6)
    if len(rounds) - since_round >= max_rounds:
        return {"settle": True, "reason": f"cannot converge within {max_rounds} round(s); still failing:\n{summary}"}
    return {"settle": False, "reason": f"rules still fail (round {last['round']}); fix them before finishing:\n{summary}"}


def status(project) -> dict:
    """How many rounds are recorded and whether the last passed (None before the first check)."""
    rounds = _rounds(project)
    return {"rounds": len(rounds), "passed": json.loads(rounds[-1].read_text())["passed"] if rounds else None}


def context(project) -> str:
    project = pathlib.Path(project)
    design = (project / "DESIGN.md").read_text(encoding="utf-8")
    rounds = _rounds(project)
    try:
        branch = git(project, "branch", "--show-current").strip() or "(detached)"
    except RuntimeError:
        branch = "(not a git repository)"
    if rounds:
        last = json.loads(rounds[-1].read_text())
        status = f"last check: round {last['round']}, " + ("all rules pass" if last["passed"] else
                                                           f"{len(last['failures'])} failure(s)")
    else:
        status = "no model yet: call generate_massing"
    return (f"# arch-harness project context\nBranch: {branch}. Status: {status}.\n"
            f"The model (model/model.json, mm) is the truth; USD, IFC and SVG are renders.\n\n"
            f"## DESIGN.md (the architect's intent)\n\n{design}")


def fork_variant(project, name: str) -> dict:
    branch = f"variant/{name}"
    existing = git(project, "branch", "--list", branch).strip()
    git(project, "switch", "-q", *([] if existing else ["-c"]), branch)
    return {"branch": branch, "created": not existing, "head": git(project, "rev-parse", "--short", "HEAD").strip()}
