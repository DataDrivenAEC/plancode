"""Run the rules (pytest) against a model and return one structured report."""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile

RULES_DIR = pathlib.Path(__file__).parent / "rules"
KINDS = ("code", "geometry", "brief")


def run_rules(model_path) -> dict:
    """Run every rule on model_path. `passed` is true only when all three kinds ran at least one check and none
    failed; a kind with no checks is listed in `unconfirmed_kinds`, never reported as passing."""
    with tempfile.TemporaryDirectory() as tmp:
        report = pathlib.Path(tmp) / "rules.json"
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(RULES_DIR), "-c", str(RULES_DIR / "pytest.ini"),
             "--rootdir", str(RULES_DIR), "-q", "--no-header", "-p", "no:randomly",
             f"--ah-model={pathlib.Path(model_path).resolve()}", f"--ah-report={report}"],
            capture_output=True, text=True, cwd=RULES_DIR)
        if not report.exists():
            raise RuntimeError(f"rules did not run (rc={proc.returncode}): {proc.stdout[-2000:]}{proc.stderr[-2000:]}")
        results = json.loads(report.read_text())
    by_kind = {k: {"passed": 0, "failed": 0, "error": 0, "skipped": 0} for k in KINDS}
    for r in results:
        by_kind[r["kind"]][r["outcome"]] += 1
    unconfirmed = [k for k in KINDS if by_kind[k]["passed"] + by_kind[k]["failed"] + by_kind[k]["error"] == 0]
    bad = sum(by_kind[k]["failed"] + by_kind[k]["error"] for k in KINDS)
    return {"passed": bad == 0 and not unconfirmed, "by_kind": by_kind, "unconfirmed_kinds": unconfirmed,
            "results": results}


def failures(report: dict) -> list[dict]:
    return [r for r in report["results"] if r["outcome"] in ("failed", "error")]
