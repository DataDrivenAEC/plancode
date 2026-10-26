# Hook contract

arch-harness keeps the domain (generators, rules, cost, export, data sources) in one Python MCP server. An agent
harness adds four calls at four points of its loop. That is the whole integration surface; `adapters/pi` is the
first implementation.

| # | Call | When the harness makes it | Returns |
|---|------|---------------------------|---------|
| 1 | `ah_after_step` | after every tool call that changes the model (`generate_massing`, `run_loop`) | `round`, `passed`, `by_kind`, `failures`, `revisions`, and `text` to append to the tool result |
| 2 | `ah_before_settle(max_rounds, since_round)` | when the agent is about to finish | `settle` (bool) and `reason`; `settle=false` while rules fail and fewer than `max_rounds` rounds ran since `since_round`; at the limit `settle=true` with "cannot converge …" |
| 3 | `ah_context` | before the agent starts a run | text: DESIGN.md plus the project status; structured: `{rounds, passed}` |
| 4 | `ah_fork_variant(name)` | when the session forks or the architect asks for a variant | `{branch: "variant/<name>", created, head}` |

Rules for an adapter:

- Make call 1 only after a model-changing step, and give its `text` to the model with the tool result.
- Hold settling (call 2) only when this run recorded a round (`ah_context.rounds` grew); bound the holds.
- When call 2 settles with a "cannot converge" reason, show the reason; never report success.
- Status is read from the round records in `model/rounds/`; an adapter keeps no copy of it.

The same calls exist as a command line for harnesses whose hooks run shell commands:

```bash
python -m arch_harness hook context       --project DIR
python -m arch_harness hook after-step    --project DIR
python -m arch_harness hook before-settle --project DIR --max-rounds 5 --since-round 0
python -m arch_harness hook fork-variant  --project DIR --name timber
```

The MCP server: `python -m arch_harness.mcp_server --project DIR` (stdio, JSON-RPC 2.0, MCP `initialize`,
`tools/list`, `tools/call`, `ping`).
