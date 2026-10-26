# arch-harness adapter for pi

The first adapter: a [pi](https://github.com/earendil-works/pi) package that puts the arch-harness
[hook contract](../../docs/hook-contract.md) on pi's extension events and exposes the MCP server's tools as pi tools.

| pi event | contract call |
|---|---|
| `before_agent_start` | `ah_context`: DESIGN.md and the status as a system-prompt section |
| `tool_result` (after `generate_massing`, `run_loop`) | `ah_after_step`: the rule failures appended to the tool result |
| `agent_before_settle` | `ah_before_settle`: no settling while rules fail, bounded by `AH_MAX_ROUNDS` (default 5) |
| session fork, `/variant <name>` | `ah_fork_variant`: the variant on its own git branch |

```bash
# from the repository root, after the quick start in the main README
.conda-ah/bin/python -m arch_harness init --example clinic --out build/my-clinic
mkdir -p build/pi-agent && cp adapters/pi/examples/models.ollama.json build/pi-agent/models.json
cd build/my-clinic
PATH=$PWD/../../.tools/node/bin:$PATH PI_CODING_AGENT_DIR=$PWD/../pi-agent \
  ../../node_modules/.bin/pi -e ../../adapters/pi --no-builtin-tools --model ollama/qwen3.6:27b
```

Settings: `AH_PYTHON` (default `<repo>/.conda-ah/bin/python`), `AH_PROJECT` (default the working directory),
`AH_MAX_ROUNDS`. Any model pi supports works; with a local model (Ollama) nothing leaves the machine.

Offline test (a real pi session with pi's faux provider, no model, no key):

```bash
.tools/node/bin/node --test adapters/pi/test/adapter.test.ts
```
