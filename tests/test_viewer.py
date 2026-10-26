"""The live viewer: a local page plus a tiny JSON API over the model's solids."""
import json
import threading
import urllib.request

import pytest

from arch_harness import hooks
from arch_harness.project import build, init_project
from arch_harness.viewer import THREE_VERSION, make_server


@pytest.fixture
def served(tmp_path, clinic_design_path):
    project = init_project(clinic_design_path.parent, tmp_path / "clinic")
    build(project)
    server = make_server(project, 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield project, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.read().decode()


def test_page_loads_nothing_from_the_internet(served):
    """The viewer runs offline: three.js (pinned THREE_VERSION, MIT) ships in the repo and the page fetches only its own server."""
    _, base = served
    html = get(base + "/")
    assert "http://" not in html and "https://" not in html
    assert f"three@{THREE_VERSION}" in get(base + "/vendor/three/VERSION")
    assert "OrbitControls" in get(base + "/vendor/three/examples/jsm/controls/OrbitControls.js")
    assert get(base + "/vendor/three/build/three.module.js").startswith("/**")


def test_model_endpoint_serves_solids_and_failures(served):
    project, base = served
    hooks.after_step(project)
    data = json.loads(get(base + "/api/model"))
    ids = {s["id"] for s in data["solids"]}
    assert "L0-C" in ids and data["project"] == "Neighbourhood health clinic"
    assert "L0-D01" in data["failing"]  # the 85 cm doors fail DIN 18040-1
    assert data["status"]["round"] == 1 and data["status"]["passed"] is False


def test_version_changes_when_the_model_changes(served):
    project, base = served
    v1 = json.loads(get(base + "/api/version"))["version"]
    build(project, overrides={"door_width": 900, "corridor_width": 1800})
    v2 = json.loads(get(base + "/api/version"))["version"]
    assert v1 != v2


def test_selection_is_recorded_for_the_agent(served):
    project, base = served
    req = urllib.request.Request(base + "/api/select", data=json.dumps({"id": "L0-D01"}).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=5).read()
    assert json.loads((project / ".arch-harness" / "selection.json").read_text())["id"] == "L0-D01"


def test_page_escapes_names_before_building_html(served):
    """Element ids, names and messages come from DESIGN.md: no innerHTML interpolates them raw."""
    _, base = served
    html = get(base + "/")
    assert "const esc = " in html
    for raw in ("${s.id}", "${s.name}", "${s.kind}", "${s.storey}", "${f.rule}", "${f.message}", "${k}"):
        assert raw not in html, raw
