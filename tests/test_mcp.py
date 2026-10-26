"""The MCP server speaks JSON-RPC over stdio: any MCP-capable harness can drive arch-harness."""
import json
import subprocess
import sys

import pytest

from arch_harness.project import init_project


class Client:
    def __init__(self, project):
        self.proc = subprocess.Popen([sys.executable, "-m", "arch_harness.mcp_server", "--project", str(project)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     text=True)
        self.n = 0

    def request(self, method, params=None):
        self.n += 1
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}}) + "\n")
        self.proc.stdin.flush()
        msg = json.loads(self.proc.stdout.readline())
        assert msg["id"] == self.n
        return msg

    def notify(self, method):
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.proc.stdin.flush()

    def call(self, name, **arguments):
        return self.request("tools/call", {"name": name, "arguments": arguments})["result"]

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=10)


@pytest.fixture
def client(tmp_path, clinic_design_path):
    project = init_project(clinic_design_path.parent, tmp_path / "clinic")
    c = Client(project)
    yield c
    c.close()


def test_initialize_and_list_tools(client):
    init = client.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                         "clientInfo": {"name": "test", "version": "0"}})
    assert init["result"]["serverInfo"]["name"] == "arch-harness"
    assert "tools" in init["result"]["capabilities"]
    client.notify("notifications/initialized")
    tools = {t["name"]: t for t in client.request("tools/list")["result"]["tools"]}
    assert {"ah_context", "ah_after_step", "ah_before_settle", "ah_fork_variant", "generate_massing",
            "check_rules", "revise_parameters", "plan_svg", "export_ifc", "estimate_cost", "run_loop",
            "read_design", "list_plugins", "query_data_source", "commit"} <= set(tools)
    for t in tools.values():
        assert t["inputSchema"]["type"] == "object" and t["description"]


def test_generate_then_check_through_mcp(client):
    client.request("initialize", {"protocolVersion": "2025-06-18"})
    out = client.call("generate_massing")
    assert out["isError"] is False and "2 storey" in out["content"][0]["text"]
    step = client.call("ah_after_step")
    assert "FAILING" in step["content"][0]["text"] and step["structuredContent"]["round"] == 1
    settle = client.call("ah_before_settle", max_rounds=5)
    assert settle["structuredContent"]["settle"] is False
    client.call("generate_massing", overrides={"door_width": 900, "corridor_width": 1800})
    assert client.call("ah_after_step")["structuredContent"]["passed"] is True
    svg = client.call("plan_svg", storey="L0")["content"][0]["text"]
    assert svg.startswith("<svg")


def test_unknown_tool_is_an_error_result(client):
    client.request("initialize", {})
    msg = client.request("tools/call", {"name": "nope", "arguments": {}})
    assert msg["result"]["isError"] is True


def test_unknown_method_is_a_jsonrpc_error(client):
    assert client.request("resources/list")["error"]["code"] == -32601


def test_cli_hook_prints_json(tmp_path, clinic_design_path):
    project = init_project(clinic_design_path.parent, tmp_path / "p")
    out = subprocess.run([sys.executable, "-m", "arch_harness", "hook", "before-settle", "--project", str(project)],
                         capture_output=True, text=True, check=True)
    assert json.loads(out.stdout)["settle"] is True


def test_cli_init_creates_a_project(tmp_path):
    out = subprocess.run([sys.executable, "-m", "arch_harness", "init", "--example", "clinic", "--out",
                          str(tmp_path / "p")], capture_output=True, text=True, check=True)
    assert (tmp_path / "p" / "DESIGN.md").exists() and out.stdout.strip().endswith("p")
