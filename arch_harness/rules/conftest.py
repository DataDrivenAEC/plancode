"""Rule harness: load the model, parametrize rules over its elements, record one result per element.

A rule test requests one of these arguments and runs once per element:
  door, wall, corridor, room (spaces with use 'room'), side (the four building sides),
  space_pair (two spaces on one storey), required_room (one programme instance).
A rule fails by raising RuleFailure (via `fail`) so the result carries data (actual, required) the loop can use.
"""
from __future__ import annotations

import itertools
import json

import pytest


class RuleFailure(AssertionError):
    def __init__(self, message: str, **data):
        super().__init__(message)
        self.data = data


def fail(message: str, **data):
    raise RuleFailure(message, **data)


def pytest_addoption(parser):
    parser.addoption("--ah-model", required=True, help="model.json to check")
    parser.addoption("--ah-report", required=True, help="where to write the JSON results")


def _model(config):
    if not hasattr(config, "_ah_model"):
        with open(config.getoption("--ah-model"), encoding="utf-8") as fh:
            config._ah_model = json.load(fh)
    return config._ah_model


def required_rooms(model):
    """Programme instances: 'Name#k'. Storey 'each' means count per storey."""
    out = []
    n_storeys = len(model["storeys"])
    for entry in model["programme"]:
        count = entry["count"] * (n_storeys if entry["storey"] == "each" else 1)
        out += [(entry["name"], k, entry["area_m2"]) for k in range(1, count + 1)]
    return out


def pytest_generate_tests(metafunc):
    m = _model(metafunc.config)
    by_storey = {}
    for s in m["spaces"]:
        by_storey.setdefault(s["storey"], []).append(s)
    sources = {
        "door": [(d, d["id"]) for d in m["doors"]],
        "wall": [(w, w["id"]) for w in m["walls"]],
        "corridor": [(s, s["id"]) for s in m["spaces"] if s["use"] == "corridor"],
        "room": [(s, s["id"]) for s in m["spaces"] if s["use"] == "room"],
        "side": [(s, "building:" + s) for s in ("west", "east", "south", "north")],
        "space_pair": [((a, b), f"{a['id']}|{b['id']}")
                       for spaces in by_storey.values() for a, b in itertools.combinations(spaces, 2)],
        "required_room": [(r, f"{r[0]}#{r[1]}") for r in required_rooms(m)],
    }
    for name, items in sources.items():
        if name in metafunc.fixturenames:
            metafunc.parametrize(name, [i[0] for i in items], ids=[i[1] for i in items])


@pytest.fixture
def model(request):
    return _model(request.config)


def _element(item):
    cs = getattr(item, "callspec", None)
    return cs.id if cs else None


def pytest_configure(config):
    config._ah_results = []


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    marker = item.get_closest_marker("rule")
    if marker is None:
        return
    record = rep.when == "call" or (rep.when == "setup" and rep.outcome != "passed")
    if not record:
        return
    data, message, outcome = {}, "", rep.outcome
    if rep.skipped:  # e.g. an empty parameter set: nothing of this kind in the model
        outcome, message = "skipped", "no element to check"
    elif call.excinfo is not None:
        exc = call.excinfo.value
        message = str(exc).split("\n")[0]
        data = getattr(exc, "data", {})
        if not isinstance(exc, AssertionError):
            outcome, message = "error", f"rule error: {type(exc).__name__}: {message}"
    item.config._ah_results.append({
        "rule": marker.kwargs["id"],
        "kind": marker.kwargs["kind"],
        "element": None if outcome == "skipped" else _element(item),
        "outcome": outcome,
        "message": message,
        "data": data,
        "source": " ".join((item.function.__doc__ or "").split()),
    })


def pytest_sessionfinish(session):
    with open(session.config.getoption("--ah-report"), "w", encoding="utf-8") as fh:
        json.dump(session.config._ah_results, fh, indent=1)
