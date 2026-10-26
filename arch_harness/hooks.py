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

from .checks import failures, run_rules
from .project import MODEL_DIR, git
from .revise import propose_revisions


def _rounds(project) -> list[pathlib.Path]:
    return sorted((pathlib.Path(project) / MODEL_DIR / "rounds").glob("round-*.json"))


def _fail_text(fails: list[dict], limit: int = 12) -> str:
    lines = [f"- [{f['kind']}] {f['rule']} @ {f['element']}: {f['message']}" for f in fails[:limit]]
    if len(fails) > limit:
        lines.append(f"- … and {len(fails) - limit} more")
    return "\n".join(lines)


def after_step(project) -> dict:
    project = pathlib.Path(project)
    model_path = project / MODEL_DIR / "model.json"
    if not model_path.exists():
        return {"round": None, "passed": False, "text": "arch-harness: no model to check yet (model/model.json)."}
    report = run_rules(model_path)
    fails = failures(report)
    params = json.loads(model_path.read_text())["parameters"]
    revisions = [] if report["passed"] else propose_revisions(report, params)
    n = len(_rounds(project)) + 1
    record = {"round": n, "source": "after_step", "parameters": params, "passed": report["passed"],
              "by_kind": report["by_kind"], "unconfirmed_kinds": report["unconfirmed_kinds"],
              "failures": [{k: f[k] for k in ("rule", "kind", "element", "message")} for f in fails],
              "revisions": revisions}
    path = project / MODEL_DIR / "rounds" / f"round-{n:02d}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n")
    k = report["by_kind"]
    head = (f"arch-harness rules, round {n}: " + ("ALL PASS" if report["passed"] else "FAILING") + " — " +
            ", ".join(f"{x} {k[x]['passed']} passed/{k[x]['failed']} failed" for x in ("code", "geometry", "brief")))
    if report["unconfirmed_kinds"]:
        head += f"; unconfirmed (nothing checked): {', '.join(report['unconfirmed_kinds'])}"
    text = head
    if fails:
        text += "\n" + _fail_text(fails)
    if revisions:
        text += "\nDeterministic fixes (apply as overrides): " + ", ".join(
            f"{r['param']} {r['from']}→{r['to']}" for r in revisions)
    elif fails:
        text += "\nNo parameter fix: these need a layout decision (see plan_svg and the generator notes)."
    return {"round": n, "passed": report["passed"], "by_kind": k, "failures": record["failures"],
            "revisions": revisions, "text": text}


def before_settle(project, max_rounds: int = 5, since_round: int = 0) -> dict:
    rounds = _rounds(project)
    if not rounds:
        return {"settle": True, "reason": "no model has been checked; nothing to hold"}
    last = json.loads(rounds[-1].read_text())
    if last["passed"]:
        return {"settle": True, "reason": f"all three rule kinds pass (round {last['round']})"}
    summary = _fail_text([dict(f) for f in last["failures"]], limit=6)
    if len(rounds) - since_round >= max_rounds:
        return {"settle": True, "reason": f"cannot converge within {max_rounds} round(s); still failing:\n{summary}"}
    return {"settle": False, "reason": f"rules still fail (round {last['round']}); fix them before finishing:\n{summary}"}


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
